/* WebMCP tools for Cloud Job Assistant.
 * Experimental browser API: tools are exposed only when the browser supports
 * document.modelContext and the page is served from a secure context (HTTPS/localhost).
 * These tools never submit applications or authenticate to third-party sites.
 */
(() => {
  const context = document.modelContext;
  const status = document.getElementById("webmcp-status");
  if (!context || typeof context.registerTool !== "function") {
    if (status) status.textContent = "WebMCP недоступен в этом браузере. Обычный интерфейс продолжает работать.";
    return;
  }

  const json = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: { "Accept": "application/json", ...(options.headers || {}) }
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) return { error: data.error || `HTTP ${response.status}` };
    return data;
  };

  const tools = [
    {
      name: "get_candidate_profile",
      description: "Returns the candidate profile configured in JobAutoApply, including confirmed skills, experience statement and portfolio link. Use this before drafting an application; do not infer unlisted skills.",
      inputSchema: { type: "object", properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: true },
      execute: async (_input, { signal } = {}) => {
        try {
          return await json("/api/profile", { signal });
        } catch (error) {
          return { error: "Could not load candidate profile.", details: String(error) };
        }
      }
    },
    {
      name: "list_application_tasks",
      description: "Lists application briefs currently held by the JobAutoApply web service. These are preparation records, not submitted applications. The prototype stores them in memory and they may reset after a restart.",
      inputSchema: { type: "object", properties: {}, additionalProperties: false },
      annotations: { readOnlyHint: true },
      execute: async (_input, { signal } = {}) => {
        try {
          return await json("/api/tasks", { signal });
        } catch (error) {
          return { error: "Could not load application tasks.", details: String(error) };
        }
      }
    },
    {
      name: "prepare_application_brief",
      description: "Creates a draft application brief for a public job-posting URL. This only saves a preparation task in JobAutoApply; it does not log in, contact an employer, or submit an application. Never include passwords, one-time codes, or sensitive personal data.",
      inputSchema: {
        type: "object",
        properties: {
          url: { type: "string", format: "uri", description: "Public job posting URL (http or https)." },
          role: { type: "string", maxLength: 180, description: "Target role title." },
          company: { type: "string", maxLength: 180, description: "Company name, if known." },
          notes: { type: "string", maxLength: 1200, description: "Relevant requirements copied from the public job post; do not include secrets or sensitive personal data." }
        },
        required: ["url"],
        additionalProperties: false
      },
      annotations: { readOnlyHint: false, destructiveHint: false },
      execute: async (input, { signal } = {}) => {
        const url = String(input?.url || "").trim();
        let parsed;
        try { parsed = new URL(url); } catch { return { error: "Provide a valid public job URL." }; }
        if (!["http:", "https:"].includes(parsed.protocol) || !parsed.hostname) {
          return { error: "Only http and https job URLs are accepted." };
        }
        try {
          return await json("/api/tasks", {
            method: "POST",
            signal,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              url,
              role: String(input.role || "Junior Frontend Developer").slice(0, 180),
              company: String(input.company || "").slice(0, 180),
              notes: String(input.notes || "").slice(0, 1200)
            })
          });
        } catch (error) {
          return { error: "Could not prepare the application brief.", details: String(error) };
        }
      }
    }
  ];

  Promise.all(tools.map(tool => context.registerTool(tool)))
    .then(() => {
      if (status) status.textContent = "WebMCP активен: зарегистрировано 3 инструмента.";
      document.documentElement.dataset.webmcp = "ready";
    })
    .catch(error => {
      if (status) status.textContent = "Не удалось зарегистрировать WebMCP-инструменты: " + String(error);
      console.error("WebMCP registration failed", error);
    });
})();
