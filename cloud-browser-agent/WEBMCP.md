# WebMCP integration

JobAutoApply exposes three browser-native WebMCP tools on the Cloud Job Assistant home page.

## Tools

- `get_candidate_profile` — reads the candidate profile from `GET /api/profile`.
- `list_application_tasks` — reads preparation records from `GET /api/tasks`.
- `prepare_application_brief` — validates a public HTTP(S) job URL and creates a draft record through `POST /api/tasks`.

The preparation tool only creates a draft. It does not sign in to job boards, contact employers, or submit applications. Existing approval gates and daily application limits are not bypassed.

## Browser requirements

WebMCP is experimental and browser support is not universal. The integration feature-detects `document.modelContext`; if unavailable, the ordinary web interface continues to work and displays a compatibility message. Serve the app over HTTPS (or localhost) in a browser build that enables WebMCP.

The implementation uses the current document-scoped Imperative API and returns structured JSON errors to the agent. Tools are registered for the lifetime of the page.

## Manual verification

1. Deploy the `cloud-browser-agent` service over HTTPS.
2. Open the home page in a WebMCP-enabled browser.
3. Confirm the status line says that three tools were registered.
4. Ask the browser agent to read the candidate profile and list application tasks.
5. Ask it to prepare a brief using a public job URL; confirm a new item appears in Task history.
6. Confirm no application was submitted and no third-party login was attempted.

## Current MVP limitations

- Application tasks are held in process memory and reset when the service restarts or sleeps.
- The current backend creates a generic honest draft from the configured profile; it does not fetch or parse the job posting when preparing a brief.
- The existing `/api/tasks` endpoints are not authenticated. Do not expose this prototype to untrusted users or sensitive candidate data without adding per-user authentication, authorization, CSRF protections where applicable, rate limiting, and persistent storage.
