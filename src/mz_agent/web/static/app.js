/* ===== MzAgent 控制台 — app.js ===== */
/* 入口：初始化 + API 封装 + 事件绑定 + 组件渲染 */

const sessionId = document.body.dataset.sessionId;

/* ---------- DOM 引用 ---------- */
const $ = (id) => document.getElementById(id);

const el = {
  /* 侧边栏 */
  sidebar: $("sidebar"),
  sidebarBackdrop: $("sidebar-backdrop"),
  btnSidebarToggle: $("btn-sidebar-toggle"),
  btnNewChat: $("btn-new-chat"),
  sidebarSessionLabel: $("sidebar-session-label"),
  btnOpenSettings: $("btn-open-settings"),

  /* 侧边栏 — 能力导航 */
  btnOpenTools: $("btn-open-tools"),
  btnOpenMcp: $("btn-open-mcp"),
  btnOpenSkills: $("btn-open-skills"),
  toolsBadge: $("tools-badge"),
  mcpBadge: $("mcp-badge"),
  skillsBadge: $("skills-badge"),

  /* 顶栏 */
  profileSelectorWrap: $("profile-selector-wrap"),
  profileSelector: $("profile-selector"),
  statusDot: $("status-dot"),
  sessionId: $("session-id"),
  refreshStatus: $("refresh-status"),
  copySession: $("copy-session"),
  resetSession: $("reset-session"),

  /* 对话流 */
  chatScroll: $("chat-scroll"),
  chatFlow: $("chat-flow"),
  chatEmpty: $("chat-empty"),
  thinkingIndicator: $("thinking-indicator"),

  /* 输入区 */
  roundForm: $("round-form"),
  goal: $("goal"),
  capToggles: $("capability-toggles"),
  ragToggle: $("rag-toggle"),
  submitButton: $("submit-button"),
  goalError: $("goal-error"),

  /* 设置抽屉 */
  settingsOverlay: $("settings-overlay"),
  settingsDrawer: $("settings-drawer"),
  btnCloseSettings: $("btn-close-settings"),
  profileForm: $("profile-form"),
  profileSelectorDrawer: $("profile-selector-drawer"),
  profileBaseUrl: $("profile-base-url"),
  profileApiKey: $("profile-api-key"),
  profileKeyHint: $("profile-key-hint"),
  saveConnection: $("save-connection"),
  discoverModels: $("discover-models"),
  discoveredModelSection: $("discovered-model-section"),
  discoveredModelSelector: $("discovered-model-selector"),
  profileApiMode: $("profile-api-mode"),
  addModel: $("add-model"),
  activeModelSection: $("active-model-section"),
  activeProfileModeHint: $("active-profile-mode-hint"),
  activateProfile: $("activate-profile"),
  testProfile: $("test-profile"),
  deleteProfile: $("delete-profile"),
  connectionResult: $("connection-result"),
  profileTestResult: $("profile-test-result"),
  settingsEmptyState: $("settings-empty-state"),

  /* TOOLS 管理抽屉 */
  toolsOverlay: $("tools-overlay"),
  toolsDrawer: $("tools-drawer"),
  btnCloseTools: $("btn-close-tools"),
  toolsMasterToggle: $("tools-master-toggle"),
  toolsCount: $("tools-count"),
  toolsList: $("tools-list"),
  toolsAddToggle: $("tools-add-toggle"),
  toolsAddForm: $("tools-add-form"),

  /* MCP 管理抽屉 */
  mcpOverlay: $("mcp-overlay"),
  mcpDrawer: $("mcp-drawer"),
  btnCloseMcp: $("btn-close-mcp"),
  mcpMasterToggle: $("mcp-master-toggle"),
  mcpCount: $("mcp-count"),
  mcpList: $("mcp-list"),
  mcpAddToggle: $("mcp-add-toggle"),
  mcpAddForm: $("mcp-add-form"),

  /* SKILLS 管理抽屉 */
  skillsOverlay: $("skills-overlay"),
  skillsDrawer: $("skills-drawer"),
  btnCloseSkills: $("btn-close-skills"),
  skillsMasterToggle: $("skills-master-toggle"),
  skillsCount: $("skills-count"),
  skillsList: $("skills-list"),
  skillsAddToggle: $("skills-add-toggle"),
  skillsAddForm: $("skills-add-form"),

  /* Toast */
  toastContainer: $("toast-container"),
};

/* ---------- 状态 ---------- */
const roleLabels = { assistant: "MzAgent", user: "你", system: "系统", tool: "TOOLS", mcp: "MCP" };
const roleAvatarText = { assistant: "M", user: "你", system: "S", tool: "T", mcp: "M" };

let profileState = {
  activeProfileName: null,
  profiles: [],
  connection: null,
  discoveredModels: [],
};
let isLoading = false;
let activeAgentStream = null;
let markdownReady = false;

const markdownRoles = new Set(["assistant", "user"]);
const apiModeLabels = {
  "openai-responses": "OpenAI Responses · /v1/responses",
  "openai-completions": "OpenAI Chat · /v1/chat/completions",
  "anthropic-messages": "Anthropic Messages · /v1/messages",
};
const apiModeShortLabels = {
  "openai-responses": "Responses",
  "openai-completions": "Chat",
  "anthropic-messages": "Messages",
};

/* ---------- 能力注册表状态 ---------- */
/* TOOLS / MCP / SKILLS 各自维护一份 {items: [], masterEnabled: true} */
let capState = {
  tool:  { items: [], masterEnabled: true },
  mcp:   { items: [], masterEnabled: true },
  skill: { items: [], masterEnabled: true },
};

/* ---------- 收集当前启用的能力 ---------- */
function getEnabledCapabilities() {
  const caps = [];
  /* TOOLS / MCP / SKILLS：主开关 ON + 子项 enabled */
  for (const [type, state] of Object.entries(capState)) {
    if (!state.masterEnabled) continue;
    const enabledItems = state.items.filter((it) => it.enabled);
    if (enabledItems.length > 0) {
      caps.push(type);
    }
  }
  /* RAG 开关 */
  if (el.ragToggle.checked) caps.push("rag");
  return caps;
}

/* 根据开关推断 action_type：有开关开启则 agent 自主决定，否则纯 llm */
function resolveActionType() {
  const caps = getEnabledCapabilities();
  if (caps.length === 0) return "llm";
  /* 有能力开关开启时，由后端 agent 根据 enabled_capabilities 自行编排 */
  return "auto";
}

/* ---------- API 封装 ---------- */
async function api(path, options = {}) {
  const resp = await fetch(path, options);
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.message || "请求失败");
  return data;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeCodeLanguage(language) {
  const normalized = String(language || "").trim().toLowerCase();
  if (!normalized) return "plaintext";
  return normalized.replace(/[^a-z0-9_+-]/g, "") || "plaintext";
}

function safeParseJson(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function configureMarkdown() {
  if (markdownReady || !window.marked) return;

  const renderer = {
    link({ href, title, tokens }) {
      const text = this.parser.parseInline(tokens);
      const target = href || "#";
      const titleAttr = title ? ` title="${escapeHtml(title)}"` : "";
      return `<a href="${escapeHtml(target)}" target="_blank" rel="noopener noreferrer"${titleAttr}>${text}</a>`;
    },
    code({ text, lang }) {
      const language = normalizeCodeLanguage(lang);
      return `
        <div class="message-code-block">
          <button class="message-code-copy" type="button" aria-label="复制代码">复制</button>
          <pre><code class="language-${language}">${escapeHtml(text)}</code></pre>
        </div>
      `;
    },
  };

  window.marked.use({
    gfm: true,
    breaks: true,
    renderer,
  });

  markdownReady = true;
}

function closeAgentStream() {
  if (activeAgentStream) {
    activeAgentStream.close();
    activeAgentStream = null;
  }
}

async function loadSessionSnapshotFromStream() {
  if (typeof window.EventSource !== "function") {
    throw new Error("当前浏览器不支持事件流。");
  }

  closeAgentStream();

  return new Promise((resolve, reject) => {
    let settled = false;
    let latestStatus = null;
    let latestHistory = null;
    const source = new EventSource(`/api/agent/stream?session_id=${encodeURIComponent(sessionId)}`);
    activeAgentStream = source;

    const finish = (payload) => {
      if (settled) return;
      settled = true;
      closeAgentStream();
      resolve(payload);
    };

    const fail = (message) => {
      if (settled) return;
      settled = true;
      closeAgentStream();
      reject(new Error(message));
    };

    source.addEventListener("session_status", (event) => {
      const payload = safeParseJson(event.data);
      if (!payload) return;
      latestStatus = payload;
      updateStatusDot(payload.status_label);
    });

    source.addEventListener("session_history", (event) => {
      const payload = safeParseJson(event.data);
      if (!payload) return;
      latestHistory = payload;
      renderChatFlow(payload.history || []);
    });

    source.addEventListener("stream_end", () => {
      finish({ status: latestStatus, history: latestHistory });
    });

    source.onerror = () => {
      if (settled) return;
      fail("会话事件流连接失败。");
    };
  });
}

async function loadSessionSnapshot() {
  try {
    return await loadSessionSnapshotFromStream();
  } catch {
    const [status, history] = await Promise.all([
      api(`/api/session/${sessionId}/status`),
      api(`/api/session/${sessionId}/history`),
    ]);
    updateStatusDot(status.status_label);
    renderChatFlow(history.history || []);
    return { status, history };
  }
}

/* 预留：WebSocket 双向通信 */
// function connectWebSocket(sessionId, handlers) {
//   const ws = new WebSocket(`ws://${location.host}/ws/session/${sessionId}`);
//   ws.onmessage = (e) => handlers.onMessage(JSON.parse(e.data));
//   ws.onclose = () => handlers.onClose?.();
//   return ws;
// }

/* ---------- Toast 通知 ---------- */
function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  el.toastContainer.appendChild(toast);
  setTimeout(() => { toast.remove(); }, 3000);
}

/* ---------- 加载态 ---------- */
function setLoading(loading) {
  isLoading = loading;
  el.refreshStatus.disabled = loading;
  el.resetSession.disabled = loading;
  [el.saveConnection, el.discoverModels, el.addModel, el.activateProfile, el.testProfile, el.deleteProfile].forEach((button) => {
    if (button) button.disabled = loading;
  });
  el.thinkingIndicator.classList.toggle("hidden", !loading);
  syncSettingsState();
}

/* ---------- 状态点 ---------- */
function updateStatusDot(statusLabel) {
  el.statusDot.className = "status-dot";
  el.statusDot.title = statusLabel || "待输入";
  if (!statusLabel || statusLabel === "待输入") {
    el.statusDot.classList.add("idle");
  } else if (statusLabel.includes("处理") || statusLabel.includes("运行")) {
    el.statusDot.classList.add("processing");
  } else if (statusLabel.includes("错误") || statusLabel.includes("失败")) {
    el.statusDot.classList.add("error");
  }
}

/* ---------- 表单校验 ---------- */
function validateForm() {
  el.goalError.textContent = "";
  if (!profileState.activeProfileName) {
    el.goalError.textContent = "请先配置 NewAPI 连接并启用一个模型。";
    return false;
  }
  const goal = el.goal.value.trim();
  if (!goal) {
    el.goalError.textContent = "请先填写你想让我做什么。";
    return false;
  }
  return true;
}

function focusComposer() {
  el.goal.focus();
  const length = el.goal.value.length;
  el.goal.setSelectionRange(length, length);
}

async function writeClipboard(text, successMessage) {
  try {
    await navigator.clipboard.writeText(text);
    showToast(successMessage, "success");
    return true;
  } catch (err) {
    showToast(`复制失败：${err.message}`, "error");
    return false;
  }
}

function renderMessageMarkdown(messageEl, content) {
  const container = messageEl.querySelector(".message-content");
  if (!window.marked || !window.DOMPurify) {
    container.textContent = content || "";
    return;
  }

  configureMarkdown();
  const rawHtml = window.marked.parse(content || "");
  container.innerHTML = window.DOMPurify.sanitize(rawHtml, {
    ADD_ATTR: ["target", "rel", "class", "aria-label"],
  });

  container.querySelectorAll(".message-code-copy").forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", async () => {
      const code = button.parentElement?.querySelector("code")?.textContent || "";
      const copied = await writeClipboard(code, "代码已复制");
      if (!copied) return;
      const previous = button.textContent;
      button.textContent = "已复制";
      window.setTimeout(() => {
        button.textContent = previous;
      }, 1200);
    });
  });

  if (window.hljs) {
    container.querySelectorAll("pre code").forEach((node) => {
      window.hljs.highlightElement(node);
    });
  }
}

function renderMessagePlainText(messageEl, content) {
  messageEl.querySelector(".message-content").textContent = content || "";
}

function buildMessageActions(role, item) {
  const buttons = [
    `
      <button class="message-action-btn" type="button" data-action="copy">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
        <span>复制</span>
      </button>
    `,
  ];

  if (role === "assistant" && item.round_id) {
    buttons.push(`
      <button class="message-action-btn" type="button" data-action="retry">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
        <span>重试</span>
      </button>
    `);
  }

  if (role === "user") {
    buttons.push(`
      <button class="message-action-btn ghost" type="button" data-action="edit">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 013 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>
        <span>编辑</span>
      </button>
    `);
  }

  return `<div class="message-actions">${buttons.join("")}</div>`;
}

function bindMessageActions(messageEl, item) {
  const copyButton = messageEl.querySelector('[data-action="copy"]');
  if (copyButton) {
    copyButton.addEventListener("click", async () => {
      await writeClipboard(item.content || "", "消息已复制");
    });
  }

  const retryButton = messageEl.querySelector('[data-action="retry"]');
  if (retryButton) {
    retryButton.addEventListener("click", async () => {
      setLoading(true);
      try {
        const payload = await api(`/api/session/${sessionId}/rounds/${encodeURIComponent(item.round_id)}/retry`, {
          method: "POST",
        });
        updateStatusDot(payload.status?.status_label);
        renderChatFlow(payload.history || []);
        showToast("已重新执行该轮次", "success");
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        setLoading(false);
      }
    });
  }

  const editButton = messageEl.querySelector('[data-action="edit"]');
  if (editButton) {
    editButton.addEventListener("click", () => {
      el.goal.value = item.content || "";
      autoResizeTextarea();
      focusComposer();
      showToast("已回填到输入框，可修改后重新发送", "success");
    });
  }
}

/* ---------- 对话流渲染 ---------- */
function createMessageEl(item, index) {
  const role = item.role || "unknown";
  const div = document.createElement("div");
  div.className = "message";
  div.dataset.role = role;
  if (item.round_id) {
    div.dataset.roundId = item.round_id;
  }

  div.innerHTML = `
    <div class="message-avatar">${roleAvatarText[role] || "?"}</div>
    <div class="message-body">
      <div class="message-header">
        <span class="message-role">${roleLabels[role] || role}</span>
        <span class="message-index">#${index + 1}</span>
      </div>
      <div class="message-content"></div>
      ${buildMessageActions(role, item)}
    </div>
  `;

  if (markdownRoles.has(role)) {
    renderMessageMarkdown(div, item.content || "");
  } else {
    renderMessagePlainText(div, item.content || "");
  }
  bindMessageActions(div, item);
  return div;
}

function renderChatFlow(history) {
  const children = Array.from(el.chatFlow.children);
  children.forEach((child) => {
    if (child !== el.chatEmpty) child.remove();
  });

  if (!history || !history.length) {
    el.chatEmpty.classList.remove("hidden");
    return;
  }

  el.chatEmpty.classList.add("hidden");
  history.forEach((item, i) => {
    el.chatFlow.appendChild(createMessageEl(item, i));
  });

  requestAnimationFrame(() => {
    el.chatScroll.scrollTop = el.chatScroll.scrollHeight;
  });
}

function appendMessage(item, index) {
  el.chatEmpty.classList.add("hidden");
  el.chatFlow.appendChild(createMessageEl(item, index));
  requestAnimationFrame(() => {
    el.chatScroll.scrollTop = el.chatScroll.scrollHeight;
  });
}

/* ---------- 连接与模型渲染 ---------- */
function renderProfileSelectors(payload) {
  profileState = {
    activeProfileName: payload.active_profile_name,
    profiles: payload.profiles || [],
    connection: payload.connection || null,
    discoveredModels: profileState.discoveredModels || [],
  };
  renderConnectionForm();
  renderModelSelectors();
  renderDiscoveredModels(profileState.discoveredModels);
  syncSettingsState();
  resetProfileTestResult();
}

function renderConnectionForm() {
  const connection = profileState.connection || {};
  el.profileBaseUrl.value = connection.base_url || "";
  el.profileApiKey.value = "";
  el.profileKeyHint.textContent = connection.api_key_masked
    ? `当前已保存密钥：${connection.api_key_masked}，留空则继续沿用。`
    : "请填写 NewAPI API Key，保存后即可获取模型列表。";
}

function getApiModeLabel(apiMode) {
  return apiModeLabels[apiMode] || apiMode;
}

function getApiModeShortLabel(apiMode) {
  return apiModeShortLabels[apiMode] || apiMode;
}

function getProfileByName(profileName) {
  return profileState.profiles.find((profile) => profile.profile_name === profileName) || null;
}

function renderModelSelectors() {
  const hasProfiles = profileState.profiles.length > 0;
  const activeName = profileState.activeProfileName;

  [el.profileSelector, el.profileSelectorDrawer].forEach((select) => {
    select.innerHTML = "";
    if (!hasProfiles) {
      select.disabled = true;
      select.value = "";
      return;
    }

    profileState.profiles.forEach((profile) => {
      const option = document.createElement("option");
      option.value = profile.profile_name;
      option.textContent = profile.is_active
        ? `${profile.display_name} · ${getApiModeShortLabel(profile.api_mode)} · 已启用`
        : `${profile.display_name} · ${getApiModeShortLabel(profile.api_mode)}`;
      select.appendChild(option);
    });
    select.disabled = false;
    select.value = activeName || profileState.profiles[0].profile_name;
  });

  syncActiveProfileModeHint();
}

function renderDiscoveredModels(models) {
  profileState.discoveredModels = Array.isArray(models) ? [...models] : [];
  el.discoveredModelSelector.innerHTML = "";
  if (!profileState.discoveredModels.length) {
    el.discoveredModelSelector.disabled = true;
    el.discoveredModelSelector.value = "";
    return;
  }

  profileState.discoveredModels.forEach((modelName) => {
    const option = document.createElement("option");
    option.value = modelName;
    option.textContent = modelName;
    el.discoveredModelSelector.appendChild(option);
  });
  el.discoveredModelSelector.disabled = false;
}

function syncComposerAvailability() {
  el.submitButton.disabled = isLoading || !profileState.activeProfileName;
}

function syncActiveProfileModeHint() {
  const selectedProfileName = el.profileSelectorDrawer.value || profileState.activeProfileName;
  const profile = getProfileByName(selectedProfileName);
  if (!profile) {
    el.activeProfileModeHint.textContent = "当前模型的请求协议会在这里显示。";
    return;
  }
  el.activeProfileModeHint.textContent = `当前协议：${getApiModeLabel(profile.api_mode)}`;
}

function syncSettingsState() {
  const connectionConfigured = Boolean(profileState.connection?.is_configured);
  const hasProfiles = profileState.profiles.length > 0;
  const hasDiscoveredModels = profileState.discoveredModels.length > 0;
  const selectedProfileName = el.profileSelectorDrawer.value || profileState.activeProfileName;
  const hasSelectedProfile = Boolean(selectedProfileName);
  const hasSelectedApiMode = Boolean(el.profileApiMode.value);

  el.profileSelectorWrap.classList.toggle("hidden", !hasProfiles);
  el.activeModelSection.classList.toggle("hidden", !hasProfiles);
  el.discoveredModelSection.classList.toggle("hidden", !hasDiscoveredModels);

  el.discoverModels.disabled = isLoading || !connectionConfigured;
  el.profileApiMode.disabled = isLoading || !connectionConfigured || !hasDiscoveredModels;
  el.addModel.disabled = isLoading || !connectionConfigured || !hasDiscoveredModels || !hasSelectedApiMode;
  el.activateProfile.disabled = isLoading || !hasSelectedProfile;
  el.testProfile.disabled = isLoading || !hasSelectedProfile;
  el.deleteProfile.disabled = isLoading || !hasSelectedProfile;

  if (!connectionConfigured && !hasProfiles) {
    el.settingsEmptyState.textContent = "当前无配置方案";
    el.settingsEmptyState.classList.remove("hidden");
  } else if (connectionConfigured && !hasProfiles && !hasDiscoveredModels) {
    el.settingsEmptyState.textContent = "当前已保存连接，但还没有添加模型。";
    el.settingsEmptyState.classList.remove("hidden");
  } else {
    el.settingsEmptyState.classList.add("hidden");
  }

  syncActiveProfileModeHint();
  syncComposerAvailability();
}

function buildConnectionPayload() {
  return {
    base_url: el.profileBaseUrl.value.trim(),
    api_key: el.profileApiKey.value.trim() || null,
    timeout: 60,
  };
}

function buildProfilePayload() {
  const modelName = el.discoveredModelSelector.value;
  return {
    profile_name: modelName,
    display_name: modelName,
    model_name: modelName,
    api_mode: el.profileApiMode.value,
    extra_headers: {},
    enabled_capabilities: [],
  };
}

function resetConnectionResult() {
  el.connectionResult.textContent = "";
  el.connectionResult.className = "profile-test-result hidden";
}

function resetProfileTestResult() {
  el.profileTestResult.textContent = "";
  el.profileTestResult.className = "profile-test-result hidden";
}

function renderConnectionResult(message, ok = true) {
  el.connectionResult.textContent = message;
  el.connectionResult.className = `profile-test-result ${ok ? "success" : "error"}`;
}

function renderProfileTestResult(payload) {
  const lines = [payload.message || "连接测试已完成。"];
  if (payload.model) {
    lines.push(`模型：${payload.model}`);
  }
  if (payload.api_mode) {
    lines.push(`协议：${getApiModeLabel(payload.api_mode)}`);
  }
  if (payload.latency_ms) {
    lines.push(`耗时：${payload.latency_ms} ms`);
  }
  if (payload.output_text) {
    lines.push(`返回：${payload.output_text}`);
  }
  el.profileTestResult.textContent = lines.join("\n");
  el.profileTestResult.className = `profile-test-result ${payload.ok ? "success" : "error"}`;
}

/* ---------- 数据刷新 ---------- */
async function refreshAll() {
  const [, profiles] = await Promise.all([
    loadSessionSnapshot(),
    api("/api/llm/profiles"),
    refreshCapabilities(),
  ]);
  renderProfileSelectors(profiles);

  /* refreshCapabilities 已在 Promise.all 中完成 */
}

/* ---------- 能力注册表刷新 ---------- */
async function refreshCapabilities() {
  const types = ["tool", "mcp", "skill"];
  for (const type of types) {
    try {
      const data = await api(`/api/capabilities/${type}`);
      capState[type].items = (data.items || []).map((it) => ({
        name: it.name,
        description: it.description || "",
        enabled: it.enabled !== false,
        endpoint: it.endpoint || "",
        transport: it.transport || "",
        command: it.command || "",
        entry: it.entry || "",
      }));
    } catch {
      /* 后端尚未实现此接口，保持空列表 */
    }
  }
  renderAllCapDrawers();
}

/* ---------- 能力抽屉渲染 ---------- */
function renderCapDrawer(type) {
  const state = capState[type];

  /* 映射 DOM 元素（统一处理 tool→tools / mcp→mcp / skill→skills 命名） */
  const map = {
    tool:  { list: el.toolsList,  count: el.toolsCount,  badge: el.toolsBadge,  master: el.toolsMasterToggle },
    mcp:   { list: el.mcpList,    count: el.mcpCount,    badge: el.mcpBadge,    master: el.mcpMasterToggle },
    skill: { list: el.skillsList, count: el.skillsCount, badge: el.skillsBadge, master: el.skillsMasterToggle },
  };
  const dom = map[type];
  if (!dom) return;

  dom.master.checked = state.masterEnabled;

  const total = state.items.length;
  const enabled = state.items.filter((it) => it.enabled).length;
  dom.count.textContent = `已启用 ${enabled} / ${total}`;
  dom.badge.textContent = String(total);
  dom.badge.classList.toggle("has-items", total > 0);

  /* 渲染列表 */
  dom.list.innerHTML = "";
  if (total === 0) {
    const typeLabel = { tool: "TOOL", mcp: "MCP", skill: "SKILL" }[type];
    dom.list.innerHTML = `<div class="cap-empty">暂无已注册 ${typeLabel}，点击上方「添加 ${typeLabel}」进行注册。</div>`;
    return;
  }

  dom.list.innerHTML = "";
  state.items.forEach((item, idx) => {
    const meta = [
      item.description,
      item.endpoint ? `调用地址：${item.endpoint}` : "",
      item.transport ? `传输方式：${item.transport}` : "",
      item.command ? `启动命令：${item.command}` : "",
      item.entry ? `入口路径：${item.entry}` : "",
    ].filter(Boolean);
    const div = document.createElement("div");
    div.className = `cap-item${item.enabled ? " enabled" : ""}`;
    const switchId = `${type}-switch-${idx}`;
    div.innerHTML = `
      <div class="cap-item-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          ${type === "tool" ? '<path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>'
           : type === "mcp" ? '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>'
           : '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>'}
        </svg>
      </div>
      <div class="cap-item-info">
        <div class="cap-item-name">${escapeHtml(item.name)}</div>
        <div class="cap-item-desc">${meta.map((line) => `<div class="cap-item-meta">${escapeHtml(line)}</div>`).join("")}</div>
      </div>
      <div class="cap-item-switch">
        <input type="checkbox" id="${switchId}" ${item.enabled ? "checked" : ""} />
        <label for="${switchId}"></label>
      </div>
      <button class="cap-item-delete" type="button" title="删除" aria-label="删除 ${item.name}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
      </button>
    `;
    /* 子项开关事件 */
    const checkbox = div.querySelector("input");
    checkbox.addEventListener("change", async () => {
      const previous = item.enabled;
      item.enabled = checkbox.checked;
      div.classList.toggle("enabled", checkbox.checked);
      renderCapDrawer(type);
      try {
        const data = await api(`/api/capabilities/${type}/${encodeURIComponent(item.name)}/toggle`, {
          method: "POST",
        });
        capState[type].items = (data.items || []).map((capability) => ({
          name: capability.name,
          description: capability.description || "",
          enabled: capability.enabled !== false,
          endpoint: capability.endpoint || "",
          transport: capability.transport || "",
          command: capability.command || "",
          entry: capability.entry || "",
        }));
        renderCapDrawer(type);
      } catch (err) {
        item.enabled = previous;
        renderCapDrawer(type);
        showToast(err.message, "error");
      }
    });
    /* 删除按钮事件 */
    div.querySelector(".cap-item-delete").addEventListener("click", async () => {
      if (!window.confirm(`确定要删除 ${item.name} 吗？`)) return;
      await removeCapItem(type, idx);
    });
    dom.list.appendChild(div);
  });
}

function renderAllCapDrawers() {
  renderCapDrawer("tool");
  renderCapDrawer("mcp");
  renderCapDrawer("skill");
}

/* ---------- 能力抽屉 开/关 ---------- */
function openCapDrawer(type) {
  const map = {
    tool:  { overlay: el.toolsOverlay,  drawer: el.toolsDrawer },
    mcp:   { overlay: el.mcpOverlay,    drawer: el.mcpDrawer },
    skill: { overlay: el.skillsOverlay, drawer: el.skillsDrawer },
  };
  const dom = map[type];
  if (!dom) return;
  dom.overlay.classList.add("open");
  dom.drawer.classList.add("open");
}

function closeCapDrawer(type) {
  const map = {
    tool:  { overlay: el.toolsOverlay,  drawer: el.toolsDrawer },
    mcp:   { overlay: el.mcpOverlay,    drawer: el.mcpDrawer },
    skill: { overlay: el.skillsOverlay, drawer: el.skillsDrawer },
  };
  const dom = map[type];
  if (!dom) return;
  dom.overlay.classList.remove("open");
  dom.drawer.classList.remove("open");
}

/* ---------- 添加能力项 ---------- */
async function addCapItem(type, formData) {
  const name = formData.get("name")?.trim();
  if (!name) { showToast("名称不能为空", "error"); return; }
  /* 检查重名 */
  if (capState[type].items.some((it) => it.name === name)) {
    showToast(`${name} 已存在`, "error");
    return;
  }
  const newItem = {
    name,
    description: formData.get("description")?.trim() || "",
    enabled: true,
    /* 各类型特有字段，前端暂存 */
    endpoint: formData.get("endpoint")?.trim() || "",
    transport: formData.get("transport")?.trim() || "",
    command: formData.get("command")?.trim() || "",
    entry: formData.get("entry")?.trim() || "",
  };

  /* 尝试通知后端 */
  try {
    await api(`/api/capabilities/${type}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(newItem),
    });
  } catch {
    /* 后端尚未实现，仅前端本地添加 */
  }

  capState[type].items.push(newItem);
  renderCapDrawer(type);
  showToast(`${name} 已添加`, "success");
}

/* ---------- 删除能力项 ---------- */
async function removeCapItem(type, idx) {
  const item = capState[type].items[idx];
  if (!item) return;

  /* 尝试通知后端 */
  try {
    await api(`/api/capabilities/${type}/${encodeURIComponent(item.name)}`, { method: "DELETE" });
  } catch {
    /* 后端尚未实现，仅前端本地删除 */
  }

  capState[type].items.splice(idx, 1);
  renderCapDrawer(type);
  showToast(`${item.name} 已删除`, "success");
}

/* ---------- 添加表单展开/折叠 ---------- */
function setupAddFormToggle(type) {
  const toggleMap = {
    tool:  { toggle: el.toolsAddToggle,  form: el.toolsAddForm },
    mcp:   { toggle: el.mcpAddToggle,    form: el.mcpAddForm },
    skill: { toggle: el.skillsAddToggle, form: el.skillsAddForm },
  };
  const dom = toggleMap[type];
  if (!dom) return;

  /* 点击标题展开/折叠 */
  dom.toggle.addEventListener("click", () => {
    dom.form.classList.toggle("hidden");
  });

  /* 取消按钮 */
  dom.form.querySelector("[data-action=cancel]").addEventListener("click", () => {
    dom.form.classList.add("hidden");
    dom.form.reset();
  });

  /* 提交 */
  dom.form.addEventListener("submit", async (e) => {
    e.preventDefault();
    await addCapItem(type, new FormData(dom.form));
    dom.form.reset();
    dom.form.classList.add("hidden");
  });
}

/* ---------- 设置抽屉 ---------- */
function openSettings() {
  el.settingsOverlay.classList.add("open");
  el.settingsDrawer.classList.add("open");
}

function closeSettings() {
  el.settingsOverlay.classList.remove("open");
  el.settingsDrawer.classList.remove("open");
}

/* ---------- 侧边栏（移动端） ---------- */
function openSidebar() {
  el.sidebar.classList.add("open");
  el.sidebarBackdrop.classList.add("open");
}

function closeSidebar() {
  el.sidebar.classList.remove("open");
  el.sidebarBackdrop.classList.remove("open");
}

/* ---------- textarea 自动高度 ---------- */
function autoResizeTextarea() {
  el.goal.style.height = "auto";
  el.goal.style.height = Math.min(el.goal.scrollHeight, 200) + "px";
}

function submitRoundForm() {
  if (typeof el.roundForm.requestSubmit === "function") {
    el.roundForm.requestSubmit(el.submitButton);
    return;
  }
  el.submitButton.click();
}

/* ========== 事件绑定 ========== */

/* 添加表单初始化 */
setupAddFormToggle("tool");
setupAddFormToggle("mcp");
setupAddFormToggle("skill");

/* 能力管理抽屉 — 打开 */
el.btnOpenTools.addEventListener("click", () => openCapDrawer("tool"));
el.btnOpenMcp.addEventListener("click", () => openCapDrawer("mcp"));
el.btnOpenSkills.addEventListener("click", () => openCapDrawer("skill"));

/* 能力管理抽屉 — 关闭 */
el.btnCloseTools.addEventListener("click", () => closeCapDrawer("tool"));
el.btnCloseMcp.addEventListener("click", () => closeCapDrawer("mcp"));
el.btnCloseSkills.addEventListener("click", () => closeCapDrawer("skill"));
el.toolsOverlay.addEventListener("click", () => closeCapDrawer("tool"));
el.mcpOverlay.addEventListener("click", () => closeCapDrawer("mcp"));
el.skillsOverlay.addEventListener("click", () => closeCapDrawer("skill"));

/* 能力管理抽屉 — 主开关 */
el.toolsMasterToggle.addEventListener("change", () => {
  capState.tool.masterEnabled = el.toolsMasterToggle.checked;
  renderCapDrawer("tool");
});
el.mcpMasterToggle.addEventListener("change", () => {
  capState.mcp.masterEnabled = el.mcpMasterToggle.checked;
  renderCapDrawer("mcp");
});
el.skillsMasterToggle.addEventListener("change", () => {
  capState.skill.masterEnabled = el.skillsMasterToggle.checked;
  renderCapDrawer("skill");
});

/* 发送表单 */
el.goal.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || !event.ctrlKey || event.altKey || event.shiftKey || event.isComposing) {
    return;
  }
  event.preventDefault();
  if (el.submitButton.disabled) {
    return;
  }
  submitRoundForm();
});

el.roundForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!validateForm()) return;

  const actionType = resolveActionType();
  const enabledCaps = getEnabledCapabilities();

  setLoading(true);
  try {
    const payload = await api("/api/round", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        goal: el.goal.value.trim(),
        action_type: actionType,
        target: null,
        profile_name: profileState.activeProfileName,
        enabled_capabilities: enabledCaps,
        /* 各能力类型的细粒度启用列表 */
        enabled_tools: capState.tool.masterEnabled
          ? capState.tool.items.filter((it) => it.enabled).map((it) => it.name) : [],
        enabled_mcp: capState.mcp.masterEnabled
          ? capState.mcp.items.filter((it) => it.enabled).map((it) => it.name) : [],
        enabled_skills: capState.skill.masterEnabled
          ? capState.skill.items.filter((it) => it.enabled).map((it) => it.name) : [],
        rag_enabled: el.ragToggle.checked,
      }),
    });

    updateStatusDot(payload.status?.status_label);
    renderChatFlow(payload.history || []);
    if (payload.result_type !== "clarify") {
      el.goal.value = "";
      autoResizeTextarea();
    }
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    setLoading(false);
  }
});

/* 刷新 */
el.refreshStatus.addEventListener("click", async () => {
  setLoading(true);
  try { await refreshAll(); showToast("已刷新", "success"); }
  catch (err) { showToast(err.message, "error"); }
  finally { setLoading(false); }
});

/* 重置会话 */
el.resetSession.addEventListener("click", async () => {
  if (!window.confirm("确定要重置当前会话吗？历史消息会被清空。")) return;
  setLoading(true);
  try {
    const payload = await api(`/api/session/${sessionId}/reset`, { method: "POST" });
    updateStatusDot(payload.status?.status_label);
    renderChatFlow([]);
    showToast(payload.message || "会话已重置", "success");
  } catch (err) { showToast(err.message, "error"); }
  finally { setLoading(false); }
});

/* 复制会话 ID */
el.copySession.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(sessionId);
    showToast("会话标识已复制", "success");
  } catch (err) { showToast(`复制失败：${err.message}`, "error"); }
});

/* textarea 自动高度 */
el.goal.addEventListener("input", autoResizeTextarea);

/* 侧边栏切换（移动端） */
el.btnSidebarToggle.addEventListener("click", openSidebar);
el.sidebarBackdrop.addEventListener("click", closeSidebar);

/* 设置抽屉 */
el.btnOpenSettings.addEventListener("click", openSettings);
el.settingsOverlay.addEventListener("click", closeSettings);
el.btnCloseSettings.addEventListener("click", closeSettings);

/* 顶栏方案选择器同步到抽屉 */
el.profileSelectorDrawer.addEventListener("change", () => {
  resetProfileTestResult();
  syncSettingsState();
});

el.profileApiMode.addEventListener("change", () => {
  syncSettingsState();
});

el.profileForm.addEventListener("submit", (e) => {
  e.preventDefault();
});

async function activateProfileByName(name, successMessage = "已启用模型") {
  if (!name) {
    showToast("当前没有可启用的模型", "error");
    return;
  }
  setLoading(true);
  try {
    const resp = await api(`/api/llm/profiles/${name}/activate`, { method: "POST" });
    renderProfileSelectors(resp.profiles);
    showToast(resp.message || successMessage, "success");
  } catch (err) { showToast(err.message, "error"); }
  finally { setLoading(false); }
}

el.profileSelector.addEventListener("change", async () => {
  const name = el.profileSelector.value;
  if (!name || name === profileState.activeProfileName) return;
  await activateProfileByName(name);
});

/* 保存连接 */
el.saveConnection.addEventListener("click", async () => {
  const payload = buildConnectionPayload();
  if (!payload.base_url) {
    showToast("请先填写 NewAPI base_url", "error");
    return;
  }
  setLoading(true);
  resetConnectionResult();
  try {
    const resp = await api("/api/llm/connection", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderProfileSelectors(resp.profiles);
    renderDiscoveredModels([]);
    syncSettingsState();
    renderConnectionResult(resp.message || "连接配置已保存", true);
    showToast(resp.message || "连接配置已保存", "success");
  } catch (err) {
    renderConnectionResult(err.message || "连接配置保存失败", false);
    showToast(err.message, "error");
  } finally {
    setLoading(false);
  }
});

/* 获取模型 */
el.discoverModels.addEventListener("click", async () => {
  setLoading(true);
  resetConnectionResult();
  try {
    const resp = await api("/api/llm/connection/models", { method: "POST" });
    renderDiscoveredModels(resp.models || []);
    syncSettingsState();
    renderConnectionResult(resp.message || "模型列表已更新", true);
    showToast(resp.message || "模型列表已更新", "success");
  } catch (err) {
    renderDiscoveredModels([]);
    syncSettingsState();
    renderConnectionResult(err.message || "模型获取失败", false);
    showToast(err.message, "error");
  } finally {
    setLoading(false);
  }
});

/* 添加模型 */
el.addModel.addEventListener("click", async () => {
  const payload = buildProfilePayload();
  if (!payload.model_name) {
    showToast("请先从站点列表中选择一个模型", "error");
    return;
  }
  if (!payload.api_mode) {
    showToast("请先选择模型的请求协议", "error");
    return;
  }
  setLoading(true);
  try {
    const resp = await api("/api/llm/profiles", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderProfileSelectors(resp.profiles);
    el.profileSelectorDrawer.value = payload.profile_name;
    syncSettingsState();
    showToast(resp.message || "模型已添加", "success");
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    setLoading(false);
  }
});

/* 设为当前 */
el.activateProfile.addEventListener("click", async () => {
  const name = el.profileSelectorDrawer.value;
  await activateProfileByName(name);
});

/* 测试当前方案连接 */
el.testProfile.addEventListener("click", async () => {
  const name = el.profileSelectorDrawer.value;
  if (!name) {
    showToast("当前没有可测试的模型", "error");
    return;
  }

  setLoading(true);
  resetProfileTestResult();
  try {
    const resp = await api(`/api/llm/profiles/${encodeURIComponent(name)}/test`, { method: "POST" });
    renderProfileTestResult(resp);
    showToast(resp.ok ? "连接测试成功" : "连接测试失败", resp.ok ? "success" : "error");
  } catch (err) {
    renderProfileTestResult({
      ok: false,
      message: err.message || "连接测试失败",
      model: null,
      api_mode: null,
      latency_ms: 0,
      output_text: null,
    });
    showToast(err.message, "error");
  } finally {
    setLoading(false);
  }
});

/* 删除方案 */
el.deleteProfile.addEventListener("click", async () => {
  const name = el.profileSelectorDrawer.value;
  if (!name) { showToast("当前没有可删除的模型", "error"); return; }
  if (!window.confirm(`确定要删除模型 ${name} 吗？`)) return;
  setLoading(true);
  try {
    const resp = await api(`/api/llm/profiles/${name}`, { method: "DELETE" });
    renderProfileSelectors(resp.profiles);
    resetProfileTestResult();
    showToast(resp.message || "模型已删除", "success");
  } catch (err) { showToast(err.message, "error"); }
  finally { setLoading(false); }
});

/* 新建对话（预留） */
el.btnNewChat.addEventListener("click", () => {
  showToast("多会话功能即将上线", "info");
});

/* ========== 初始化 ========== */
refreshAll().catch((err) => { showToast(err.message, "error"); });
