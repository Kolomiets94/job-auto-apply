/* WebMCP tools for Cloud Job Assistant.
 * Experimental browser API: tools are exposed only when the browser supports
 * document.modelContext and the page is served from a secure context (HTTPS/localhost).
 * These tools never submit applications or authenticate to third-party sites.
 */
(() => {
  const context = document.modelContext;
  const status = document.getElementById("webmcp-status");
  const toolNames = [
    "get_candidate_profile",
    "list_application_tasks",
    "prepare_application_brief"
  ];

  // A visible diagnostic panel helps verify the integration without DevTools.
  let panel = document.getElementById("webmcp-diagnostics");
  if (!panel && status) {
    panel = document.createElement("section");
    panel.id = "webmcp-diagnostics";
    panel.style.cssText = "margin-top:12px;padding:14px;border:1px solid #d9e1ef;border-radius:10px;background:#f8faff;color:#182033";
    const heading = document.createElement("strong");
    heading.textContent = "Проверка WebMCP";
    const details = document.createElement("p");
    details.id = "webmcp-diagnostic-detail";
    details.className = "muted";
    details.style.marginBottom = "8px";
    const list = document.createElement("ul");
    list.id = "webmcp-tool-list";
    list.style.cssText = "margin:8px 0 0;padding-left:20px;font-size:13px";
    const security = document.createElement("p");
    security.className = "muted";
    security.style.cssText = "margin:10px 0 0;padding:10px;border-radius:8px;background:#fff6df;color:#654b00";
    security.textContent = "Доступ к API /api/profile и /api/tasks защищён паролем приложения и сессионной cookie. Не передавайте пароль другим пользователям; используйте HTTPS.";
    const help = document.createElement("details");
    help.style.marginTop = "10px";
    const summary = document.createElement("summary");
    summary.textContent = "Как проверить на компьютере";
    const instructions = document.createElement("p");
    instructions.className = "muted";
    instructions.textContent = "Откройте эту страницу в актуальном Chrome/Chrome Canary на компьютере. Если WebMCP API недоступен, откройте chrome://flags/#enable-webmcp-testing, включите WebMCP Testing (если такой флаг доступен), перезапустите браузер и обновите страницу. После регистрации проверьте список инструментов браузерного агента отдельно. На телефонах поддержка может отсутствовать.";
    help.append(summary, instructions);
    panel.append(heading, details, list, security, help);
    status.insertAdjacentElement("afterend", panel);
  }

  const detail = panel?.querySelector("#webmcp-diagnostic-detail");
  const list = panel?.querySelector("#webmcp-tool-list");
  const setStatus = (message, state) => {
    if (status) status.textContent = message;
    if (detail) detail.textContent = message;
    if (panel) {
      panel.dataset.state = state;
      panel.style.borderColor = state === "ready" ? "#16a34a" : state === "error" ? "#dc2626" : state === "warning" ? "#d97706" : "#d9e1ef";
    }
  };

  if (!context || typeof context.registerTool !== "function") {
    setStatus("WebMCP недоступен в этом браузере. Обычный интерфейс продолжает работать.", "unavailable");
    if (list) list.textContent = "Инструменты пока не зарегистрированы в этом браузере.";
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

  setStatus("WebMCP API обнаружен. Регистрирую 3 инструмента…", "pending");
  if (list) {
    list.replaceChildren(...toolNames.map(name => {
      const item = document.createElement("li");
      item.textContent = name;
      return item;
    }));
  }

  const registration = Promise.all(tools.map(tool => context.registerTool(tool)));
  // This method is part of the WebMCP API: consumers should wait for async registration.
  if (typeof context.waitForToolsUntil === "function") {
    context.waitForToolsUntil(registration);
  }

  registration.then(async () => {
      document.documentElement.dataset.webmcp = "registered";

      // getTools() verifies this document's registered tool list, not external-agent discovery.
      if (typeof context.getTools !== "function") {
        setStatus("Вызовы регистрации всех 3 инструментов завершились. getTools() недоступен; обнаружение агентом нужно проверить отдельно.", "warning");
        return;
      }

      try {
        const registeredTools = await context.getTools();
        const registeredNames = new Set(registeredTools.map(tool => tool.name));
        const missing = toolNames.filter(name => !registeredNames.has(name));
        if (missing.length) {
          setStatus("Регистрация вызвана, но getTools() не подтвердил инструменты: " + missing.join(", "), "error");
          if (list) list.textContent = "Не подтверждены: " + missing.join(", ");
          document.documentElement.dataset.webmcp = "error";
          return;
        }
        setStatus("Регистрация успешна: getTools() подтвердил все 3 инструмента в этой странице. Обнаружение внешним браузерным агентом проверяется отдельно.", "ready");
      } catch (error) {
        setStatus("Вызовы регистрации завершились, но проверка getTools() не удалась: " + String(error), "warning");
        document.documentElement.dataset.webmcp = "registered-unverified";
      }
    })
    .catch(error => {
      setStatus("Ошибка регистрации WebMCP: " + String(error), "error");
      if (list) list.textContent = "Не удалось зарегистрировать инструменты.";
      document.documentElement.dataset.webmcp = "error";
      console.error("WebMCP registration failed", error);
    });
})();
