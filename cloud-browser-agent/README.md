# Autonomous Browser Agent

This adds an LLM-guided Playwright agent to the existing Flask service. It can inspect a page, reason about the next step, navigate, click ordinary controls, fill ordinary fields, select options, and continue across pages.

## Run locally (recommended for persistent sessions)

Run the browser on the computer where you want its profile and cookies stored:

```bash
cd cloud-browser-agent
python -m venv .venv
# Activate the virtual environment, then:
pip install -r requirements.txt
python -m playwright install chromium
```

Set these environment variables before starting the app:

- `AGENT_ACCESS_TOKEN`: a long random token protecting the agent endpoints.
- `AGENT_API_KEY`: API key for your chosen OpenAI-compatible model endpoint.
- `AGENT_MODEL`: model name supported by that endpoint (default: `gpt-4.1-mini`).
- `AGENT_API_BASE`: API base URL (default: `https://api.openai.com/v1`).
- `AGENT_PROFILE_DIR`: directory for the persistent Chromium profile (default: `./agent-profile`).
- `AGENT_HEADLESS`: `true` by default; set to `false` when a desktop display is available.

Then start the app:

```bash
python app.py
```

Open `http://127.0.0.1:10000/agent`. The browser profile is kept in `AGENT_PROFILE_DIR`, so cookies and localStorage can survive restarts as long as that directory remains intact. Back it up securely; it contains account access data.

For a local Ollama server that exposes the OpenAI-compatible API, set `AGENT_API_BASE` to `http://127.0.0.1:11434/v1`, `AGENT_API_KEY` to a non-empty placeholder accepted by your local setup (for example `ollama`), and `AGENT_MODEL` to an installed tool-capable model. Model quality and tool-following vary.

## Safety and current limits

- The page content is treated as untrusted input; it cannot override the user's task or agent rules.
- Password, one-time-code, recovery-code, payment and card fields are not filled by the agent. Complete those steps yourself.
- CAPTCHA and identity checks require human participation.
- Buttons that appear to submit, apply, send, pay, delete, register, or confirm are paused for explicit confirmation.
- Do not put passwords, API keys, or private account data in the task description.
- The configured model provider receives the task and a text snapshot of the current page. Do not use this with pages containing information you do not want to send to that provider.
- This is a controlled browser agent, not a guarantee that every website or workflow can be automated. Sites may block automation or change their layout.

## Deployment notes

A cloud deployment needs `AGENT_ACCESS_TOKEN`, `AGENT_API_KEY`, and the model settings as private environment variables. The browser profile must live on persistent storage if sessions are expected to survive restarts. Ephemeral free-tier filesystems do not guarantee that. For the most private and reliable session storage, run the agent locally.

The existing job-search worker and application logic are not changed by this module. It does not send job applications automatically.
