# HeadHunter agent (GitHub Actions)

This is the first, deliberately read-only stage of the autonomous browser agent.
It runs Chromium on GitHub-hosted runners, so your computer can be off.

## Configure the session once

1. Sign in to HeadHunter in a trusted local browser.
2. Export a Playwright storage-state JSON for the HH domain using the existing
   `hh-bootstrap` session-export flow in this repository. The export contains
   account credentials in the form of session cookies; treat it like a password.
3. In the GitHub repository, open **Settings → Secrets and variables → Actions**
   and create an Actions secret named `HH_STORAGE_STATE_JSON` with the complete
   storage-state JSON as its value. Do not commit this file, paste it into issues,
   or send it in chat.
4. Open **Actions → HeadHunter Resume Agent → Run workflow**.

The workflow uses the existing `browser_apply._storage_state()` parser and the
project's pinned Playwright dependency. It checks whether the session is still
valid and lists the existing resume titles. It does not print cookies, edit a
resume, submit an application, or bypass CAPTCHA/2FA. If HH asks for a security
challenge or a fresh login, the run stops and reports that status; refresh the
secret locally and retry.

## Important limitations

- GitHub Actions provides an ephemeral runner. Browser profile files do not
  persist between runs; the Actions secret is the durable input.
- HH may expire or revoke sessions, so re-authentication can be needed.
- This stage does not yet use a generative model and does not edit resume fields.
  Editing safely requires the recruiter's guide and an explicit review/approval
  step. No paid model/API key is used in this first stage.
- The workflow is manual-only. Existing job search and application workflows
  are unchanged.
