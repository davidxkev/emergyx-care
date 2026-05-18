(function () {
  const boot = window.emergyxDashboardBoot || {};
  const state = {
    mode: boot.mode || "demo",
    threads: Array.isArray(boot.threads) ? boot.threads : [],
    activeThread: boot.activeThread || null,
    activeThreadId:
      boot.activeThread && boot.activeThread.thread ? boot.activeThread.thread.id : null,
    quickPrompts: Array.isArray(boot.quickPrompts) ? boot.quickPrompts : [],
    pending: false,
  };

  const historyButtons = Array.from(document.querySelectorAll("[data-open-history]"));
  const newThreadButtons = Array.from(document.querySelectorAll("[data-new-thread]"));
  const explainButtons = Array.from(document.querySelectorAll("[data-explain-latest]"));
  const reportButtons = Array.from(document.querySelectorAll("[data-generate-report]"));
  const historyDrawer = document.getElementById("history-drawer");
  const historyBackdrop = document.getElementById("history-drawer-backdrop");
  const historyClose = document.getElementById("history-close");
  const threadList = document.getElementById("thread-list");
  const messages = document.getElementById("assistant-messages");
  const quickPrompts = document.getElementById("quick-prompts");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const sendButton = document.getElementById("send-button");
  const explainOutput = document.getElementById("explain-output");
  const reportOutput = document.getElementById("report-output");
  const reportEmpty = document.getElementById("report-empty");
  const simulateButton = document.getElementById("simulate-fall-button");

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

  function sourceChipClasses(source) {
    if (source === "live_sensor") return "table-pill table-pill--success";
    if (source === "simulated" || source === "simulated_seed") return "table-pill table-pill--warning";
    return "table-pill table-pill--neutral";
  }

  function sourceLabel(source) {
    if (source === "live_sensor") return "Live sensor";
    if (source === "simulated") return "Demo run";
    if (source === "simulated_seed") return "Demo baseline";
    if (source === "manual") return "Manual";
    return state.mode === "live" ? "Live sensor" : "Demo run";
  }

  function evidenceLabel(kind) {
    const labels = {
      incident: "Incident",
      alert: "Alert",
      event: "Event",
      report: "Report",
      light: "Light context",
      summary: "Timeline summary",
    };
    return labels[kind] || "Context";
  }

  function setDrawerOpen(isOpen) {
    if (!historyDrawer || !historyBackdrop) return;
    if (isOpen) {
      historyBackdrop.hidden = false;
      historyDrawer.removeAttribute("aria-hidden");
      requestAnimationFrame(() => historyDrawer.classList.add("is-open"));
      return;
    }
    historyDrawer.classList.remove("is-open");
    historyDrawer.setAttribute("aria-hidden", "true");
    window.setTimeout(() => {
      historyBackdrop.hidden = true;
    }, 220);
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

  function renderThreadList() {
    if (!threadList) return;
    if (!state.threads.length) {
      threadList.innerHTML = `
        <div class="thread-empty">
          <p><strong>No saved conversations yet.</strong></p>
          <p>Start a caregiver chat to create local history for this mode.</p>
        </div>
      `;
      return;
    }

    threadList.innerHTML = state.threads
      .map((thread) => {
        const isActive = state.activeThreadId === thread.id;
        return `
          <button type="button" data-thread-id="${thread.id}" class="thread-card ${
            isActive ? "is-active" : ""
          }">
            <span class="thread-card__title">${escapeHtml(thread.title)}</span>
            <span class="thread-card__time">${escapeHtml(thread.updated_at || "")}</span>
          </button>
        `;
      })
      .join("");

    threadList.querySelectorAll("[data-thread-id]").forEach((button) => {
      button.addEventListener("click", async () => {
        await loadThread(Number(button.dataset.threadId));
        setDrawerOpen(false);
      });
    });
  }

  function renderEvidence(metadata) {
    const evidence = metadata && Array.isArray(metadata.evidence) ? metadata.evidence : [];
    if (!evidence.length) return "";

    return `
      <details class="emergyx-evidence">
        <summary class="message-tag">Used local context</summary>
        <div class="evidence-list">
          ${evidence
            .map((item) => {
              const source =
                item.metadata && item.metadata.source
                  ? item.metadata.source
                  : state.mode === "live"
                    ? "live_sensor"
                    : "simulated";
              return `
                <article class="evidence-card">
                  <div class="evidence-card__meta">
                    <span class="${sourceChipClasses(source)}">${sourceLabel(source)}</span>
                    <span class="table-pill table-pill--neutral">${escapeHtml(
                      evidenceLabel(item.kind)
                    )}</span>
                  </div>
                  <h5 class="evidence-card__title">${escapeHtml(item.label || evidenceLabel(item.kind))}</h5>
                  <p class="evidence-card__text">${escapeHtml(item.text || "")}</p>
                  <span class="evidence-card__time">${escapeHtml(item.timestamp || "")}</span>
                </article>
              `;
            })
            .join("")}
        </div>
      </details>
    `;
  }

  function renderQuickPrompts() {
    if (!quickPrompts) return;
    quickPrompts.innerHTML = state.quickPrompts
      .map(
        (prompt) =>
          `<button type="button" class="prompt-chip">${escapeHtml(prompt)}</button>`
      )
      .join("");

    quickPrompts.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", async () => {
        const prompt = button.textContent || "";
        if (prompt.toLowerCase().includes("generate") && prompt.toLowerCase().includes("report")) {
          await generateReport();
          return;
        }
        if (chatInput) {
          chatInput.value = prompt;
          chatInput.focus();
        }
      });
    });
  }

  function renderMessages() {
    if (!messages) return;
    const active = state.activeThread;
    if (!active || !Array.isArray(active.messages) || !active.messages.length) {
      messages.innerHTML = `
        <div class="chat-empty">
          <p class="eyebrow">${state.mode === "live" ? "Live mode" : "Demo mode"}</p>
          <h3>Ask about today’s events, alerts, or safety patterns.</h3>
          <p>Emergyx Care combines a local care timeline, rule-based urgent alerts, and a local Gemma agent for caregiver explanations and reports.</p>
        </div>
      `;
      renderQuickPrompts();
      return;
    }

    messages.innerHTML = active.messages
      .map((message) => {
        const isUser = message.role === "user";
        const metadata = message.metadata || {};
        const chips = [];
        if (!isUser && message.model_name) {
          chips.push(`<span class="message-tag">${escapeHtml(message.model_name)}</span>`);
        }
        if (!isUser && message.used_mock) {
          chips.push('<span class="message-tag">Fallback</span>');
        }
        if (message.created_at) {
          chips.push(`<span class="message-tag">${escapeHtml(message.created_at)}</span>`);
        }

        return `
          <div class="message-row ${isUser ? "message-row--user" : "message-row--assistant"}">
            <div class="message-card">
              <div class="message-body">${formatParagraphs(message.content)}</div>
              <div class="message-meta">${chips.join("")}</div>
              ${!isUser ? renderEvidence(metadata) : ""}
            </div>
          </div>
        `;
      })
      .join("");

    renderQuickPrompts();
    messages.scrollTop = messages.scrollHeight;
  }

  function setReportContent(text) {
    if (!reportOutput || !reportEmpty) return;
    if (text && text.trim()) {
      reportOutput.innerHTML = formatParagraphs(text);
      reportEmpty.hidden = true;
      return;
    }
    reportOutput.innerHTML = "";
    reportEmpty.hidden = false;
  }

  async function refreshThreads() {
    const payload = await fetchJson(`/chat/threads?mode=${encodeURIComponent(state.mode)}`);
    state.threads = payload.threads || [];
    renderThreadList();
  }

  async function createThread() {
    const payload = await fetchJson(`/chat/threads?mode=${encodeURIComponent(state.mode)}`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    state.activeThread = { thread: payload.thread, messages: [] };
    state.activeThreadId = payload.thread.id;
    await refreshThreads();
    renderMessages();
    window.history.replaceState(
      {},
      "",
      `/dashboard?mode=${encodeURIComponent(state.mode)}&thread_id=${payload.thread.id}`
    );
  }

  async function loadThread(threadId) {
    const detail = await fetchJson(`/chat/threads/${threadId}?mode=${encodeURIComponent(state.mode)}`);
    state.activeThread = detail;
    state.activeThreadId = detail.thread.id;
    renderThreadList();
    renderMessages();
    window.history.replaceState(
      {},
      "",
      `/dashboard?mode=${encodeURIComponent(state.mode)}&thread_id=${threadId}`
    );
  }

  function appendPendingMessage(content) {
    if (!state.activeThread) {
      state.activeThread = {
        thread: { id: state.activeThreadId, title: "Caregiver assistant" },
        messages: [],
      };
    }

    state.activeThread.messages = [
      ...(state.activeThread.messages || []),
      {
        id: `tmp-user-${Date.now()}`,
        role: "user",
        content,
        created_at: "Sending…",
        metadata: null,
      },
      {
        id: `tmp-assistant-${Date.now()}`,
        role: "assistant",
        content: "Reviewing the local care timeline and preparing a caregiver explanation.",
        created_at: "",
        used_mock: false,
        metadata: null,
      },
    ];
    renderMessages();
  }

  async function sendMessage(content) {
    if (state.pending || !content) return;
    state.pending = true;
    if (sendButton) sendButton.disabled = true;
    if (chatInput) chatInput.disabled = true;

    try {
      if (!state.activeThreadId) {
        await createThread();
      }
      appendPendingMessage(content);
      const detail = await fetchJson(
        `/chat/threads/${state.activeThreadId}/messages?mode=${encodeURIComponent(state.mode)}`,
        {
          method: "POST",
          body: JSON.stringify({ content }),
        }
      );
      state.activeThread = detail;
      state.activeThreadId = detail.thread.id;
      await refreshThreads();
      renderMessages();
      window.history.replaceState(
        {},
        "",
        `/dashboard?mode=${encodeURIComponent(state.mode)}&thread_id=${detail.thread.id}`
      );
    } catch (error) {
      window.alert(error.message || "The caregiver assistant could not answer right now.");
    } finally {
      state.pending = false;
      if (sendButton) sendButton.disabled = false;
      if (chatInput) {
        chatInput.disabled = false;
        chatInput.focus();
      }
    }
  }

  async function explainLatest() {
    if (!explainOutput) return;
    explainOutput.innerHTML = "<p>Generating a caregiver explanation from the local incident context…</p>";
    try {
      const payload = await fetchJson(`/agent/explain-latest?mode=${encodeURIComponent(state.mode)}`, {
        method: "POST",
      });
      explainOutput.innerHTML = formatParagraphs(payload.explanation || "");
    } catch (error) {
      explainOutput.innerHTML = `<p>${escapeHtml(error.message || "Explanation unavailable.")}</p>`;
    }
  }

  async function generateReport() {
    reportButtons.forEach((button) => {
      button.disabled = true;
    });
    try {
      const payload = await fetchJson(`/reports/daily?mode=${encodeURIComponent(state.mode)}`, {
        method: "POST",
      });
      setReportContent(payload.report || "");
    } catch (error) {
      setReportContent(error.message || "Report unavailable.");
    } finally {
      reportButtons.forEach((button) => {
        button.disabled = false;
      });
    }
  }

  async function simulateFall() {
    if (!simulateButton) return;
    simulateButton.disabled = true;
    try {
      await fetchJson("/events/simulate-fall", {
        method: "POST",
        body: JSON.stringify({}),
      });
      window.location.reload();
    } catch (error) {
      window.alert(error.message || "Simulated fall failed.");
      simulateButton.disabled = false;
    }
  }

  historyButtons.forEach((button) => button.addEventListener("click", () => setDrawerOpen(true)));
  newThreadButtons.forEach((button) =>
    button.addEventListener("click", () => {
      state.activeThread = null;
      state.activeThreadId = null;
      renderThreadList();
      renderMessages();
      window.history.replaceState({}, "", `/dashboard?mode=${encodeURIComponent(state.mode)}`);
      if (chatInput) chatInput.focus();
    })
  );
  explainButtons.forEach((button) => button.addEventListener("click", explainLatest));
  reportButtons.forEach((button) => button.addEventListener("click", generateReport));

  if (historyBackdrop) historyBackdrop.addEventListener("click", () => setDrawerOpen(false));
  if (historyClose) historyClose.addEventListener("click", () => setDrawerOpen(false));
  if (simulateButton) simulateButton.addEventListener("click", simulateFall);

  if (chatForm) {
    chatForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!chatInput) return;
      const content = chatInput.value.trim();
      if (!content) return;
      chatInput.value = "";
      await sendMessage(content);
    });
  }

  if (chatInput) {
    chatInput.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        if (chatForm) chatForm.requestSubmit();
      }
    });
  }

  renderThreadList();
  renderMessages();
})();
