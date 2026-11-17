extern alias WebService;
extern alias StudentsService;
extern alias AcademicsService;
extern alias EnrollmentsService;

using System.IdentityModel.Tokens.Jwt;
using System.Net.Http.Headers;
using System.Security.Claims;
using System.Security.Cryptography;
using Azure.Core;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Data.SqlClient;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.IdentityModel.Protocols;
using Microsoft.IdentityModel.Protocols.OpenIdConnect;
using Microsoft.IdentityModel.Tokens;
using WebTokens = WebService::Contoso.Web.Services.IDelegatedTokens;

namespace Contoso.RuntimeIntegration;

internal sealed class RuntimeStack : IAsyncDisposable
{
    internal const string Tenant = "11111111-1111-1111-1111-111111111111";
    internal const string Issuer = $"https://login.microsoftonline.com/{Tenant}/v2.0";
    private readonly RSA rsa = RSA.Create(2048);
    private readonly Dictionary<string, string> connections = new();
    private readonly string master;
    internal readonly HashSet<string> FailedOrigins = [];
    internal readonly List<(string Service, string Path, string Identity)> Calls = [];
    private readonly ServiceFactory<StudentsService::Program> students;
    private readonly ServiceFactory<AcademicsService::Program> academics;
    private readonly ServiceFactory<EnrollmentsService::Program> enrollments;
    private readonly ServiceFactory<WebService::Program> web;

    internal RuntimeStack()
    {
        var sourceRoot = Environment.GetEnvironmentVariable("CONTOSO_RUNTIME_SOURCES")
            ?? throw new InvalidOperationException("CONTOSO_RUNTIME_SOURCES must identify the four pinned source checkouts.");
        var sql = Environment.GetEnvironmentVariable("CONTOSO_RUNTIME_SQL_CONNECTION")
            ?? throw new InvalidOperationException("Disposable loopback SQL is mandatory; no SQLite fallback or skipped test.");
        var settings = new SqlConnectionStringBuilder(sql);
        if (settings.DataSource is not ("127.0.0.1,1433" or "localhost,1433")
            || settings.FailoverPartner.Length != 0 || settings.AttachDBFilename.Length != 0)
            throw new InvalidOperationException("Only the disposable loopback SQL instance is accepted.");
        settings.InitialCatalog = "master";
        settings.Pooling = false;
        master = settings.ConnectionString;
        foreach (var service in new[] { "Students", "Academics", "Enrollments" })
        {
            settings.InitialCatalog = $"AdlcRuntime_{service}_{Guid.NewGuid():N}";
            connections.Add(service, settings.ConnectionString);
        }
        students = Api<StudentsService::Program>("Students");
        academics = Api<AcademicsService::Program>("Academics");
        enrollments = Api<EnrollmentsService::Program>("Enrollments", services =>
        {
            services.RemoveAll<TokenCredential>();
            services.AddSingleton<TokenCredential>(new LookupCredential(this));
            services.AddHttpClient("references").ConfigurePrimaryHttpMessageHandler(() => new Router(this));
        });
        var webConfiguration = Configuration("Web");
        webConfiguration["AzureAd:ClientId"] = "22222222-2222-2222-2222-222222222222";
        webConfiguration["AzureAd:ClientCredentials:0:SourceType"] = "SignedAssertionFromManagedIdentity";
        webConfiguration["AllowedHosts"] = "web.runtime.test";
        foreach (var service in connections.Keys)
        {
            var lower = service.ToLowerInvariant();
            webConfiguration[$"Services:{service}:BaseUrl"] = $"https://{lower}.runtime.test/";
            webConfiguration[$"Services:{service}:ReadScopes:0"] = $"api://runtime-{lower}/{lower}.read";
            if (service == "Enrollments")
            {
                webConfiguration[$"Services:{service}:WriteScopes:0"] = $"api://runtime-{lower}/{lower}.read";
                webConfiguration[$"Services:{service}:WriteScopes:1"] = $"api://runtime-{lower}/{lower}.write";
            }
        }
        web = new ServiceFactory<WebService::Program>(
            Path.Combine(sourceRoot, "contoso-web", "src", "Contoso.Web"), webConfiguration, services =>
            {
                services.AddAuthentication(options =>
                {
                    options.DefaultAuthenticateScheme = "runtime-user";
                    options.DefaultChallengeScheme = "runtime-user";
                }).AddJwtBearer("runtime-user", options =>
                {
                    options.Audience = Audience("Web");
                    options.MapInboundClaims = false;
                    options.TokenValidationParameters = new TokenValidationParameters
                    {
                        ValidAudience = Audience("Web"),
                        ValidIssuer = Issuer,
                        ValidateIssuer = true,
                        ValidateAudience = true,
                        ValidateLifetime = true,
                        ValidateIssuerSigningKey = true,
                        RequireSignedTokens = true,
                        RoleClaimType = "roles",
                        NameClaimType = "sub",
                        ClockSkew = TimeSpan.Zero
                    };
                    ConfigureJwt(options);
                });
                services.RemoveAll<WebTokens>();
                services.AddScoped<WebTokens>(provider => new DelegatedCredential(
                    this, provider.GetRequiredService<IHttpContextAccessor>()));
                foreach (var service in connections.Keys)
                    services.AddHttpClient(service).ConfigurePrimaryHttpMessageHandler(() => new Router(this));
            });

        ServiceFactory<T> Api<T>(string service, Action<IServiceCollection>? configure = null) where T : class =>
            new(Path.Combine(sourceRoot, $"contoso-{service.ToLowerInvariant()}", "src",
                    service == "Academics" ? "Contoso.Academics" : $"Contoso.{service}.Api"),
                Configuration(service), services =>
                {
                    services.PostConfigure<JwtBearerOptions>(JwtBearerDefaults.AuthenticationScheme, ConfigureJwt);
                    configure?.Invoke(services);
                });
    }

    private Dictionary<string, string?> Configuration(string service)
    {
        var values = new Dictionary<string, string?>
        {
            ["AzureAd:TenantId"] = Tenant,
            ["AzureAd:Audience"] = Audience(service)
        };
        if (connections.TryGetValue(service, out var connection))
            values[$"ConnectionStrings:{service}"] = connection;
        if (service == "Enrollments")
            foreach (var reference in new[] { "Students", "Academics" })
            {
                values[$"{reference}:BaseUrl"] = $"https://{reference.ToLowerInvariant()}.runtime.test/";
                values[$"{reference}:Scope"] = $"api://runtime-{reference.ToLowerInvariant()}/.default";
            }
        return values;
    }

    private static string Audience(string service) => $"api://runtime-{service.ToLowerInvariant()}";
    private void ConfigureJwt(JwtBearerOptions options)
    {
        var metadata = new OpenIdConnectConfiguration { Issuer = Issuer };
        metadata.SigningKeys.Add(new RsaSecurityKey(rsa) { KeyId = "synthetic-runtime-key" });
        options.ConfigurationManager = new StaticConfigurationManager<OpenIdConnectConfiguration>(metadata);
        options.TokenValidationParameters.ClockSkew = TimeSpan.Zero;
    }

    internal string Token(string service, string role = "Registrar", bool appOnly = false, string? audience = null,
        string? delegatedScopes = null)
    {
        var lower = service.ToLowerInvariant();
        var claims = new List<Claim> { new("sub", "synthetic-runtime-user"), new("roles", role) };
        if (appOnly) claims.Add(new Claim("idtyp", "app"));
        else claims.Add(new Claim("scp", delegatedScopes ?? $"{lower}.read {lower}.write"));
        return new JwtSecurityTokenHandler().WriteToken(new JwtSecurityToken(
            Issuer, audience ?? Audience(service), claims, DateTime.UtcNow.AddMinutes(-1),
            DateTime.UtcNow.AddMinutes(5),
            new SigningCredentials(new RsaSecurityKey(rsa) { KeyId = "synthetic-runtime-key" }, SecurityAlgorithms.RsaSha256)));
    }

    internal HttpClient Client(string service, string role = "Registrar", bool appOnly = false, string? audience = null)
    {
        var factory = service switch
        {
            "Students" => students.CreateClient(Options(service)),
            "Academics" => academics.CreateClient(Options(service)),
            "Enrollments" => enrollments.CreateClient(Options(service)),
            "Web" => web.CreateClient(Options(service)),
            _ => throw new InvalidOperationException("Unknown service")
        };
        factory.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", Token(service, role, appOnly, audience));
        return factory;
    }

    private static WebApplicationFactoryClientOptions Options(string service) => new()
    {
        BaseAddress = new Uri($"https://{service.ToLowerInvariant()}.runtime.test"),
        AllowAutoRedirect = false
    };

    internal async Task InitializeAsync()
    {
        await Migrate<StudentsService::Program, StudentsService::Contoso.Students.Api.StudentsDbContext>(students);
        await Migrate<AcademicsService::Program, AcademicsService::Contoso.Academics.AcademicsDbContext>(academics);
        await Migrate<EnrollmentsService::Program, EnrollmentsService::Contoso.Enrollments.Api.EnrollmentDb>(enrollments);
    }

    private static async Task Migrate<TProgram, TDatabase>(WebApplicationFactory<TProgram> factory)
        where TProgram : class where TDatabase : DbContext
    {
        using var scope = factory.Services.CreateScope();
        await scope.ServiceProvider.GetRequiredService<TDatabase>().Database.MigrateAsync();
    }

    public async ValueTask DisposeAsync()
    {
        await web.DisposeAsync();
        await enrollments.DisposeAsync();
        await academics.DisposeAsync();
        await students.DisposeAsync();
        await using var connection = new SqlConnection(master);
        await connection.OpenAsync();
        foreach (var value in connections.Values)
        {
            var name = new SqlConnectionStringBuilder(value).InitialCatalog;
            if (!System.Text.RegularExpressions.Regex.IsMatch(name, @"^AdlcRuntime_(Students|Academics|Enrollments)_[0-9a-f]{32}$"))
                throw new InvalidOperationException("Refusing to delete an unexpected database.");
            await using var command = connection.CreateCommand();
            command.CommandText = $"IF DB_ID(@name) IS NOT NULL DROP DATABASE [{name}]";
            command.Parameters.AddWithValue("@name", name);
            await command.ExecuteNonQueryAsync();
        }
        rsa.Dispose();
    }

    private sealed class Router(RuntimeStack stack) : HttpMessageHandler
    {
        private readonly Dictionary<string, HttpMessageInvoker> invokers = [];
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var uri = request.RequestUri ?? throw new InvalidOperationException("Missing request URI");
            if (uri.Scheme != "https" || uri.Port != 443 || uri.UserInfo.Length != 0)
                throw new InvalidOperationException("Only controlled HTTPS service origins are routable.");
            var service = uri.Host switch
            {
                "students.runtime.test" => "Students",
                "academics.runtime.test" => "Academics",
                "enrollments.runtime.test" => "Enrollments",
                _ => throw new InvalidOperationException("Unrecognized service origin")
            };
            if (stack.FailedOrigins.Contains(service))
                throw new HttpRequestException("Controlled integration transport failure");
            var jwt = new JwtSecurityTokenHandler().ReadJwtToken(
                request.Headers.Authorization?.Parameter ?? throw new InvalidOperationException("Missing service bearer token"));
            stack.Calls.Add((service, uri.AbsolutePath, jwt.Claims.Any(c => c.Type == "idtyp" && c.Value == "app") ? "app" : "user"));
            if (!invokers.TryGetValue(service, out var invoker))
            {
                var handler = service switch
                {
                    "Students" => stack.students.Server.CreateHandler(),
                    "Academics" => stack.academics.Server.CreateHandler(),
                    _ => stack.enrollments.Server.CreateHandler()
                };
                invoker = new HttpMessageInvoker(handler);
                invokers.Add(service, invoker);
            }
            return invoker.SendAsync(request, cancellationToken);
        }
        protected override void Dispose(bool disposing)
        {
            if (disposing) foreach (var invoker in invokers.Values) invoker.Dispose();
            base.Dispose(disposing);
        }
    }

    private sealed class LookupCredential(RuntimeStack stack) : TokenCredential
    {
        public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken) =>
            GetTokenAsync(requestContext, cancellationToken).AsTask().GetAwaiter().GetResult();
        public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
        {
            var service = requestContext.Scopes.Single() switch
            {
                "api://runtime-students/.default" => "Students",
                "api://runtime-academics/.default" => "Academics",
                _ => throw new InvalidOperationException("Unexpected lookup scope")
            };
            return ValueTask.FromResult(new AccessToken(stack.Token(service, $"{service}.Lookup", true), DateTimeOffset.UtcNow.AddMinutes(5)));
        }
    }

    private sealed class DelegatedCredential(RuntimeStack stack, IHttpContextAccessor context) : WebTokens
    {
        public Task<string> GetAsync(string[] scopes)
        {
            var service = scopes.First().Split('/')[2] switch
            {
                "runtime-students" => "Students",
                "runtime-academics" => "Academics",
                "runtime-enrollments" => "Enrollments",
                _ => throw new InvalidOperationException("Unexpected delegated resource")
            };
            if (scopes.Any(scope => !scope.StartsWith(Audience(service) + "/", StringComparison.Ordinal)))
                throw new InvalidOperationException("Cross-resource token request");
            var role = context.HttpContext!.User.IsInRole("Registrar") ? "Registrar" : "Reader";
            var permissions = string.Join(" ", scopes.Select(scope => scope[(scope.LastIndexOf('/') + 1)..]));
            return Task.FromResult(stack.Token(service, role, delegatedScopes: permissions));
        }
    }
}

internal sealed class ServiceFactory<TProgram>(
    string source, Dictionary<string, string?> configuration, Action<IServiceCollection> configure)
    : WebApplicationFactory<TProgram> where TProgram : class
{
    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Testing").UseContentRoot(source);
        builder.ConfigureAppConfiguration((_, values) => values.AddInMemoryCollection(configuration));
        builder.ConfigureTestServices(configure);
    }
}
