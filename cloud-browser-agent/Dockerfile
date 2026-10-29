FROM mcr.microsoft.com/playwright/python:v1.55.0-noble
WORKDIR /app
COPY cloud-browser-agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY cloud-browser-agent/ ./
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-10000}"]
