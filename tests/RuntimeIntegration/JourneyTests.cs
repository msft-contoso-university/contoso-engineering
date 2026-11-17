using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.VisualStudio.TestTools.UnitTesting;

[assembly: DoNotParallelize]

namespace Contoso.RuntimeIntegration;

[TestClass]
public sealed class JourneyTests
{
    private RuntimeStack? stack;
    private RuntimeStack Stack => stack ?? throw new InvalidOperationException("Runtime stack not initialized");

    [TestInitialize]
    public async Task Initialize()
    {
        stack = new RuntimeStack();
        await stack.InitializeAsync();
    }

    [TestCleanup]
    public async Task Cleanup()
    {
        if (stack is not null) await stack.DisposeAsync();
    }

    [TestMethod]
    public async Task WebJourneyPersistsEnrollmentAndGradeAcrossRealServices()
    {
        var (student, course) = await SeedReferences();
        using var browser = Stack.Client("Web");
        StringAssert.Contains(await browser.GetStringAsync($"/Students?id={student}"), "Runtime Student");
        StringAssert.Contains(await browser.GetStringAsync($"/Catalog/Details/{course}"), "Runtime Course");
        using var created = await PostForm(browser, "/Enrollments/Create", new()
        {
            ["StudentId"] = student.ToString(),
            ["CourseId"] = course.ToString(),
            ["Grade"] = "A"
        });
        Assert.AreEqual(HttpStatusCode.Redirect, created.StatusCode);
        var enrollment = await SingleEnrollment();
        Assert.AreEqual(student, enrollment.GetProperty("studentId").GetInt32());
        Assert.AreEqual(course, enrollment.GetProperty("courseId").GetInt32());
        var id = enrollment.GetProperty("id").GetInt32();
        using var changed = await PostForm(browser, $"/Enrollments/Edit/{id}", new() { ["Grade"] = "B" });
        Assert.AreEqual(HttpStatusCode.Redirect, changed.StatusCode);
        Assert.AreEqual("B", (await SingleEnrollment()).GetProperty("grade").GetString());
        Assert.IsTrue(Stack.Calls.Any(call => call.Service == "Students" && call.Identity == "app"));
        Assert.IsTrue(Stack.Calls.Any(call => call.Service == "Academics" && call.Identity == "app"));
        Assert.IsTrue(Stack.Calls.Any(call => call.Service == "Students" && call.Identity == "user"));
    }

    [TestMethod]
    public async Task ReaderCannotWriteThroughWebOrDirectApi()
    {
        using var browser = Stack.Client("Web", "Reader");
        using var response = await PostForm(browser, "/Enrollments/Create", new()
        {
            ["StudentId"] = "1",
            ["CourseId"] = "1",
            ["Grade"] = "A"
        });
        Assert.AreEqual(HttpStatusCode.Forbidden, response.StatusCode);
        using var direct = Stack.Client("Enrollments", "Reader");
        using var denied = await direct.PostAsJsonAsync("/api/v1/enrollments/", new { studentId = 1, courseId = 1, grade = "A" });
        Assert.AreEqual(HttpStatusCode.Forbidden, denied.StatusCode);
        Assert.IsFalse(Stack.Calls.Any(call => call.Identity == "app"));
        await AssertEmpty();
    }

    [TestMethod]
    public async Task AppOnlyIdentityCannotWriteDelegatedEnrollment()
    {
        foreach (var role in new[] { "Students.Lookup", "Registrar" })
        {
            using var client = Stack.Client("Enrollments", role, appOnly: true);
            using var response = await client.PostAsJsonAsync("/api/v1/enrollments/", new { studentId = 1, courseId = 1, grade = "A" });
            Assert.AreEqual(HttpStatusCode.Forbidden, response.StatusCode, $"App-only {role} must not write.");
        }
        Assert.IsFalse(Stack.Calls.Any(call => call.Identity == "app"));
        await AssertEmpty();
    }

    [TestMethod]
    [DataRow("Students", DisplayName = "MissingStudentReference")]
    [DataRow("Academics", DisplayName = "MissingCourseReference")]
    public async Task MissingReferencesDoNotPersistEnrollment(string missing)
    {
        var (student, course) = await SeedReferences();
        using var client = Stack.Client("Enrollments");
        using var response = await client.PostAsJsonAsync("/api/v1/enrollments/", new
        {
            studentId = missing == "Students" ? int.MaxValue : student,
            courseId = missing == "Academics" ? int.MaxValue : course,
            grade = "A"
        });
        Assert.AreEqual(HttpStatusCode.BadRequest, response.StatusCode);
        await AssertEmpty();
    }

    [TestMethod]
    public async Task UpstreamTransportFailureIsVisibleAndDoesNotPersist()
    {
        var (student, course) = await SeedReferences();
        Stack.FailedOrigins.Add("Academics");
        using var client = Stack.Client("Enrollments");
        using var failed = await client.PostAsJsonAsync("/api/v1/enrollments/", new { studentId = student, courseId = course, grade = "A" });
        Assert.AreEqual(HttpStatusCode.ServiceUnavailable, failed.StatusCode);
        using var browser = Stack.Client("Web");
        using var visible = await browser.GetAsync("/Catalog");
        Assert.AreEqual(HttpStatusCode.ServiceUnavailable, visible.StatusCode);
        StringAssert.Contains(await visible.Content.ReadAsStringAsync(), "Service unavailable");
        await AssertEmpty();
    }

    [TestMethod]
    public async Task WrongAudienceDoesNotReachEnrollmentWrites()
    {
        using var client = Stack.Client("Enrollments", audience: "api://runtime-students");
        using var response = await client.PostAsJsonAsync("/api/v1/enrollments/", new { studentId = 1, courseId = 1, grade = "A" });
        Assert.AreEqual(HttpStatusCode.Unauthorized, response.StatusCode);
        await AssertEmpty();
    }

    private async Task<(int Student, int Course)> SeedReferences()
    {
        using var students = Stack.Client("Students");
        using var student = await students.PostAsJsonAsync("/api/v1/students", new
        {
            firstName = "Runtime",
            lastName = "Student",
            enrollmentDate = "2024-09-01T00:00:00Z"
        });
        Assert.AreEqual(HttpStatusCode.Created, student.StatusCode);
        var studentId = (await student.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32();
        using var academics = Stack.Client("Academics");
        using var department = await academics.PostAsJsonAsync("/api/v1/departments", new
        {
            name = "Runtime Department",
            budget = 1000,
            startDate = "2024-01-01"
        });
        Assert.AreEqual(HttpStatusCode.Created, department.StatusCode);
        var departmentId = (await department.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32();
        using var course = await academics.PostAsJsonAsync("/api/v1/courses", new
        {
            title = "Runtime Course",
            credits = 3,
            departmentId
        });
        Assert.AreEqual(HttpStatusCode.Created, course.StatusCode);
        return (studentId, (await course.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("id").GetInt32());
    }

    private async Task<JsonElement> SingleEnrollment()
    {
        using var client = Stack.Client("Enrollments");
        var document = await client.GetFromJsonAsync<JsonElement>("/api/v1/enrollments/");
        Assert.AreEqual(1, document.GetProperty("totalCount").GetInt32());
        return document.GetProperty("items")[0];
    }

    private async Task AssertEmpty()
    {
        using var client = Stack.Client("Enrollments");
        var document = await client.GetFromJsonAsync<JsonElement>("/api/v1/enrollments/");
        Assert.AreEqual(0, document.GetProperty("totalCount").GetInt32());
    }

    private static async Task<HttpResponseMessage> PostForm(HttpClient browser, string path, Dictionary<string, string> values)
    {
        var html = await browser.GetStringAsync(path);
        var token = Regex.Match(html, "name=\"__RequestVerificationToken\"[^>]*value=\"([^\"]+)\"", RegexOptions.CultureInvariant);
        Assert.IsTrue(token.Success, "Actual Web form must include antiforgery protection.");
        values.Add("__RequestVerificationToken", WebUtility.HtmlDecode(token.Groups[1].Value));
        return await browser.PostAsync(path, new FormUrlEncodedContent(values));
    }
}
