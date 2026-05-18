(function () {
  const boot = window.emergyxDetailsBoot || {};
  const mode = boot.mode || "demo";
  const toolResult = document.getElementById("tool-result-output");
  const agentResult = document.getElementById("agent-result-output");
  const debugOutput = document.getElementById("debug-output");
  const simulateButton = document.getElementById("simulate-fall-button");
  const telegramButton = document.getElementById("test-telegram-button");
  const explainButton = document.getElementById("explain-latest-button");
  const reportButton = document.getElementById("generate-report-button");

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function formatParagraphs(value) {
    const text = escapeHtml(value || "");
    return text
      .split(/\n{2,}/)
      .map((paragraph) => `<p>${paragraph.replaceAll("\n", "<br />")}</p>`)
      .join("");
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `Request failed (${response.status})`);
    }
    return response.json();
  }

  function writeActionResult(title, detail, rawPayload) {
    if (toolResult) {
      toolResult.innerHTML = `<p><strong>${escapeHtml(title)}</strong></p><p>${escapeHtml(detail)}</p>`;
    }
    if (debugOutput) {
      debugOutput.textContent =
        typeof rawPayload === "string" ? rawPayload : JSON.stringify(rawPayload, null, 2);
    }
  }

  function writeAgentResult(text, rawPayload) {
    if (agentResult) {
      agentResult.innerHTML = formatParagraphs(text);
    }
    if (debugOutput) {
      debugOutput.textContent =
        typeof rawPayload === "string" ? rawPayload : JSON.stringify(rawPayload, null, 2);
    }
  }

  async function runAction(actionTitle, url, options, onSuccess) {
    try {
      const payload = await fetchJson(url, options);
      onSuccess(payload);
    } catch (error) {
      writeActionResult(actionTitle, error.message || "Action failed.", error.message || "Action failed.");
    }
  }

  if (simulateButton) {
    simulateButton.addEventListener("click", async () => {
      await runAction(
        "Simulated fall created",
        "/events/simulate-fall",
        { method: "POST", body: JSON.stringify({}) },
        (payload) =>
          writeActionResult(
            "Simulated fall created",
            "A demo likely-fall event was added to the local care timeline.",
            payload
          )
      );
    });
  }

  if (telegramButton) {
    telegramButton.addEventListener("click", async () => {
      await runAction(
        "Telegram test",
        "/alerts/test-telegram",
        { method: "POST" },
        (payload) =>
          writeActionResult("Telegram test", payload.message || "Telegram test completed.", payload)
      );
    });
  }

  if (explainButton) {
    explainButton.addEventListener("click", async () => {
      await runAction(
        "Caregiver explanation",
        `/agent/explain-latest?mode=${encodeURIComponent(mode)}`,
        { method: "POST" },
        (payload) => writeAgentResult(payload.explanation || "No explanation returned.", payload)
      );
    });
  }

  if (reportButton) {
    reportButton.addEventListener("click", async () => {
      await runAction(
        "Daily report",
        `/reports/daily?mode=${encodeURIComponent(mode)}`,
        { method: "POST" },
        (payload) => writeAgentResult(payload.report || "No report returned.", payload)
      );
    });
  }
})();
