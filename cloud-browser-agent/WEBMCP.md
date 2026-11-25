# WebMCP integration

JobAutoApply exposes three browser-native WebMCP tools on the Cloud Job Assistant home page.

## Tools

- `get_candidate_profile` — reads the candidate profile from `GET /api/profile`.
- `list_application_tasks` — reads preparation records from `GET /api/tasks`.
- `prepare_application_brief` — validates a public HTTP(S) job URL and creates a draft record through `POST /api/tasks`.

The preparation tool only creates a draft. It does not sign in to job boards, contact employers, or submit applications. Existing approval gates and daily application limits are not bypassed.

## Browser requirements

WebMCP is experimental and browser support is not universal. The integration feature-detects `document.modelContext`; if unavailable, the ordinary web interface continues to work and displays a compatibility message. Serve the app over HTTPS (or localhost) in a browser build that enables WebMCP.

## Visible diagnostic panel

The home page shows a WebMCP diagnostic panel:

- **API unavailable** — this browser does not expose `document.modelContext`; this is not evidence that the site deployment failed.
- **Registration pending** — the browser API exists and the page is registering the three tools.
- **Registration confirmed** — all three `registerTool()` promises resolved and `getTools()` returned all three expected names for this page.
- **Registration check incomplete** — registration calls resolved, but `getTools()` was unavailable or failed.
- **Registration error** — one or more registration calls failed, or `getTools()` did not return every expected tool.

The code calls `waitForToolsUntil(registration)` when the browser exposes it. This is a documented WebMCP API method that tells tool consumers to wait for asynchronous registration to settle.

Important: `getTools()` confirms the tools registered in the page's model context. It does not independently prove that an external browser agent has discovered them. Use the browser's WebMCP inspector or agent tool list for that final check.

The panel lists the tool names and includes desktop setup instructions. On a desktop Chrome/Chrome Canary build where WebMCP is not enabled, open `chrome://flags/#enable-webmcp-testing`, enable the flag if it is available in that build, restart the browser, and reload the page. Flag availability depends on the browser version/channel. Mobile browsers may not expose the experimental API.

The panel also warns that the prototype's `/api/profile` and `/api/tasks` endpoints currently have no authentication. The profile includes contact information. Do not use the public prototype for sensitive data until authentication and authorization are implemented.

## Manual verification

1. Open the deployed Cloud Job Assistant home page over HTTPS in a WebMCP-enabled desktop browser.
2. Confirm the diagnostic panel reports that `getTools()` returned all three expected names.
3. Use the browser's WebMCP inspector or agent tool list to confirm discovery of `get_candidate_profile`, `list_application_tasks`, and `prepare_application_brief`.
4. Invoke the two read-only tools and confirm they return profile and task data.
5. If testing `prepare_application_brief`, use a public job URL and confirm a draft appears in Task history. This does not submit an application.

## Current MVP limitations

- Application tasks are held in process memory and reset when the service restarts or sleeps.
- The current backend creates a generic honest draft from the configured profile; it does not fetch or parse the job posting when preparing a brief.
- The existing `/api/tasks` endpoints are not authenticated, and `/api/profile` exposes configured candidate contact information. Do not expose this prototype to untrusted users or sensitive candidate data without adding per-user authentication, authorization, CSRF protections where applicable, rate limiting, and persistent storage.
