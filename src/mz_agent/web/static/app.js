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
  profileName: $("profile-name"),
  profileProviderType: $("profile-provider-type"),
  profileModel: $("profile-model"),
  profileApiMode: $("profile-api-mode"),
  profileBaseUrl: $("profile-base-url"),
  profileApiKey: $("profile-api-key"),
  profileKeyHint: $("profile-key-hint"),
  activateProfile: $("activate-profile"),
  saveProfile: $("save-profile"),
  newProfile: $("new-profile"),
  deleteProfile: $("delete-profile"),

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

let profileState = { activeProfileName: null, defaultProfileName: null, profiles: [] };
let isLoading = false;

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

/* 预留：Agent SSE 实时流 */
// function connectAgentStream(sessionId, onMessage) {
//   const source = new EventSource(`/api/agent/stream?session_id=${sessionId}`);
//   source.onmessage = (e) => onMessage(JSON.parse(e.data));
//   return source;
// }

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
  el.submitButton.disabled = loading;
  el.refreshStatus.disabled = loading;
  el.resetSession.disabled = loading;
  el.thinkingIndicator.classList.toggle("hidden", !loading);
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
  const goal = el.goal.value.trim();
  if (!goal) {
    el.goalError.textContent = "请先填写你想让我做什么。";
    return false;
  }
  return true;
}

/* ---------- 对话流渲染 ---------- */
function createMessageEl(item, index) {
  const role = item.role || "unknown";
  const div = document.createElement("div");
  div.className = "message";
  div.dataset.role = role;

  div.innerHTML = `
    <div class="message-avatar">${roleAvatarText[role] || "?"}</div>
    <div class="message-body">
      <div class="message-header">
        <span class="message-role">${roleLabels[role] || role}</span>
        <span class="message-index">#${index + 1}</span>
      </div>
      <div class="message-content"></div>
    </div>
  `;
  div.querySelector(".message-content").textContent = item.content || "";
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

/* ---------- 连接方案渲染 ---------- */
function renderProfileSelectors(payload) {
  profileState = {
    activeProfileName: payload.active_profile_name,
    defaultProfileName: payload.default_profile_name,
    profiles: payload.profiles || [],
  };

  [el.profileSelector, el.profileSelectorDrawer].forEach((select) => {
    select.innerHTML = "";
    profileState.profiles.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.profile_name;
      const label = p.profile_name;
      opt.textContent = p.is_default ? `${label} · 当前` : label;
      select.appendChild(opt);
    });
    const active = profileState.activeProfileName || profileState.defaultProfileName;
    if (active) select.value = active;
  });

  loadProfileIntoForm(profileState.activeProfileName || profileState.defaultProfileName);
}

function loadProfileIntoForm(name) {
  const p = profileState.profiles.find((x) => x.profile_name === name);
  if (!p) return;
  el.profileName.value = p.profile_name;
  el.profileProviderType.value = p.provider_type;
  el.profileModel.value = p.default_model || "";
  el.profileBaseUrl.value = p.base_url || "";
  el.profileApiKey.value = "";
  el.profileApiMode.value = p.api_mode || "responses";
  el.profileKeyHint.textContent = p.api_key_masked
    ? `该方案已保存密钥：${p.api_key_masked}`
    : "该方案尚未配置密钥，请填写后保存。";
}

function clearProfileForm() {
  el.profileName.value = "";
  el.profileProviderType.value = "openai_compatible_proxy";
  el.profileModel.value = "";
  el.profileBaseUrl.value = "";
  el.profileApiKey.value = "";
  el.profileApiMode.value = "responses";
  el.profileKeyHint.textContent = "新方案需要单独配置密钥，保存后即可切换使用。";
}

function buildProfilePayload() {
  const name = el.profileName.value.trim();
  return {
    profile_name: name,
    display_name: name,
    provider_type: el.profileProviderType.value,
    default_model: el.profileModel.value.trim() || null,
    base_url: el.profileBaseUrl.value.trim() || null,
    api_key: el.profileApiKey.value.trim() || null,
    api_mode: el.profileApiMode.value,
    timeout: 60,
    extra_headers: {},
    enabled_capabilities: [],
  };
}

/* ---------- 数据刷新 ---------- */
async function refreshAll() {
  const [status, history, profiles] = await Promise.all([
    api(`/api/session/${sessionId}/status`),
    api(`/api/session/${sessionId}/history`),
    api("/api/llm/profiles"),
  ]);
  updateStatusDot(status.status_label);
  renderChatFlow(history.history || []);
  renderProfileSelectors(profiles);

  /* 尝试刷新能力注册表（后端如尚未实现则静默跳过） */
  refreshCapabilities();
}

/* ---------- 能力注册表刷新 ---------- */
async function refreshCapabilities() {
  /* 预留 API：GET /api/capabilities/{type} → { items: [{ name, description, enabled }] } */
  const types = ["tool", "mcp", "skill"];
  for (const type of types) {
    try {
      const data = await api(`/api/capabilities/${type}`);
      capState[type].items = (data.items || []).map((it) => ({
        name: it.name,
        description: it.description || "",
        enabled: it.enabled !== false,
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
        <div class="cap-item-name">${item.name}</div>
        <div class="cap-item-desc">${item.description}</div>
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
    checkbox.addEventListener("change", () => {
      item.enabled = checkbox.checked;
      div.classList.toggle("enabled", checkbox.checked);
      renderCapDrawer(type);
      /* 预留：通知后端 POST /api/capabilities/{type}/{name}/toggle */
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
    await api(`/api/capabilities/${type}/${item.name}`, { method: "DELETE" });
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
        profile_name: el.profileSelector.value || null,
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
el.profileSelector.addEventListener("change", () => {
  el.profileSelectorDrawer.value = el.profileSelector.value;
  loadProfileIntoForm(el.profileSelector.value);
});

el.profileSelectorDrawer.addEventListener("change", () => {
  el.profileSelector.value = el.profileSelectorDrawer.value;
  loadProfileIntoForm(el.profileSelectorDrawer.value);
});

/* 方案保存 */
el.profileForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = buildProfilePayload();
  if (!payload.profile_name) { showToast("请先填写方案名", "error"); return; }
  const exists = profileState.profiles.some((p) => p.profile_name === payload.profile_name);
  const method = exists ? "PUT" : "POST";
  const path = exists ? `/api/llm/profiles/${payload.profile_name}` : "/api/llm/profiles";
  setLoading(true);
  try {
    const resp = await api(path, {
      method,
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    renderProfileSelectors(resp.profiles);
    el.profileSelector.value = payload.profile_name;
    el.profileSelectorDrawer.value = payload.profile_name;
    loadProfileIntoForm(payload.profile_name);
    showToast(resp.message || "方案已保存", "success");
  } catch (err) { showToast(err.message, "error"); }
  finally { setLoading(false); }
});

/* 设为当前 */
el.activateProfile.addEventListener("click", async () => {
  const name = el.profileSelectorDrawer.value;
  if (!name) { showToast("当前没有可切换的连接方案", "error"); return; }
  setLoading(true);
  try {
    const resp = await api(`/api/llm/profiles/${name}/activate`, { method: "POST" });
    renderProfileSelectors(resp.profiles);
    showToast(resp.message || "已切换", "success");
  } catch (err) { showToast(err.message, "error"); }
  finally { setLoading(false); }
});

/* 新建方案 */
el.newProfile.addEventListener("click", clearProfileForm);

/* 删除方案 */
el.deleteProfile.addEventListener("click", async () => {
  const name = el.profileSelectorDrawer.value;
  if (!name) { showToast("当前没有可删除的连接方案", "error"); return; }
  if (!window.confirm(`确定要删除连接方案 ${name} 吗？`)) return;
  setLoading(true);
  try {
    const resp = await api(`/api/llm/profiles/${name}`, { method: "DELETE" });
    renderProfileSelectors(resp.profiles);
    showToast(resp.message || "方案已删除", "success");
  } catch (err) { showToast(err.message, "error"); }
  finally { setLoading(false); }
});

/* 新建对话（预留） */
el.btnNewChat.addEventListener("click", () => {
  showToast("多会话功能即将上线", "info");
});

/* ========== 初始化 ========== */
refreshAll().catch((err) => { showToast(err.message, "error"); });
