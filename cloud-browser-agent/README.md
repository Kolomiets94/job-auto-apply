# Cloud Job Assistant

A small web app to organize job application URLs and prepare honest, profile-based draft text. It does **not** automatically submit applications or log in to third-party sites.

## Deploy on Render

Create a free Python web service connected to this repository:
- Build command: `pip install -r cloud-browser-agent/requirements.txt`
- Start command: `cd cloud-browser-agent && gunicorn app:app --bind 0.0.0.0:$PORT`
- Health check path: `/health`
- Plan: Free

Set optional environment variables `CANDIDATE_NAME` and `CANDIDATE_EMAIL` if you want to override the defaults.

## Notes
- This prototype stores tasks in memory, so task history resets when the service restarts or sleeps.
- Do not enter passwords, one-time codes, or sensitive personal documents.
- Always review each draft and submit applications manually.
- This is an application-preparation dashboard, not yet an autonomous cloud browser agent. A remote browser provider and its credentials would be needed for actual website interaction.
