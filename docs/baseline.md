# Source baseline observations

These are static observations from the authorized reference checkout at commit
`0716ee7262eff2c268ebb72097ceb93e0fc83536`, not an executed characterization
suite or proof of behavior parity. The original source is MIT licensed; retain
its license and copyright notice in repositories containing derived code.

- The Razor UI calls the API for student, course, department and instructor
  journeys. Student detail consumes a student response containing courses.
- The API exposes CRUD routes under `api/Students`, `api/Courses`,
  `api/Departments` and `api/Instructors`. Students and instructors use
  50-item pages; student search uses a first/last-name prefix.
- Student and course details currently compose data in one EF context. Course
  responses embed department details; department responses embed instructor
  details. The `StudentCourse` key is the course/student pair.
- Individual missing records return 404, successful updates return 204,
  successful creates return 201, and successful deletes return 200 with the
  deleted object. Updates with a different route and body ID return 400.
  Constraint failures and concurrent deletes require characterization against
  the SQL provider before defining equivalent cross-service behavior.
- `CancelarMatricula/{id}` currently returns success without changing data; it
  is not evidence that enrollment cancellation works.
- Startup calls `EnsureCreatedAsync` and uses random synthetic seed data.
  Replacement must use separately authorized migrations and deterministic
  seeding. Existing course and department names remain useful fixtures.
- The test project uses MSTest despite misleading namespace text; at least the
  course tests are placeholder assertions, not a behavior baseline.

Before extraction, add executable characterization tests for observable
journeys, validation, deletes and dependency failures. Do not equate this static
inventory with those tests or assume deletion semantics that were not observed.
