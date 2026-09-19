const csrf = document.querySelector('meta[name="csrf-token"]').content;
const state = {
  snapshot: null,
  diarySeason: "",
  diaryDay: "",
  reviewSeason: "",
  reviewDay: "1",
  openDetailKeys: new Set(),
};
const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  })[character]);
}

function humanize(value) {
  return String(value ?? "Unknown").toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function badge(value) {
  const status = String(value ?? "UNKNOWN");
  const tone = ["RUNNING", "ARMED", "COMPLETED", "PUBLISHED", "WRITTEN", "ACTIVE", "CLEARED"].includes(status)
    ? "good"
    : ["RECOVERY_REQUIRED", "DEPARTED", "MISSING", "REVIEW_REQUIRED"].includes(status)
      ? "alert"
      : ["WAITING_FOR_MODEL", "QUEUED", "EXPECTED", "LATE", "AWAITING_PUBLISH_REVIEW"].includes(status)
        ? "warm" : "muted";
  return `<span class="badge badge-${tone}">${escapeHtml(humanize(status))}</span>`;
}

function dateLabel(value, includeDate = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return escapeHtml(value);
  const options = includeDate
    ? { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }
    : { hour: "numeric", minute: "2-digit" };
  return escapeHtml(new Intl.DateTimeFormat(undefined, options).format(date));
}

function count(counts, key) { return Number((counts || {})[key] || 0); }
function total(counts) { return Object.values(counts || {}).reduce((sum, value) => sum + Number(value || 0), 0); }
function resolvedRuns(counts) { return count(counts, "COMPLETED") + count(counts, "SKIPPED"); }
function activeSeason(snapshot) {
  const seasons = snapshot?.seasons || [];
  const activeId = (snapshot?.active_season_ids || [])[0];
  return seasons.find((season) => season.season_id === activeId) || seasons[0] || null;
}

function detailMarkup(key, label, content, className = "") {
  if (!content) return "";
  const open = state.openDetailKeys.has(key) ? " open" : "";
  const classAttribute = className ? ` class="${escapeHtml(className)}"` : "";
  return `<details${classAttribute} data-detail-key="${escapeHtml(key)}"${open}><summary>${escapeHtml(label)}</summary><pre class="diary-copy">${escapeHtml(content)}</pre></details>`;
}

function bindDetailState(container) {
  container.querySelectorAll("details[data-detail-key]").forEach((detail) => {
    detail.addEventListener("toggle", () => {
      const key = detail.dataset.detailKey;
      if (!key) return;
      if (detail.open) state.openDetailKeys.add(key);
      else state.openDetailKeys.delete(key);
    });
  });
}

function diaryReviewCard(diary, keyPrefix) {
  const privateAttempt = diary.review_source !== "ACCEPTED_DIARY";
  const reviewNote = privateAttempt
    ? diary.wellness_flag
      ? '<p class="review-flag">Wellness flag retained privately. This is owner-only review output and is not accepted or publishable diary text.</p>'
      : '<p class="review-note">Private model output retained for review; it is not accepted or publishable diary text.</p>'
    : '';
  const sourceNote = privateAttempt
    ? `<p class="review-note">${escapeHtml(humanize(diary.review_source))}${diary.model_attempt ? ` · attempt ${escapeHtml(diary.model_attempt)}` : ""}</p>`
    : "";
  const content = diary.content
    ? detailMarkup(`${keyPrefix}:${diary.diary_id}:content`, privateAttempt ? "Read private review output" : "Read private entry", diary.content)
    : '<p class="faint">No readable private content has been recorded for this entry.</p>';
  const raw = diary.raw_output && diary.raw_output !== diary.content
    ? detailMarkup(`${keyPrefix}:${diary.diary_id}:raw`, "Inspect raw private model output", diary.raw_output)
    : "";
  return `<article class="diary-entry ${privateAttempt ? "review-private" : ""}"><div class="diary-top"><div><p class="eyebrow">Day ${escapeHtml(diary.day_number)} · ${escapeHtml(diary.character_id)}</p><h3>${escapeHtml(diary.word_count ? `${diary.word_count} words` : privateAttempt ? "Private diary attempt" : "Diary entry")}</h3></div>${badge(diary.status)}</div>${diary.late ? '<p>Written after the scheduled cutoff; the original day is preserved.</p>' : ""}${sourceNote}${reviewNote}${content}${raw}</article>`;
}

function setConnection(online, label) {
  const node = $("#connection");
  node.classList.toggle("is-live", online);
  node.classList.toggle("is-error", !online);
  $("#connection-label").textContent = label;
}

function renderMetrics(snapshot) {
  const season = activeSeason(snapshot);
  const runs = season?.run_counts || snapshot.runs?.by_status || {};
  const runTotal = total(runs);
  const done = resolvedRuns(runs);
  const next = season?.next_run;
  const recoveries = snapshot.recoveries || [];
  const unread = Number(snapshot.notifications?.unread || 0);
  $("#metric-state").textContent = season ? humanize(season.status) : "No season";
  $("#metric-state-detail").textContent = season ? `${season.season_id} · ${season.title || "Untitled season"}` : "Waiting for a season record";
  $("#metric-queue").textContent = runTotal ? `${done}/${runTotal}` : "—";
  $("#metric-queue-detail").textContent = runTotal ? `${count(runs, "RUNNING")} running · ${count(runs, "QUEUED")} queued` : "No scheduled runs yet";
  $("#metric-next").textContent = next ? `Run ${next.run_number}` : "—";
  $("#metric-next-detail").textContent = next ? `${dateLabel(next.scheduled_local, true)} · day ${next.day_number}` : "All scheduled work resolved";
  $("#metric-attention").textContent = String(recoveries.length + unread);
  $("#metric-attention-detail").textContent = `${recoveries.length} recovery · ${unread} notification${unread === 1 ? "" : "s"}`;
  $("#checked-at").textContent = dateLabel(snapshot.checked_at, true);
}

function renderSeasons(snapshot) {
  const seasons = snapshot.seasons || [];
  const activeIds = snapshot.active_season_ids || [];
  const container = $("#seasons");
  if (!seasons.length) {
    container.innerHTML = '<div class="empty-state"><strong>No season records yet</strong><span>The dashboard is connected and ready for the first season.</span></div>';
    return;
  }
  container.innerHTML = seasons.map((season) => {
    const runs = season.run_counts || {};
    const runTotal = total(runs);
    const done = resolvedRuns(runs);
    const percent = runTotal ? Math.round((done / runTotal) * 100) : 0;
    const next = season.next_run;
    const diaries = season.diary_counts || {};
    const diaryText = total(diaries)
      ? `${count(diaries, "WRITTEN")} written · ${count(diaries, "LATE")} late · ${count(diaries, "MISSING")} missing`
      : "No diary obligations yet";
    const wellnessPolicy = season.wellness_policy === "MANUAL_REVIEW"
      ? "manual wellness review"
      : "automatic tap-out";
    const cast = (season.cast || []).map((member) => {
      const memberStatus = String(member.status || "ACTIVE").toLowerCase();
      return `<span class="cast-person"><span class="cast-dot ${escapeHtml(memberStatus)}"></span><span>${escapeHtml(member.name || member.character_id)}</span><span class="cast-status">${escapeHtml(member.status || "ACTIVE")}</span></span>`;
    }).join("");
    return `<article class="season-card ${activeIds.includes(season.season_id) ? "is-active" : ""}">
      <div class="season-top"><div><p class="eyebrow">Season ${escapeHtml(season.season_id)}</p><h3>${escapeHtml(season.title || "Untitled season")}</h3></div>${badge(season.status)}</div>
      <div class="season-meta"><span>${done}/${runTotal || "—"} runs resolved</span><span>${escapeHtml(diaryText)}</span><span>${escapeHtml(wellnessPolicy)}</span></div>
      <div class="progress" aria-label="${percent}% of scheduled runs resolved"><span style="--progress: ${percent}%"></span></div>
      <div class="season-columns"><div><span class="label">Next scheduled</span><span class="value">${next ? `Run ${next.run_number} · ${dateLabel(next.scheduled_local, true)}` : "No unresolved run"}</span></div><div><span class="label">Delay / turn state</span><span class="value">${next ? `${humanize(next.status)}${next.delay ? ` · ${escapeHtml(next.delay)}` : ""}` : "Queue is quiet"}</span></div></div>
      <div class="cast-row">${cast || '<span class="faint">Cast manifest not present in this snapshot.</span>'}</div>
    </article>`;
  }).join("");
}

function renderAttention(snapshot) {
  const recoveries = snapshot.recoveries || [];
  const container = $("#attention");
  if (!recoveries.length && !snapshot.notifications?.unread) {
    container.innerHTML = '<div class="empty-state"><strong>Quiet for now</strong><span>No recovery requests or unread operator notifications.</span></div>';
    return;
  }
  const cards = recoveries.map((item) => {
    const canChoose = item.run_status === "RECOVERY_REQUIRED";
    const controls = canChoose
      ? `<div class="action-row"><button class="button button-small" data-recovery="${escapeHtml(item.run_id)}" data-season="${escapeHtml(item.season_id)}" data-decision="retry">Retry run</button><button class="button button-small button-quiet" data-recovery="${escapeHtml(item.run_id)}" data-season="${escapeHtml(item.season_id)}" data-decision="skip">Skip run</button><button class="button button-small button-danger" data-recovery="${escapeHtml(item.run_id)}" data-season="${escapeHtml(item.season_id)}" data-decision="end">End season</button></div>`
      : '<span class="faint">The automatic model-wait timer is still active.</span>';
    return `<article class="attention-card ${canChoose ? "" : "waiting"}><div class="attention-top">${badge(item.status)}<span class="faint">${escapeHtml(item.run_id)}</span></div><p>Season ${escapeHtml(item.season_id)} · scheduled ${dateLabel(item.scheduled_local, true)} · current run state ${humanize(item.run_status)}.</p>${controls}</article>`;
  }).join("");
  const notification = snapshot.notifications?.unread
    ? `<div class="note">${escapeHtml(snapshot.notifications.unread)} unread operator notification${snapshot.notifications.unread === 1 ? "" : "s"}. Details remain in the private service records.</div>` : "";
  container.innerHTML = cards + notification;
}

function renderAlert(snapshot) {
  const banner = $("#global-alert");
  const messages = [];
  if (snapshot.integrity !== "ok") messages.push(`Database integrity check: ${snapshot.integrity}.`);
  if (Number(snapshot.work?.due_queued || 0) > 0) messages.push(`${snapshot.work.due_queued} due work item${snapshot.work.due_queued === 1 ? "" : "s"} waiting for the service worker.`);
  if ((snapshot.recoveries || []).length) messages.push(`${snapshot.recoveries.length} recovery request${snapshot.recoveries.length === 1 ? "" : "s"} need${snapshot.recoveries.length === 1 ? "s" : ""} attention.`);
  banner.className = `alert ${snapshot.integrity !== "ok" ? "error" : messages.length ? "" : "good"}`;
  banner.innerHTML = messages.length ? `<span aria-hidden="true">●</span><span>${messages.map(escapeHtml).join(" ")}</span>` : '<span aria-hidden="true">✦</span><span>Service state is readable. The worker continues independently if this window is closed.</span>';
}

function renderPublication(snapshot) {
  const publications = snapshot.publications || [];
  const container = $("#publication");
  if (!publications.length) {
    container.innerHTML = '<div class="empty-state"><strong>No publication review yet</strong><span>Private seasons stay private until the explicit end-of-season gate.</span></div>';
    return;
  }
  container.innerHTML = publications.map((publication) => `<article class="publication-item"><div class="publication-top"><strong>${escapeHtml(publication.season_id)} · version ${escapeHtml(publication.version)}</strong>${badge(publication.status)}</div><p>${escapeHtml(publication.eligible_diary_count)} diary records eligible · ${publication.output_path ? `output: ${escapeHtml(publication.output_path)}` : "no public output projected"}</p></article>`).join("");
}

function syncDiaryControls(snapshot) {
  const seasons = snapshot.seasons || [];
  const selected = seasons.some((season) => season.season_id === state.diarySeason)
    ? state.diarySeason : activeSeason(snapshot)?.season_id || seasons[0]?.season_id || "";
  state.diarySeason = selected;
  const seasonSelect = $("#diary-season");
  seasonSelect.innerHTML = seasons.length
    ? seasons.map((season) => `<option value="${escapeHtml(season.season_id)}">${escapeHtml(season.season_id)}${season.title ? ` · ${escapeHtml(season.title)}` : ""}</option>`).join("")
    : '<option value="">No seasons</option>';
  seasonSelect.value = selected;
  $("#diary-day").value = state.diaryDay;
}

function syncReviewControls(snapshot) {
  const seasons = snapshot.seasons || [];
  const selected = seasons.some((season) => season.season_id === state.reviewSeason)
    ? state.reviewSeason : activeSeason(snapshot)?.season_id || seasons[0]?.season_id || "";
  state.reviewSeason = selected;
  const seasonSelect = $("#review-season");
  seasonSelect.innerHTML = seasons.length
    ? seasons.map((season) => `<option value="${escapeHtml(season.season_id)}">${escapeHtml(season.season_id)}${season.title ? ` · ${escapeHtml(season.title)}` : ""}</option>`).join("")
    : '<option value="">No seasons</option>';
  seasonSelect.value = selected;
  $("#review-day").value = state.reviewDay;
}

function renderDiaries(diaries) {
  const summary = $("#diary-summary");
  const written = diaries.filter((diary) => diary.status === "WRITTEN").length;
  const late = diaries.filter((diary) => diary.status === "LATE").length;
  const missing = diaries.filter((diary) => diary.status === "MISSING").length;
  summary.textContent = diaries.length ? `${written} written · ${late} late · ${missing} missing · ${diaries.length} record${diaries.length === 1 ? "" : "s"}` : "No diary records for this selection.";
  const container = $("#diaries");
  if (!diaries.length) {
    container.innerHTML = '<div class="empty-state"><strong>No diary records here</strong><span>Entries appear after a completed diary call. The current season remains private.</span></div>';
    return;
  }
  container.innerHTML = diaries.map((diary) => diaryReviewCard(diary, "diary-desk")).join("");
  bindDetailState(container);
}

async function loadDiaries() {
  if (!state.diarySeason) { renderDiaries([]); return; }
  const params = new URLSearchParams({ season_id: state.diarySeason });
  if (state.diaryDay) params.set("day", state.diaryDay);
  try {
    const response = await fetch(`/api/diaries?${params.toString()}`, { cache: "no-store" });
    if (response.status === 401) { window.location = "/login"; return; }
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not load diaries");
    renderDiaries(payload.diaries || []);
  } catch (error) {
    $("#diary-summary").textContent = error.message;
    $("#diaries").innerHTML = '<div class="empty-state"><strong>Diary view unavailable</strong><span>Try refreshing the dashboard.</span></div>';
  }
}

function renderDayReview(payload) {
  const summary = $("#review-summary");
  const date = payload.original_date ? ` · ${payload.original_date}` : "";
  const closure = payload.closed ? "day closure recorded" : "day still open";
  summary.textContent = `Day ${payload.day_number}${date} · ${payload.runs.length} scheduled run${payload.runs.length === 1 ? "" : "s"} · ${closure}`;
  const container = $("#day-review");
  const script = payload.shared_script
    ? detailMarkup(`day-review:${payload.season_id}:${payload.day_number}:script`, `Read shared Day ${payload.day_number} script`, payload.shared_script, "review-script")
    : '<div class="empty-state"><strong>No readable shared script yet</strong><span>Accepted scene turns will appear here as the day resolves.</span></div>';
  const runs = payload.runs.length
    ? `<ul class="review-run-list">${payload.runs.map((run) => `<li class="review-run">Run ${escapeHtml(run.run_number)} · slot ${escapeHtml(run.slot_number)} · ${escapeHtml(humanize(run.status))}${run.delay ? ` · ${escapeHtml(run.delay)}` : ""}</li>`).join("")}</ul>`
    : '<p class="faint">No scheduled runs were found for this day.</p>';
  const diaries = payload.diaries.length
    ? `<div class="review-diary-grid">${payload.diaries.map((diary) => diaryReviewCard(diary, `day-review:${payload.season_id}:${payload.day_number}`)).join("")}</div>`
    : '<div class="empty-state"><strong>No diary obligations yet</strong><span>Diary records appear after the first completed scene of the original day.</span></div>';
  container.innerHTML = `${runs}${script}<div class="panel-header"><div><h3>Private diary review</h3><p>Accepted entries and held private attempts stay visible only to the signed-in owner.</p></div></div>${diaries}`;
  bindDetailState(container);
}

async function loadDayReview() {
  if (!state.reviewSeason || !state.reviewDay) { return; }
  const params = new URLSearchParams({ season_id: state.reviewSeason, day: state.reviewDay });
  try {
    const response = await fetch(`/api/day-review?${params.toString()}`, { cache: "no-store" });
    if (response.status === 401) { window.location = "/login"; return; }
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not load end-of-day review");
    renderDayReview(payload);
  } catch (error) {
    $("#review-summary").textContent = error.message;
    $("#day-review").innerHTML = '<div class="empty-state"><strong>End-of-day review unavailable</strong><span>Try reloading the review.</span></div>';
  }
}

async function fetchStatus() {
  const response = await fetch("/api/status", { cache: "no-store" });
  if (response.status === 401) { window.location = "/login"; return null; }
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Could not load status");
  return payload;
}

async function refresh({ reloadContent = false } = {}) {
  setConnection(false, "Refreshing…");
  try {
    const snapshot = await fetchStatus();
    if (!snapshot) return;
    state.snapshot = snapshot;
    renderMetrics(snapshot);
    renderAlert(snapshot);
    renderSeasons(snapshot);
    renderAttention(snapshot);
    renderPublication(snapshot);
    syncDiaryControls(snapshot);
    syncReviewControls(snapshot);
    setConnection(true, "Live");
    if (reloadContent) {
      await Promise.all([loadDiaries(), loadDayReview()]);
    }
  } catch (error) {
    setConnection(false, "Unavailable");
    $("#global-alert").className = "alert error";
    $("#global-alert").innerHTML = `<span aria-hidden="true">!</span><span>${escapeHtml(error.message)} Try refreshing.</span>`;
  }
}

async function postJSON(path, payload) {
  const response = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(payload) });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || "The action was rejected");
  return result;
}

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-recovery]");
  if (!button) return;
  const decision = button.dataset.decision;
  const run = button.dataset.recovery;
  const season = button.dataset.season;
  const verb = decision === "end" ? "end the season" : `${decision} ${run}`;
  if (!window.confirm(`Are you sure you want to ${verb}?`)) return;
  button.disabled = true;
  try { await postJSON("/api/recover", { season_id: season, run_id: run, decision }); await refresh(); }
  catch (error) { window.alert(error.message); button.disabled = false; }
});

$("#refresh").addEventListener("click", () => refresh({ reloadContent: true }));
$("#diary-season").addEventListener("change", (event) => { state.diarySeason = event.target.value; state.diaryDay = ""; $("#diary-day").value = ""; loadDiaries(); });
$("#diary-day").addEventListener("change", (event) => { state.diaryDay = event.target.value; loadDiaries(); });
$("#review-season").addEventListener("change", (event) => { state.reviewSeason = event.target.value; loadDayReview(); });
$("#review-day").addEventListener("change", (event) => { state.reviewDay = event.target.value; loadDayReview(); });
$("#review-reload").addEventListener("click", loadDayReview);
refresh({ reloadContent: true });
window.setInterval(() => refresh(), 60000);
