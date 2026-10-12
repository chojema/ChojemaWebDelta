"use strict";

const POLL_INTERVAL_MS = 600;
const STATUS_LABELS = {
  changed: "변경됨",
  unchanged: "변경 없음",
  error: "점검 실패",
  new: "기준 저장됨",
  idle: "점검 전",
};
// 눈에 먼저 띄어야 하는 순서
const STATUS_ORDER = ["changed", "error", "new", "idle", "unchanged"];
const SORT_STORAGE_KEY = "chojema-webdelta-sort";
// 자동 확인 주기의 기본 목록(초). 0은 끔.
const AUTO_PRESETS = [0, 60, 300, 600, 1800, 3600, 7200, 86400, 604800];
const SHORT_INTERVAL_SECONDS = 300;
const SORTERS = {
  status: (a, b) => STATUS_ORDER.indexOf(statusOf(a)) - STATUS_ORDER.indexOf(statusOf(b)) || a.id - b.id,
  newest: (a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id,
  oldest: (a, b) => a.created_at.localeCompare(b.created_at) || a.id - b.id,
  name: (a, b) => a.name.localeCompare(b.name, "ko") || a.id - b.id,
};
// 편집 창에 보여 주는 영역(CSS 선택자) 예시. tests/test_app.py의 SelectorExamplesTest가 같은 선택자를 검증한다.
const SELECTOR_EXAMPLES = [
  { pattern: "#content", label: "id가 content인 것", sample: '<div id="content">' },
  { pattern: ".board-list", label: "class에 board-list가 있는 것", sample: '<ul class="board-list">' },
  { pattern: "a.Link--primary", label: "태그와 class를 함께", sample: '<a class="Link--primary Link">' },
  { pattern: 'a[href^="/releases/tag/"]', label: "주소가 이 글자로 시작하는 링크", sample: '<a href="/releases/tag/v1.0">' },
  { pattern: "#content .title", label: "#content 안에 있는 .title", sample: "" },
  { pattern: "#notice, #schedule", label: "두 영역을 함께", sample: "" },
];
// 편집 창에 보여 주는 무시 패턴 예시. tests/test_app.py의 IgnorePatternExamplesTest가 같은 패턴을 검증한다.
const IGNORE_EXAMPLES = [
  { pattern: "조회수?\\s*:?\\s*[\\d,]+", label: "조회수", sample: "조회 1,234 / 조회수: 56" },
  { pattern: "\\d{4}[-./]\\s?\\d{1,2}[-./]\\s?\\d{1,2}\\.?", label: "날짜", sample: "2026-10-12 / 2026. 10. 12." },
  { pattern: "\\d{1,2}:\\d{2}(:\\d{2})?", label: "시각", sample: "09:05 / 09:05:30" },
  { pattern: "\\d+\\s*(초|분|시간|일)\\s*전", label: "지난 시간", sample: "3분 전 / 2 시간 전" },
  { pattern: "(댓글|추천|좋아요)\\s*\\(?[\\d,]+\\)?", label: "댓글·추천 수", sample: "댓글 (12) / 추천 3" },
  { pattern: "^.*광고.*$", label: "특정 낱말이 든 줄 전체", sample: "'광고'가 들어간 줄" },
  { pattern: "^오늘 방문자.*$", label: "특정 말로 시작하는 줄 전체", sample: "오늘 방문자 1,024명" },
  { pattern: "(?i)copyright.*$", label: "영문 대소문자 구분 없이, 그 뒤 끝까지", sample: "Copyright © 2026 …" },
];

const $ = (id) => document.getElementById(id);
const dialog = $("site-dialog");
const form = $("site-form");

let state = {
  sites: [],
  job: { running: false, total: 0, done: 0, checking: [] },
  auto: { interval_seconds: 0, next_check_at: null },
};
let lastRendered = "";
let pollTimer = null;
let autoRefreshTimer = null;
let editingId = null;
let confirmingDeleteId = null;
let sortKey = loadSortKey();
const openDiffs = new Set();
const selected = new Set();

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.append(child);
  return node;
}

async function api(method, path, body) {
  const options = { method, headers: {} };
  if (method !== "GET") {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body ?? {});
  }
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `요청 실패 (${response.status})`);
  return data;
}

// 정렬 선택은 이 브라우저에만 기억한다. 저장소를 못 쓰는 환경에서도 화면은 그대로 동작해야 한다.
function loadSortKey() {
  try {
    const saved = localStorage.getItem(SORT_STORAGE_KEY);
    if (saved in SORTERS) return saved;
  } catch (error) { /* 기본값 사용 */ }
  return "status";
}

function saveSortKey() {
  try {
    localStorage.setItem(SORT_STORAGE_KEY, sortKey);
  } catch (error) { /* 기억하지 못해도 정렬은 적용된다 */ }
}

function statusOf(site) {
  return site.status || "idle";
}

function formatInterval(seconds) {
  if (!seconds) return "끔";
  if (seconds === 604800) return "1주일";
  const units = [[86400, "일"], [3600, "시간"], [60, "분"], [1, "초"]];
  const parts = [];
  let rest = seconds;
  for (const [size, label] of units) {
    const count = Math.floor(rest / size);
    if (count) parts.push(`${count}${label}`);
    rest -= count * size;
  }
  return parts.join(" ");
}

function formatTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("ko-KR", {
    month: "long", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function showNotice(message, kind = "error") {
  $("notice").textContent = message || "";
  $("notice").className = `notice ${kind}`;
  $("notice").hidden = !message;
}

async function refresh() {
  try {
    state = await api("GET", "/api/state");
  } catch (error) {
    stopPolling();
    showNotice("앱과 연결이 끊겼습니다. 앱을 다시 실행한 뒤 이 화면을 새로 고치세요.");
    return;
  }
  render();
  if (state.job.running) startPolling();
  else stopPolling();
  scheduleAutoRefresh();
}

// 자동 확인은 앱이 스스로 시작하므로, 예정 시각에 맞춰 화면이 상태를 다시 읽어 온다.
function scheduleAutoRefresh() {
  clearTimeout(autoRefreshTimer);
  const nextAt = state.auto.next_check_at;
  if (!nextAt || state.job.running) return;
  const delay = Math.max(1000, new Date(nextAt).getTime() - Date.now() + 700);
  autoRefreshTimer = setTimeout(refresh, Math.min(delay, 2 ** 31 - 1));
}

function startPolling() {
  if (pollTimer === null) pollTimer = setInterval(refresh, POLL_INTERVAL_MS);
}

function stopPolling() {
  clearInterval(pollTimer);
  pollTimer = null;
}

// action이 문자열을 돌려주면 완료 안내로 보여 준다.
async function act(action) {
  showNotice("");
  let notice = null;
  try {
    const result = await action();
    if (typeof result === "string") notice = [result, "info"];
  } catch (error) {
    notice = [error.message, "error"];
  }
  await refresh();
  if (notice) showNotice(...notice);
}

function confirmDelete(title, text) {
  $("confirm-title").textContent = title;
  $("confirm-text").textContent = text;
  const box = $("confirm-dialog");
  return new Promise((resolve) => {
    box.addEventListener("close", () => resolve(box.returnValue === "ok"), { once: true });
    box.returnValue = "cancel";
    box.showModal();
  });
}

function render() {
  const liveIds = new Set(state.sites.map((site) => site.id));
  for (const id of selected) if (!liveIds.has(id)) selected.delete(id);
  const fingerprint = JSON.stringify(
    [state, [...openDiffs], confirmingDeleteId, sortKey, [...selected]],
  );
  if (fingerprint === lastRendered) return;
  lastRendered = fingerprint;

  const { sites, job } = state;
  $("version").textContent = `v${state.version}`;
  $("data-dir").textContent = state.data_dir;
  $("data-dir").parentElement.title = state.data_dir;

  const { interval_seconds: autoInterval, next_check_at: nextCheckAt } = state.auto;
  // 꺼져 있을 때는 상태("끔")가 아니라 누르면 일어날 일("켜기")을 적는다.
  $("auto").textContent = autoInterval ? `자동 확인: ${formatInterval(autoInterval)}` : "자동 확인 켜기";
  $("auto-status").hidden = !autoInterval;
  if (autoInterval) {
    const next = new Date(nextCheckAt).toLocaleTimeString("ko-KR", {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    const nextDay = new Date(nextCheckAt).toDateString() === new Date().toDateString()
      ? "" : `${formatTime(nextCheckAt).split(" 오")[0]} `;
    $("auto-status").textContent =
      `${formatInterval(autoInterval)}마다 자동 확인 · 다음 확인 ${nextDay}${next}`;
  }

  $("check-all").disabled = job.running || sites.length === 0;
  $("check-all").textContent = job.running ? `확인하는 중… ${job.done}/${job.total}` : "변경 확인";
  $("progress").hidden = !job.running;
  if (job.running) {
    const ratio = job.total ? job.done / job.total : 0;
    $("progress-fill").style.width = `${Math.round(ratio * 100)}%`;
  }

  const counts = {};
  for (const site of sites) counts[statusOf(site)] = (counts[statusOf(site)] || 0) + 1;
  const countBadges = [el("span", { class: "badge", text: `전체 ${sites.length}` })];
  for (const status of STATUS_ORDER) {
    if (counts[status]) {
      countBadges.push(el("span", {
        class: `badge ${status}`, text: `${STATUS_LABELS[status]} ${counts[status]}`,
      }));
    }
  }
  $("counts").replaceChildren(...(sites.length ? countBadges : []));
  $("ack-all").hidden = !counts.changed || job.running;

  $("sort").value = sortKey;
  $("sort").parentElement.hidden = sites.length < 2;
  $("sites").replaceChildren(...[...sites].sort(SORTERS[sortKey]).map(renderSite));
  $("empty").hidden = sites.length > 0;

  $("export").disabled = sites.length === 0;
  $("delete-all").disabled = sites.length === 0;
  $("selection").hidden = selected.size === 0;
  $("selection-count").textContent = `${selected.size}개 선택됨`;
  $("select-all").checked = selected.size === sites.length;
  $("select-all").indeterminate = selected.size > 0 && selected.size < sites.length;
}

function renderSite(site) {
  const status = statusOf(site);
  const checking = state.job.checking.includes(site.id);
  const busy = state.job.running;

  const pick = el("input", {
    class: "pick", type: "checkbox", "aria-label": `${site.name} 선택`,
    onchange: (event) => {
      event.target.checked ? selected.add(site.id) : selected.delete(site.id);
      render();
    },
  });
  pick.checked = selected.has(site.id);

  const head = el("div", { class: "site-head" }, [
    pick,
    el("span", { class: `badge ${status}`, text: checking ? "확인하는 중…" : STATUS_LABELS[status] }),
    el("a", {
      class: "site-name", href: site.url, target: "_blank", rel: "noopener noreferrer",
      title: "새 탭에서 페이지 열기", text: site.name,
    }),
  ]);
  if (status === "changed") {
    const added = site.diff.filter((line) => line.kind === "add").length;
    const removed = site.diff.filter((line) => line.kind === "del").length;
    head.append(el("span", { class: "muted", text: `추가 ${added}줄 · 삭제 ${removed}줄` }));
  }

  // 카드는 두 줄: 윗줄에 상태·이름·버튼, 아랫줄에 주소와 부가 정보.
  const metaParts = [site.url];
  if (site.selector) metaParts.push(`영역: ${site.selector}`);
  if (site.last_checked_at) metaParts.push(`마지막 점검 ${formatTime(site.last_checked_at)}`);
  if (sortKey === "newest" || sortKey === "oldest") metaParts.push(`추가 ${formatTime(site.created_at)}`);
  const meta = el("div", { class: "site-meta muted", title: site.url });
  if (status === "error" && site.last_error) {
    meta.append(el("span", { class: "site-error", text: site.last_error }), " · ");
  }
  meta.append(metaParts.join(" · "));
  const item = el("li", { class: `site ${status}` }, [head, meta]);

  if (status === "changed") {
    const open = openDiffs.has(site.id);
    head.append(
      el("button", {
        class: "small", type: "button", text: open ? "변경 내용 접기" : "변경 내용 보기",
        onclick: () => { open ? openDiffs.delete(site.id) : openDiffs.add(site.id); render(); },
      }),
      el("button", {
        class: "small", type: "button", text: "확인함", title: "현재 상태를 새 기준으로 삼습니다",
        onclick: () => act(() => api("POST", `/api/sites/${site.id}/ack`)),
      }),
    );
  }
  head.append(
    el("span", { class: "spacer" }),
    el("button", {
      class: "small quiet", type: "button", text: "점검", title: "이 사이트만 다시 확인",
      ...(busy ? { disabled: "" } : {}),
      onclick: () => act(() => api("POST", "/api/check", { site_ids: [site.id] })),
    }),
    el("button", {
      class: "small quiet", type: "button", text: "편집", onclick: () => openDialog(site),
    }),
  );
  if (confirmingDeleteId === site.id) {
    head.append(
      el("button", {
        class: "small danger", type: "button", text: "정말 삭제",
        onclick: () => { confirmingDeleteId = null; act(() => api("DELETE", `/api/sites/${site.id}`)); },
      }),
      el("button", {
        class: "small quiet", type: "button", text: "취소",
        onclick: () => { confirmingDeleteId = null; render(); },
      }),
    );
  } else {
    head.append(el("button", {
      class: "small quiet", type: "button", text: "삭제",
      onclick: () => { confirmingDeleteId = site.id; render(); },
    }));
  }
  if (status === "changed" && openDiffs.has(site.id)) item.append(renderDiff(site));
  return item;
}

function renderDiff(site) {
  const marks = { add: "+", del: "−", ctx: " " };
  const box = el("div", { class: "diff" });
  if (site.diff.length === 0) {
    box.append(el("div", { class: "diff-note", text: "표시할 차이가 없습니다." }));
  }
  for (const line of site.diff) {
    if (line.kind === "gap") {
      box.append(el("div", { class: "diff-line gap", text: "⋯" }));
      continue;
    }
    box.append(el("div", { class: `diff-line ${line.kind}` }, [
      el("span", { class: "mark", text: marks[line.kind] }),
      el("span", { text: line.text }),
    ]));
  }
  if (site.diff_truncated) {
    box.append(el("div", { class: "diff-note", text: "변경이 많아 앞부분만 표시했습니다." }));
  }
  return box;
}

function openDialog(site) {
  editingId = site ? site.id : null;
  $("dialog-title").textContent = site ? "사이트 편집" : "사이트 추가";
  form.reset();
  if (site) {
    for (const name of ["url", "name", "selector", "ignore_patterns"]) {
      form.elements[name].value = site[name];
    }
  }
  $("form-error").hidden = true;
  dialog.showModal();
}

function addIgnorePattern(pattern) {
  const field = form.elements.ignore_patterns;
  const lines = field.value.split("\n").filter((line) => line.trim());
  if (!lines.includes(pattern)) lines.push(pattern);
  field.value = lines.join("\n");
  field.rows = Math.max(3, lines.length);
}

function addSelector(selector) {
  const field = form.elements.selector;
  const parts = field.value.split(",").map((part) => part.trim()).filter(Boolean);
  for (const part of selector.split(",").map((piece) => piece.trim())) {
    if (!parts.includes(part)) parts.push(part);
  }
  field.value = parts.join(", ");
}

function renderExamples(listId, examples, onPick) {
  $(listId).replaceChildren(...examples.map((example) => el("li", {}, [
    el("button", {
      class: "example", type: "button", text: example.pattern, title: "눌러서 추가",
      onclick: () => onPick(example.pattern),
    }),
    el("span", { text: example.label }),
    el("span", { class: "muted", text: example.sample }),
  ])));
}

renderExamples("selector-examples", SELECTOR_EXAMPLES, addSelector);
renderExamples("pattern-examples", IGNORE_EXAMPLES, addIgnorePattern);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const fields = Object.fromEntries(new FormData(form));
  try {
    if (editingId === null) await api("POST", "/api/sites", fields);
    else await api("PUT", `/api/sites/${editingId}`, fields);
  } catch (error) {
    $("form-error").textContent = error.message;
    $("form-error").hidden = false;
    return;
  }
  dialog.close();
  await refresh();
});

function closeManageMenu() {
  $("manage").open = false;
}

async function exportSites() {
  const data = await api("GET", "/api/export");
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const stamp = data.exported_at.slice(0, 10).replaceAll("-", "");
  const link = el("a", { href: url, download: `chojema-webdelta-sites-${stamp}.json` });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return `사이트 ${data.sites.length}개를 파일로 내보냈습니다. 브라우저의 다운로드 폴더를 확인하세요.`;
}

// 내보낸 JSON 파일, 또는 한 줄에 주소 하나씩 적은 텍스트 파일을 받는다.
function parseImportFile(text) {
  const trimmed = text.trim();
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    let data;
    try {
      data = JSON.parse(trimmed);
    } catch (error) {
      throw new Error("파일의 JSON 형식이 올바르지 않습니다.");
    }
    const sites = Array.isArray(data) ? data : data.sites;
    if (!Array.isArray(sites)) throw new Error("사이트 목록이 들어 있지 않은 파일입니다.");
    return sites;
  }
  return trimmed.split("\n")
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"))
    .map((url) => ({ url }));
}

async function importSites(file) {
  const sites = parseImportFile(await file.text());
  if (sites.length === 0) throw new Error("파일에 가져올 사이트가 없습니다.");
  const result = await api("POST", "/api/import", { sites });
  const parts = [`사이트 ${result.added}개를 추가했습니다.`];
  if (result.skipped) parts.push(`이미 있는 ${result.skipped}개는 건너뛰었습니다.`);
  if (result.errors.length) {
    const first = result.errors[0];
    parts.push(
      `${result.errors.length}개는 넣지 못했습니다 (${first.position}번째 항목: ${first.error})`,
    );
    if (result.added === 0) throw new Error(parts.slice(1).join(" "));
  }
  return parts.join(" ");
}

$("export").addEventListener("click", () => { closeManageMenu(); act(exportSites); });
$("import").addEventListener("click", () => { closeManageMenu(); $("import-file").click(); });
$("import-file").addEventListener("change", (event) => {
  const [file] = event.target.files;
  event.target.value = "";  // 같은 파일을 다시 골라도 change가 일어나게 한다.
  if (file) act(() => importSites(file));
});
$("delete-all").addEventListener("click", async () => {
  closeManageMenu();
  const count = state.sites.length;
  const confirmed = await confirmDelete(
    `사이트 ${count}개를 모두 삭제할까요?`,
    "등록한 사이트와 저장된 비교 기준이 모두 지워지며 되돌릴 수 없습니다. "
      + "나중에 다시 쓰려면 먼저 '내보내기'로 목록을 저장해 두세요.",
  );
  if (!confirmed) return;
  act(async () => {
    const result = await api("POST", "/api/sites/delete", { all: true });
    return `사이트 ${result.deleted}개를 삭제했습니다.`;
  });
});
document.addEventListener("click", (event) => {
  if (!$("manage").contains(event.target)) closeManageMenu();
});

$("select-all").addEventListener("change", (event) => {
  selected.clear();
  if (event.target.checked) for (const site of state.sites) selected.add(site.id);
  render();
});
$("selection-clear").addEventListener("click", () => { selected.clear(); render(); });
$("selection-delete").addEventListener("click", async () => {
  const ids = [...selected];
  const confirmed = await confirmDelete(
    `선택한 사이트 ${ids.length}개를 삭제할까요?`,
    "선택한 사이트와 저장된 비교 기준이 지워지며 되돌릴 수 없습니다.",
  );
  if (!confirmed) return;
  act(async () => {
    const result = await api("POST", "/api/sites/delete", { site_ids: ids });
    return `사이트 ${result.deleted}개를 삭제했습니다.`;
  });
});

const autoDialog = $("auto-dialog");
const autoForm = $("auto-form");

$("auto-options").replaceChildren(...AUTO_PRESETS.map((seconds) => el("label", { class: "option" }, [
  el("input", { type: "radio", name: "interval", value: String(seconds) }),
  seconds ? formatInterval(seconds) : "끔",
])));

function chosenAutoInterval() {
  const choice = new FormData(autoForm).get("interval");
  if (choice !== "custom") return Number(choice);
  return Number($("auto-custom-value").value) * Number($("auto-custom-unit").value);
}

function updateAutoWarning() {
  const seconds = chosenAutoInterval();
  $("auto-warning").classList.toggle("strong", seconds > 0 && seconds <= SHORT_INTERVAL_SECONDS);
}

function openAutoDialog() {
  const current = state.auto.interval_seconds;
  const preset = AUTO_PRESETS.includes(current);
  autoForm.elements.interval.value = preset ? String(current) : "custom";
  if (!preset) {
    // 나누어떨어지는 가장 큰 단위로 보여 준다. 예: 5400초 → 90분
    const unit = [86400, 3600, 60].find((size) => current % size === 0) || 60;
    $("auto-custom-value").value = Math.max(1, Math.round(current / unit));
    $("auto-custom-unit").value = String(unit);
  }
  $("auto-error").hidden = true;
  updateAutoWarning();
  autoDialog.showModal();
}

autoForm.addEventListener("input", updateAutoWarning);
for (const id of ["auto-custom-value", "auto-custom-unit"]) {
  $(id).addEventListener("focus", () => {
    autoForm.elements.interval.value = "custom";
    updateAutoWarning();
  });
}
autoForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const seconds = chosenAutoInterval();
  try {
    if (!Number.isInteger(seconds) || seconds < 0) throw new Error("간격은 1 이상의 정수로 입력하세요.");
    await api("POST", "/api/auto", { interval_seconds: seconds });
  } catch (error) {
    $("auto-error").textContent = error.message;
    $("auto-error").hidden = false;
    return;
  }
  autoDialog.close();
  await refresh();
});
$("auto").addEventListener("click", openAutoDialog);
$("auto-cancel").addEventListener("click", () => autoDialog.close());
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();  // 숨은 탭에서는 타이머가 늦어지므로 돌아왔을 때 맞춘다.
});

$("sort").addEventListener("change", (event) => {
  sortKey = event.target.value;
  saveSortKey();
  render();
});
$("dialog-cancel").addEventListener("click", () => dialog.close());
$("add-site").addEventListener("click", () => openDialog(null));
$("check-all").addEventListener("click", () => act(() => api("POST", "/api/check")));
$("ack-all").addEventListener("click", () => act(() => api("POST", "/api/ack")));
$("quit").addEventListener("click", async () => {
  stopPolling();
  try {
    await api("POST", "/api/quit");
  } catch (error) {
    // 서버가 응답 도중 내려가도 종료된 것으로 본다.
  }
  $("overlay-text").textContent = "ChojemaWebDelta를 종료했습니다. 이 탭은 닫아도 됩니다.";
  $("overlay").hidden = false;
});

function tickClock() {
  const now = new Date();
  const date = now.toLocaleDateString("ko-KR", {
    year: "numeric", month: "long", day: "numeric", weekday: "long",
  });
  const time = now.toLocaleTimeString("ko-KR", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  $("clock").textContent = `${date} ${time}`;
  $("year").textContent = now.getFullYear();
}

tickClock();
setInterval(tickClock, 1000);
refresh();
