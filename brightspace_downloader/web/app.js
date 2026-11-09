"use strict";

/* ------------------------------------------------------------------ helpers */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const el = (tag, cls, text) => {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
};

function fmtBytes(n) {
  if (n == null || isNaN(n)) return "";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = n / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) { value /= 1024; i++; }
  return `${value.toFixed(value < 10 ? 1 : 0)} ${units[i]}`;
}
function fmtSpeed(bytesPerSec) {
  if (!bytesPerSec || bytesPerSec < 1) return "";
  return `${fmtBytes(bytesPerSec)}/s`;
}
function initials(name) {
  const words = (name || "").replace(/\(.*?\)/g, " ").split(/[\s\-_]+/).filter(Boolean);
  if (!words.length) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

let toastTimer = null;
function toast(message, isError = false) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.toggle("error", isError);
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, isError ? 6000 : 3200);
}

/* ------------------------------------------------------------------ bridge */
const Api = new Proxy({}, {
  get: (_t, name) => (...args) => {
    if (!window.pywebview || !window.pywebview.api || !window.pywebview.api[name]) {
      return Promise.reject(new Error(`Bridge method ${name} is not available`));
    }
    return window.pywebview.api[name](...args);
  },
});

function pywebviewReady() {
  return new Promise((resolve) => {
    if (window.pywebview && window.pywebview.api) return resolve();
    window.addEventListener("pywebviewready", () => resolve(), { once: true });
    const timer = setInterval(() => {
      if (window.pywebview && window.pywebview.api) { clearInterval(timer); resolve(); }
    }, 60);
  });
}

/* ------------------------------------------------------------------ state */
const state = {
  initial: null,
  host: "",
  user: null,
  course: null,      // {id, name, ...}
  tree: null,        // content json
  running: false,
  errors: [],
};

function showScreen(name) { document.body.dataset.screen = name; }

function setMsg(node, text, kind = "") {
  node.textContent = text || "";
  node.className = "inline-msg" + (kind ? " " + kind : "");
}

function busy(button, on) {
  if (!button) return;
  button.classList.toggle("btn-busy", on);
  button.disabled = on;
}

/* ------------------------------------------------------------------ boot */
async function boot() {
  await pywebviewReady();
  let initial;
  try {
    initial = await Api.get_initial_state();
  } catch (err) {
    showScreen("login");
    setMsg($("#base-url-msg"), "Could not start the backend. Please restart the app.", "error");
    return;
  }
  state.initial = initial;
  $("#base-url").value = initial.baseUrl || "";
  setupBrowserImport(initial.browserImport);

  if (initial.hasSavedSession) {
    const result = await Api.resume_session().catch(() => ({ ok: false }));
    if (result.ok) { enterCourses(result); return; }
  }
  showScreen("login");
  if (initial.baseUrl) revealAuthMethods(hostFromUrl(initial.baseUrl));
  $("#base-url").focus();
}

function hostFromUrl(url) {
  try { return new URL(url.includes("://") ? url : "https://" + url).hostname; }
  catch { return url; }
}

/* ------------------------------------------------------------------ login */
function revealAuthMethods(host) {
  state.host = host || "";
  $("#auth-host-label").textContent = host ? `Signed-in site · ${host}` : "Sign in";
  $("#auth-methods").hidden = false;
}

function setupBrowserImport(info) {
  const row = $("#browser-import-row");
  if (!info || !info.available || !info.browsers || !info.browsers.length) { row.hidden = true; return; }
  const select = $("#browser-select");
  select.innerHTML = "";
  const labels = { chrome: "Chrome", edge: "Edge", firefox: "Firefox", brave: "Brave", chromium: "Chromium", opera: "Opera", vivaldi: "Vivaldi" };
  info.browsers.forEach((b) => {
    const opt = el("option", null, labels[b] || b);
    opt.value = b;
    select.appendChild(opt);
  });
  row.hidden = false;
}

async function connect() {
  const value = $("#base-url").value.trim();
  if (!value) { setMsg($("#base-url-msg"), "Enter your Brightspace address.", "error"); return; }
  busy($("#connect-btn"), true);
  setMsg($("#base-url-msg"), "Checking…", "busy");
  const result = await Api.set_base_url(value).catch((e) => ({ ok: false, error: String(e) }));
  busy($("#connect-btn"), false);
  if (!result.ok) { setMsg($("#base-url-msg"), result.error || "Could not reach that address.", "error"); return; }
  $("#base-url").value = result.baseUrl;
  setMsg($("#base-url-msg"), `Connected to ${result.host}.`, "ok");
  revealAuthMethods(result.host);
}

async function loginWithWindow() {
  setMsg($("#login-msg"), "Opening the Brightspace login window…", "busy");
  const btn = $("#login-window-btn");
  btn.disabled = true;
  const result = await Api.login_with_window().catch((e) => ({ ok: false, error: String(e) }));
  btn.disabled = false;
  if (result.ok) { enterCourses(result); return; }
  if (result.cancelled) setMsg($("#login-msg"), "Login window closed.", "");
  else setMsg($("#login-msg"), result.error || "Login failed.", "error");
}

async function importCookieFile() {
  setMsg($("#login-msg"), "Choose a cookies file…", "busy");
  const result = await Api.pick_cookie_file().catch((e) => ({ ok: false, error: String(e) }));
  if (result.cancelled) { setMsg($("#login-msg"), "", ""); return; }
  if (result.ok) { enterCourses(result); return; }
  setMsg($("#login-msg"), result.error || "Could not import cookies.", "error");
}

async function importFromBrowser() {
  const browser = $("#browser-select").value;
  busy($("#browser-import-btn"), true);
  setMsg($("#login-msg"), `Reading cookies from ${browser}…`, "busy");
  const result = await Api.import_from_browser(browser).catch((e) => ({ ok: false, error: String(e) }));
  busy($("#browser-import-btn"), false);
  if (result.ok) { enterCourses(result); return; }
  setMsg($("#login-msg"), result.error || "Could not read cookies.", "error");
}

/* ------------------------------------------------------------------ courses */
function setUser(user) {
  state.user = user;
  if (user && user.name) {
    $("#user-name").textContent = user.name;
    $("#user-chip").hidden = false;
    $("#logout-btn").hidden = false;
  }
}

async function enterCourses(loginResult) {
  if (loginResult && loginResult.user) setUser(loginResult.user);
  showScreen("courses");
  await loadCourses();
}

async function loadCourses() {
  const listEl = $("#course-list");
  setMsg($("#courses-status"), "Loading your courses… ", "busy");
  $("#courses-status").innerHTML = '<span class="spinner"></span> Loading your courses…';
  listEl.innerHTML = "";
  const result = await Api.list_courses().catch((e) => ({ ok: false, error: String(e) }));
  if (!result.ok) {
    setMsg($("#courses-status"), result.error || "Could not load courses.", "error");
    if (result.error && /not logged in|expired/i.test(result.error)) backToLogin(result.error);
    return;
  }
  setMsg($("#courses-status"), "");
  if (result.user) setUser(result.user);
  state.courses = result.courses || [];
  renderCourses(state.courses);
}

function renderCourses(courses) {
  const listEl = $("#course-list");
  listEl.innerHTML = "";
  if (!courses.length) {
    const empty = el("div", "empty-state");
    empty.textContent = "No courses found on this account.";
    listEl.appendChild(empty);
    return;
  }
  courses.forEach((course) => {
    const card = el("button", "course-card");
    card.appendChild(el("span", "course-badge", initials(course.code || course.name)));
    const info = el("div", "course-info");
    info.appendChild(el("div", "course-name", course.name));
    const meta = el("div", "course-meta");
    if (course.code) meta.appendChild(el("span", null, course.code));
    if (course.pinned) meta.appendChild(el("span", "pill pin", "pinned"));
    if (course.active === false) meta.appendChild(el("span", "pill inactive", "inactive"));
    info.appendChild(meta);
    card.appendChild(info);
    card.appendChild(el("span", "course-go", "›"));
    card.addEventListener("click", () => openCourse(course));
    listEl.appendChild(card);
  });
}

function filterCourses(query) {
  const q = query.trim().toLowerCase();
  const filtered = !q ? state.courses
    : state.courses.filter((c) => (c.name + " " + (c.code || "")).toLowerCase().includes(q));
  renderCourses(filtered);
}

function backToLogin(message) {
  setUser(null);
  $("#user-chip").hidden = true;
  $("#logout-btn").hidden = true;
  showScreen("login");
  if (message) setMsg($("#login-msg"), message, "error");
}

/* ------------------------------------------------------------------ content */
async function openCourse(course) {
  state.course = course;
  state.tree = null;
  showScreen("content");
  $("#content-course-name").textContent = course.name;
  $("#content-sub").textContent = course.code || "";
  $("#content-body").hidden = true;
  $("#content-status").innerHTML = '<span class="spinner"></span> Reading course content…';
  $("#content-status").className = "inline-msg busy";

  const result = await Api.load_content(course.id).catch((e) => ({ ok: false, error: String(e) }));
  if (!result.ok) {
    setMsg($("#content-status"), result.error || "Could not read course content.", "error");
    if (result.error && /not logged in|expired/i.test(result.error)) backToLogin(result.error);
    return;
  }
  state.tree = result;
  if (!result.fileCount) {
    let text = "This course has no downloadable files in its Content area.";
    if (result.skippedText) text += ` (${result.skippedText} can't be downloaded here.)`;
    setMsg($("#content-status"), text, "");
    return;
  }
  setMsg($("#content-status"), "");
  $("#content-body").hidden = false;
  $("#dest-input").value = result.defaultDir || state.initial.defaultDir || "";
  $("#policy-select").value = state.initial.existingPolicy || "skip";
  updateDestHint();
  renderTree(result.nodes);
  let sub = `${result.fileCount} file${result.fileCount === 1 ? "" : "s"}`;
  if (result.skippedText) sub += ` · ${result.skippedText} skipped`;
  $("#content-sub").textContent = (course.code ? course.code + " · " : "") + sub;
}

function updateDestHint() {
  const base = $("#dest-input").value.trim().replace(/[\\/]+$/, "");
  const hint = $("#dest-hint");
  const nodes = state.tree && state.tree.nodes;
  if (!base || !nodes || !nodes.length) { hint.textContent = ""; return; }
  const sep = base.includes("\\") ? "\\" : "/";
  const firstFolder = nodes.find((n) => n.type === "folder") || nodes[0];
  hint.textContent = `Saved here, keeping the Brightspace folders — e.g. ${base}${sep}${firstFolder.name}${sep}…`;
}

/* ---- tree with tri-state checkboxes ---- */
const FOLDER_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';
const FILE_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/></svg>';
const CHEVRON_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>';

function renderTree(nodes) {
  const root = $("#tree");
  root.innerHTML = "";
  root.appendChild(buildList(nodes));
  refreshAllFolderStates();
  updateSelectionSummary();
}

function buildList(nodes) {
  const ul = el("ul");
  nodes.forEach((node) => ul.appendChild(node.type === "folder" ? buildFolder(node) : buildFile(node)));
  return ul;
}

function buildFolder(node) {
  const li = el("li", "node node-folder");
  li.dataset.type = "folder";
  const row = el("div", "node-row");

  const twisty = el("button", "twisty");
  twisty.innerHTML = CHEVRON_SVG;
  twisty.addEventListener("click", (e) => { e.stopPropagation(); toggleFolder(li, twisty); });

  const check = el("input", "node-check");
  check.type = "checkbox";
  check.addEventListener("change", () => {
    setSubtreeChecked(li, check.checked);
    updateAncestors(li);
    updateSelectionSummary();
  });

  const label = el("div", "node-label");
  const icon = el("span", "node-icon"); icon.innerHTML = FOLDER_SVG;
  label.appendChild(icon);
  label.appendChild(el("span", "node-name", node.name));
  const count = countFiles(node);
  label.appendChild(el("span", "node-size", `${count} file${count === 1 ? "" : "s"}`));
  label.addEventListener("click", () => toggleFolder(li, twisty));

  row.append(twisty, check, label);
  li.appendChild(row);
  li.appendChild(buildList(node.children));
  return li;
}

function buildFile(node) {
  const li = el("li", "node node-file");
  li.dataset.type = "file";
  li.dataset.id = node.id;
  const row = el("div", "node-row");

  const spacer = el("span", "twisty leaf");
  const check = el("input", "node-check");
  check.type = "checkbox";
  check.checked = true;
  check.dataset.id = node.id;
  check.addEventListener("change", () => { updateAncestors(li); updateSelectionSummary(); });

  const label = el("div", "node-label");
  const icon = el("span", "node-icon"); icon.innerHTML = FILE_SVG;
  label.appendChild(icon);
  label.appendChild(el("span", "node-name", node.name));
  label.title = node.title && node.title !== node.name ? node.title : node.name;
  label.addEventListener("click", () => { check.checked = !check.checked; updateAncestors(li); updateSelectionSummary(); });

  row.append(spacer, check, label);
  li.appendChild(row);
  return li;
}

function countFiles(node) {
  if (node.type === "file") return 1;
  return (node.children || []).reduce((sum, child) => sum + countFiles(child), 0);
}

function toggleFolder(li, twisty) {
  const collapsed = li.classList.toggle("collapsed");
  twisty.classList.toggle("collapsed", collapsed);
}

function setSubtreeChecked(li, checked) {
  $$("input.node-check", li).forEach((cb) => { cb.checked = checked; cb.indeterminate = false; });
}

function folderCheckbox(li) { return li.querySelector(":scope > .node-row > .node-check"); }

function updateFolderState(li) {
  const fileChecks = $$('li[data-type="file"] > .node-row > .node-check', li);
  const total = fileChecks.length;
  const checked = fileChecks.filter((cb) => cb.checked).length;
  const box = folderCheckbox(li);
  if (!box) return;
  box.checked = total > 0 && checked === total;
  box.indeterminate = checked > 0 && checked < total;
}

function updateAncestors(node) {
  const current = node.closest("li");
  let parent = current ? current.parentElement.closest('li[data-type="folder"]') : null;
  while (parent) {
    updateFolderState(parent);
    parent = parent.parentElement.closest('li[data-type="folder"]');
  }
}

function refreshAllFolderStates() {
  // deepest folders first
  const folders = $$('#tree li[data-type="folder"]');
  folders.reverse().forEach(updateFolderState);
}

function selectedIds() {
  return $$('#tree li[data-type="file"] > .node-row > .node-check')
    .filter((cb) => cb.checked)
    .map((cb) => Number(cb.dataset.id));
}

function updateSelectionSummary() {
  const total = state.tree ? state.tree.fileCount : 0;
  const selected = selectedIds().length;
  $("#selection-summary").textContent = `${selected} of ${total} file${total === 1 ? "" : "s"} selected`;
  $("#download-btn").disabled = selected === 0 || state.running;
}

function setAllChecked(checked) {
  $$('#tree input.node-check').forEach((cb) => { cb.checked = checked; cb.indeterminate = false; });
  refreshAllFolderStates();
  updateSelectionSummary();
}

function setAllCollapsed(collapsed) {
  $$('#tree li[data-type="folder"]').forEach((li) => {
    li.classList.toggle("collapsed", collapsed);
    const tw = li.querySelector(":scope > .node-row > .twisty");
    if (tw) tw.classList.toggle("collapsed", collapsed);
  });
}

/* ------------------------------------------------------------------ download */
async function startDownload() {
  const ids = selectedIds();
  if (!ids.length) return;
  const dest = $("#dest-input").value.trim();
  if (!dest) { toast("Choose a download folder first.", true); return; }
  const policy = $("#policy-select").value;

  state.running = true;
  state.errors = [];
  $("#download-btn").disabled = true;
  openProgress(ids.length, dest);

  const result = await Api.start_download(state.course.id, ids, dest, state.course.name, policy)
    .catch((e) => ({ ok: false, error: String(e) }));
  if (!result.ok) {
    closeProgress();
    state.running = false;
    updateSelectionSummary();
    toast(result.error || "Could not start the download.", true);
  }
}

function openProgress(total, dest) {
  $("#progress-title").textContent = "Downloading…";
  $("#progress-fill").style.width = "0%";
  $("#progress-fill").classList.add("indeterminate");
  $("#progress-count").textContent = `0 / ${total} files`;
  $("#progress-speed").textContent = "";
  $("#progress-file").textContent = "Preparing…";
  $("#error-box").hidden = true;
  $("#error-list").innerHTML = "";
  $("#cancel-download").disabled = false;
  $("#cancel-download").textContent = "Cancel";
  $("#progress-overlay").hidden = false;
}

function closeProgress() { $("#progress-overlay").hidden = true; }

function onProgress(p) {
  const fill = $("#progress-fill");
  fill.classList.remove("indeterminate");
  const pct = Math.round((p.fraction || 0) * 100);
  fill.style.width = `${pct}%`;
  let count = `${p.index} / ${p.total} files`;
  if (p.totalBytes) count += `  ·  ${fmtBytes(p.bytes)} / ${fmtBytes(p.totalBytes)}`;
  else if (p.bytes) count += `  ·  ${fmtBytes(p.bytes)}`;
  $("#progress-count").textContent = count;
  $("#progress-speed").textContent = fmtSpeed(p.speed);
  const name = p.path || p.name || "";
  $("#progress-file").textContent = name;
  $("#progress-file").title = name;
}

function onError(e) {
  state.errors.push(e);
  const box = $("#error-box");
  box.hidden = false;
  $("#error-count").textContent = `${state.errors.length} file${state.errors.length === 1 ? "" : "s"} failed`;
  const li = el("li");
  li.appendChild(el("span", "err-file", (e.path || e.name) + ": "));
  li.appendChild(el("span", "err-detail", e.error || "unknown error"));
  $("#error-list").appendChild(li);
  $("#error-list").parentElement.scrollTop = $("#error-list").parentElement.scrollHeight;
}

function onDone(summary) {
  state.running = false;
  closeProgress();
  showDone(summary);
}

function showDone(summary) {
  const overlay = $("#done-overlay");
  const hasErrors = (summary.failed && summary.failed.length) || summary.abortedReason;
  $("#done-icon").classList.toggle("has-errors", !!hasErrors);
  if (summary.cancelled) {
    $("#done-title").textContent = "Download cancelled";
  } else if (summary.abortedReason) {
    $("#done-title").textContent = "Download stopped";
  } else {
    $("#done-title").textContent = "All done!";
  }

  const parts = [];
  parts.push(`Downloaded ${summary.downloaded} file${summary.downloaded === 1 ? "" : "s"}` +
    (summary.bytes ? ` (${fmtBytes(summary.bytes)})` : ""));
  if (summary.skipped) parts.push(`${summary.skipped} already existed and ${summary.skipped === 1 ? "was" : "were"} skipped`);
  if (summary.failed && summary.failed.length) parts.push(`${summary.failed.length} failed`);
  if (summary.cancelled && summary.notAttempted) parts.push(`${summary.notAttempted} not downloaded`);
  $("#done-summary").textContent = parts.join(" · ") + ".";

  const errBox = $("#done-errors");
  if (summary.abortedReason || (summary.failed && summary.failed.length)) {
    errBox.hidden = false;
    errBox.innerHTML = "";
    if (summary.abortedReason) errBox.appendChild(el("div", null, summary.abortedReason));
    (summary.failed || []).forEach((f) => {
      const line = el("div");
      line.appendChild(el("span", "err-file", (f.path || f.name) + ": "));
      line.appendChild(el("span", "err-detail", f.error || "error"));
      errBox.appendChild(line);
    });
  } else {
    errBox.hidden = true;
  }

  overlay.dataset.dest = summary.dest || $("#dest-input").value.trim();
  overlay.hidden = false;
}

function finishDone(reveal) {
  const overlay = $("#done-overlay");
  const dest = overlay.dataset.dest;
  overlay.hidden = true;
  if (reveal && dest) Api.reveal(dest).catch((e) => toast(String(e), true));
  // Return to the home (courses) screen so another course can be chosen.
  state.course = null;
  state.tree = null;
  showScreen("courses");
  $("#course-search").value = "";
  loadCourses();
}

async function cancelDownload() {
  $("#cancel-download").disabled = true;
  $("#cancel-download").textContent = "Cancelling…";
  await Api.cancel_download().catch(() => {});
}

/* ------------------------------------------------------------------ events from python */
window.__bsdlEvent = (msg) => {
  if (!msg || !msg.event) return;
  const p = msg.payload || {};
  switch (msg.event) {
    case "login:status": setMsg($("#login-msg"), p.message || "", "busy"); break;
    case "download:start": break;
    case "download:progress": onProgress(p); break;
    case "download:error": onError(p); break;
    case "download:done": onDone(p); break;
  }
};

/* ------------------------------------------------------------------ wiring */
function wire() {
  $("#connect-btn").addEventListener("click", connect);
  $("#base-url").addEventListener("keydown", (e) => { if (e.key === "Enter") connect(); });
  $("#login-window-btn").addEventListener("click", loginWithWindow);
  $("#cookie-file-btn").addEventListener("click", importCookieFile);
  $("#browser-import-btn").addEventListener("click", importFromBrowser);

  $("#logout-btn").addEventListener("click", async () => {
    await Api.logout().catch(() => {});
    state.courses = [];
    backToLogin("");
    setMsg($("#login-msg"), "Logged out.", "");
  });

  $("#course-search").addEventListener("input", (e) => filterCourses(e.target.value));
  $("#refresh-courses").addEventListener("click", loadCourses);

  $("#back-to-courses").addEventListener("click", () => { state.course = null; showScreen("courses"); });
  $("#select-all").addEventListener("click", () => setAllChecked(true));
  $("#select-none").addEventListener("click", () => setAllChecked(false));
  $("#expand-all").addEventListener("click", () => setAllCollapsed(false));
  $("#collapse-all").addEventListener("click", () => setAllCollapsed(true));

  $("#dest-input").addEventListener("input", updateDestHint);
  $("#browse-dest").addEventListener("click", async () => {
    const result = await Api.pick_folder($("#dest-input").value.trim()).catch((e) => ({ ok: false, error: String(e) }));
    if (result.ok && result.path) { $("#dest-input").value = result.path; updateDestHint(); }
    else if (result.error) toast(result.error, true);
  });
  $("#download-btn").addEventListener("click", startDownload);

  $("#cancel-download").addEventListener("click", cancelDownload);
  $("#done-ok").addEventListener("click", () => finishDone(false));
  $("#done-reveal").addEventListener("click", () => finishDone(true));
}

wire();
boot();
