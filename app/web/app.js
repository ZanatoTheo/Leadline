const state = {
  direction: "startup_to_investors",
  subjectId: null,
  inline: false,
  runId: null,
};

const $ = (id) => document.getElementById(id);

const REASON_LABELS = {
  follower_only: "Only joins rounds — never leads them",
  inactive: "Hasn't led a deal recently",
  stage_mismatch: "Invests at a different stage",
  sector_mismatch: "Focuses on other sectors",
  size_mismatch: "Check size doesn't fit your round",
  out_of_region: "Invests in other regions",
};

// Plain words for the API error codes (shared_context.md section 4.6).
const ERROR_MESSAGES = {
  plugin_not_found: "The live matching plugin isn't installed yet.",
  strategy_not_found: "The live matching strategy file is missing.",
  strategy_not_validated: "The live matching strategy isn't validated yet.",
  model_auth_failed: "The model API key is missing or wrong.",
  model_config_missing: "The model isn't configured yet.",
  model_unavailable: "The model service is down. Try again in a moment.",
  model_bad_request: "The model rejected the request.",
  model_bad_reply: "The model gave an unreadable answer.",
  output_invalid: "The engine's answer didn't match the expected format.",
  all_cases_failed: "Every case failed in the engine.",
  budget_exceeded: "The request used up its usage budget.",
  request_timeout: "The request took too long and was stopped.",
  venus_unavailable: "The live matching engine isn't available.",
  fixture_missing: "A demo data file is missing.",
};

// Errors that mean live mode is broken, so demo mode would work.
const LIVE_HINT_CODES = new Set([
  "plugin_not_found", "strategy_not_found", "strategy_not_validated",
  "model_auth_failed", "model_config_missing", "model_unavailable",
  "model_bad_request", "model_bad_reply", "output_invalid", "all_cases_failed",
  "budget_exceeded", "request_timeout", "venus_unavailable",
]);

async function loadHealth() {
  try {
    const resp = await fetch("/health");
    const h = await resp.json();
    const ds = h.dataset_source || "unknown";
    const badge = $("dataset-badge");
    badge.textContent = `dataset: ${ds}`;
    badge.className = "badge " + (ds === "cala" ? "badge-lead" : "badge-mock");
    if (h.dataset_reason) badge.title = h.dataset_reason;
    if (h.venus_mode === "mock") $("mock-badge").classList.remove("hidden");
  } catch {
    // Server down or /health unreachable: leave badges hidden; run() shows the error.
  }
}

function setDirection(dir) {
  state.direction = dir;
  state.subjectId = null;
  state.inline = false;
  $("tab-raising").classList.toggle("active", dir === "startup_to_investors");
  $("tab-investing").classList.toggle("active", dir !== "startup_to_investors");
  $("tab-raising").setAttribute("aria-selected", dir === "startup_to_investors");
  $("tab-investing").setAttribute("aria-selected", dir !== "startup_to_investors");
  $("subject-heading").textContent = dir === "startup_to_investors" ? "Your company" : "Your fund";
  $("inline-form").classList.toggle("hidden", dir !== "startup_to_investors");
  $("search").value = "";
  $("search").placeholder = dir === "startup_to_investors" ? "Your company name…" : "Your fund name…";
  $("go").textContent = dir === "startup_to_investors" ? "Find my leads" : "Find startups";
  clearPicked();
  clearResults();
}

function clearPicked() {
  state.subjectId = null;
  $("picked").classList.add("hidden");
  $("go").disabled = true;
}

function pick(item) {
  state.subjectId = item.id;
  $("picked-name").textContent = item.name;
  $("picked").classList.remove("hidden");
  $("search-results").classList.add("hidden");
  $("search").value = "";
  $("go").disabled = false;
}

function clearResults() {
  $("results").classList.add("hidden");
  $("warnings").classList.add("hidden");
  $("state").textContent = "";
  $("state").className = "state";
}

let searchTimer = null;
async function onSearch() {
  const q = $("search").value.trim();
  clearTimeout(searchTimer);
  if (q.length < 2) { $("search-results").classList.add("hidden"); return; }
  searchTimer = setTimeout(async () => {
    const endpoint = state.direction === "startup_to_investors" ? "/api/companies" : "/api/investors";
    try {
      const resp = await fetch(`${endpoint}?q=${encodeURIComponent(q)}`);
      const items = await resp.json();
      renderSearchResults(items);
    } catch {
      $("search-results").classList.add("hidden");
    }
  }, 200);
}

function renderSearchResults(items) {
  const ul = $("search-results");
  ul.innerHTML = "";
  if (!items.length) { ul.classList.add("hidden"); return; }
  for (const item of items.slice(0, 8)) {
    const li = document.createElement("li");
    const sub = item.country ? ` — ${item.country}` : "";
    li.innerHTML = `${escapeHtml(item.name)}<span class="sub">${escapeHtml(
      (item.description || item.kind || "").slice(0, 60) + sub
    )}</span>`;
    li.addEventListener("click", () => pick(item));
    ul.appendChild(li);
  }
  ul.classList.remove("hidden");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// "2025-09-12" -> "14 months ago" (against today; falls back to the raw date).
function timeAgo(dateStr) {
  const then = new Date(dateStr + "T00:00:00");
  if (isNaN(then)) return dateStr;
  const days = Math.round((Date.now() - then.getTime()) / 86400000);
  if (days < 0) return dateStr;
  if (days < 14) return days <= 1 ? "yesterday" : `${days} days ago`;
  if (days < 60) return `${Math.round(days / 7)} weeks ago`;
  if (days < 730) return `${Math.round(days / 30)} months ago`;
  return `${Math.round(days / 365)} years ago`;
}

function buildRequest() {
  const req = {
    direction: state.direction,
    top_k: 10,
    as_of: $("as-of").value || new Date().toISOString().slice(0, 10),
    filters: {},
    live_check: true,
  };
  const countries = $("filter-countries").value.split(",").map((s) => s.trim()).filter(Boolean);
  if (countries.length) req.filters.countries = countries;
  const stages = [...$("filter-stages").selectedOptions].map((o) => o.value);
  if (stages.length) req.filters.stages = stages;

  if (state.subjectId) {
    req.subject_id = state.subjectId;
  } else if (state.direction === "startup_to_investors" && $("f-name").value.trim()) {
    req.subject = {
      id: "inline:" + $("f-name").value.trim(),
      name: $("f-name").value.trim(),
      description: $("f-desc").value.trim(),
      country: $("f-country").value.trim() || null,
      stage: $("f-stage").value,
      sectors: $("f-sectors").value.split(",").map((s) => s.trim()).filter(Boolean),
    };
  }
  return req;
}

async function run() {
  clearResults();
  const req = buildRequest();
  if (!req.subject_id && !req.subject) return;
  $("state").innerHTML = '<span class="spinner" aria-hidden="true"></span> Finding leads…';
  $("go").disabled = true;
  try {
    const resp = await fetch("/api/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
    const data = await resp.json();
    if (!resp.ok) {
      const code = data.error && data.error.code;
      const msg = (data.error && data.error.message) || data.detail?.message || `Error ${resp.status}`;
      showError(msg, code);
      return;
    }
    renderResult(data);
  } catch (e) {
    showError("Could not reach the API. Is the server running?");
  } finally {
    $("go").disabled = false;
  }
}

function showError(msg, code) {
  const el = $("state");
  el.textContent = "";
  const friendly = (code && ERROR_MESSAGES[code]) || msg;
  const p = document.createElement("p");
  p.textContent = friendly;
  el.appendChild(p);
  if (code && LIVE_HINT_CODES.has(code)) {
    const hint = document.createElement("p");
    hint.className = "error-hint";
    hint.textContent = "This is a live-mode error. To keep demoing: set VENUS_MODE=mock in .env and restart the server.";
    el.appendChild(hint);
  }
  if (code && ERROR_MESSAGES[code] && msg && msg !== friendly) {
    const detail = document.createElement("p");
    detail.className = "error-detail";
    detail.textContent = msg;
    el.appendChild(detail);
  }
  el.className = "state error";
}

function renderResult(data) {
  $("state").textContent = "";
  if (data.source === "mock") $("mock-badge").classList.remove("hidden");

  if (data.warnings && data.warnings.length) {
    const w = $("warnings");
    w.innerHTML = (data.status === "partial" ? "Some data is incomplete: " : "Heads up: ")
      + data.warnings.map(escapeHtml).join("; ");
    w.classList.remove("hidden");
  }
  if (data.status === "error") {
    showError((data.warnings || []).join("; ") || "The matching engine returned an error.");
    return;
  }

  state.runId = data.run_id;
  $("csv-link").href = `/api/export.csv?run_id=${encodeURIComponent(data.run_id)}`;

  const list = $("match-list");
  list.innerHTML = "";
  const evidenceById = {};
  for (const ev of data.evidence || []) evidenceById[ev.id] = ev;

  if (!data.matches || !data.matches.length) {
    $("state").textContent = "No matches found. Try widening your filters.";
    return;
  }

  for (const m of data.matches) {
    list.appendChild(matchCard(m, evidenceById));
  }
  $("results").classList.remove("hidden");

  if (data.rejected && data.rejected.length) {
    const rl = $("rejected-list");
    rl.innerHTML = "";
    for (const r of data.rejected) {
      const li = document.createElement("li");
      const label = REASON_LABELS[r.reason] || r.reason;
      li.innerHTML = `<span class="code">${escapeHtml(label)}</span> — ${escapeHtml(r.detail || "")}`;
      rl.appendChild(li);
    }
    $("why-not").classList.remove("hidden");
  }
}

function matchCard(m, evidenceById) {
  const li = document.createElement("li");
  li.className = "match-card";

  const roleClass = m.role === "lead" ? "badge-lead" : "badge-participant";
  const active = m.active || {};
  const confClass = `badge-conf-${m.confidence || "medium"}`;
  const lastLead = active.last_lead_date
    ? ` · last lead <span title="${escapeHtml(active.last_lead_date)}">${escapeHtml(timeAgo(active.last_lead_date))}</span>`
    : "";

  const reasons = (m.reasons || []).slice(0, 3).map((r) => {
    const links = (r.evidence || []).map((eid) => {
      const ev = evidenceById[eid];
      if (!ev) return "";
      const href = ev.url || "#";
      const label = ev.kind === "web" ? "web" : "Cala";
      const title = escapeHtml([ev.ref, ev.quote].filter(Boolean).join(" — "));
      return ` <a class="ev-link ev-${ev.kind === "web" ? "web" : "cala"}" href="${escapeHtml(href)}" title="${title}">[${label}]</a>`;
    }).join("");
    return `<li>${escapeHtml(r.text)}${links}</li>`;
  }).join("");

  li.innerHTML = `
    <div class="match-head">
      <span class="rank">#${m.rank}</span>
      <span class="match-name">${escapeHtml(m.candidate_name || m.candidate_id)}</span>
      <span class="badge ${roleClass}">${escapeHtml(m.role)}</span>
      <span class="badge badge-active">${escapeHtml(active.status || "unknown")}${lastLead}</span>
      <span class="badge ${confClass}">${escapeHtml(m.confidence || "")} confidence</span>
    </div>
    <div class="score-bar"><div class="score-fill" style="width:${Math.round((m.score || 0) * 100)}%"></div></div>
    <ul class="reasons">${reasons}</ul>`;
  return li;
}

$("tab-raising").addEventListener("click", () => setDirection("startup_to_investors"));
$("tab-investing").addEventListener("click", () => setDirection("investor_to_startups"));
$("search").addEventListener("input", onSearch);
$("clear-picked").addEventListener("click", clearPicked);
$("go").addEventListener("click", run);
$("as-of").value = new Date().toISOString().slice(0, 10);
loadHealth();
