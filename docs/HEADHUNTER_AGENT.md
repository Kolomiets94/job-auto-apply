# HeadHunter resume review (read-only)

Run **Actions → HeadHunter Resume Agent → Run workflow**. The agent opens the
existing resume pages and extracts their visible text into a JSON report.
Optionally provide an HTTPS hh.ru/vacancy/... URL in the **Target vacancy URL**
field to compare the resume with one vacancy and prepare a conservative draft.

Download the hh-resume-review artifact from the completed workflow run. It
contains personal resume text and must be treated as confidential. It is not
printed into Actions logs and is retained for 7 days. Restrict repository
collaborator access accordingly.

Recommendations are deterministic checklist prompts, not claims about
candidate qualifications. Keyword matches are not proof of experience. Review
all suggestions and drafts manually before using them.

Safety:
- Read-only browser navigation; no resume edits or saves.
- No application or response submission.
- No CAPTCHA/2FA bypass.
- Session remains in the HH_STORAGE_STATE_JSON Actions secret and is never
  written to the report.
- Existing Auto Apply workflows and business logic are unchanged.
