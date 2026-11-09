# HeadHunter resume review (read-only)

Run **Actions → HeadHunter Resume Agent → Run workflow**. The agent opens the
existing resume pages and extracts their visible text into a JSON report.
Optionally provide an HTTPS hh.ru/vacancy/... URL in the **Target vacancy URL**
field to compare the resume with one vacancy and prepare a conservative draft.

## One-time setup for a downloadable report

The repository is public, so the report is encrypted before upload. In
**Settings → Secrets and variables → Actions**, add a strong random secret
named **HH_REPORT_ENCRYPTION_KEY**. Keep the key private and do not commit it.
Without this secret, the workflow will still report safe counts but will not
upload resume contents. The encrypted artifact is retained for 7 days.

After downloading hh-resume-review-encrypted, decrypt it locally with OpenSSL:

    openssl enc -d -aes-256-cbc -pbkdf2 -in hh-resume-result.json.enc -out hh-resume-result.json -pass env:HH_REPORT_ENCRYPTION_KEY

Set HH_REPORT_ENCRYPTION_KEY in your local shell to the same value before
running the command. Treat the decrypted JSON as confidential personal data.

Recommendations are deterministic checklist prompts, not claims about
candidate qualifications. Keyword matches are not proof of experience. Review
all suggestions and drafts manually before using them.

Safety:
- Read-only browser navigation; no resume edits or saves.
- No application or response submission.
- No CAPTCHA/2FA bypass.
- Session remains in the HH_STORAGE_STATE_JSON Actions secret and is never
  written to the report.
- Plaintext resume text is never uploaded or printed to Actions logs.
- Existing Auto Apply workflows and business logic are unchanged.
