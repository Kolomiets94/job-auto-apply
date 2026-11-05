import os
import urllib.request

url = "https://job-auto-apply-5wmf.onrender.com/run/scheduled"
token = os.environ["SCHEDULER_TOKEN"]
request = urllib.request.Request(
    url,
    data=b"",
    headers={"Authorization": f"Bearer {token}"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=90) as response:
    print(response.read().decode("utf-8", errors="replace"))
