"use strict";

document.documentElement.dataset.dashboardVersion = "2";

const page = document.body.dataset.dashboardPage || "home";
const selectedSeason = document.body.dataset.selectedSeason || "";
let lastEnvelope = null;
let lastSuccessfulRead = 0;
let transportState = "loading";
let lastReviewEnvelope = null;
let pendingReviewEnvelope = null;
let activeReviewTab = "script";
let disclosedDiaryIds = new Set();
let reviewStateInitialized = false;
let reviewPositionTimer = null;
let lastDiagnosticsEnvelope = null;
let lastPrepareEnvelope = null;
let lastLiveEnvelope = null;
let liveTranscriptEnvelope = null;
let lastSeasonsReview = null;
let lastPublicationPreview = null;
let seasonsDecisions = {};

const one = (selector, root = document) => root.querySelector(selector);
const all = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function text(selector, value) {
  const node = one(selector);
  if (node) node.textContent = value;
}

function setHref(selector, value) {
  const node = one(selector);
  if (!node || typeof value !== "string" || !value.startsWith("/v2/")) return;
  node.setAttribute("href", value);
}

function element(tag, content, className = "") {
  const node = document.createElement(tag);
  node.textContent = content;
  if (className) node.className = className;
  return node;
}

function formatTime(value, options = {}) {
  if (!value) return "time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    ...options,
  }).format(date);
}

function formatSnapshot(value) {
  if (!value) return "Snapshot time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Snapshot time unavailable";
  return `Checked ${formatTime(value, { second: "2-digit" })}`;
}

function normalizeStatus(value) {
  return String(value || "unknown").toLowerCase().replaceAll("_", " ");
}

function currentDestinationHref(destination, context) {
  const item = (context.navigation || []).find((candidate) => candidate.destination === destination);
  return item && typeof item.href === "string" ? item.href : `/v2/${destination}`;
}

function bindSeasonPickers() {
  all("[data-season-picker]").forEach((picker) => {
    picker.addEventListener("change", () => {
      if (!picker.value || picker.value === selectedSeason) return;
      const target = new URL(window.location.href);
      target.searchParams.set("season_id", picker.value);
      target.searchParams.delete("day");
      target.searchParams.delete("run_id");
      target.searchParams.delete("tab");
      target.searchParams.delete("character_id");
      window.location.assign(target.toString());
    });
  });
}

function updateSharedContext(context, meta) {
  const selected = (context.seasons || []).find(
    (season) => season.season_id === context.selected_season_id,
  );
  all("[data-season-picker]").forEach((picker) => {
    if (context.selected_season_id) picker.value = context.selected_season_id;
  });
  text("[data-context-season]", context.selected_season_id || "None");
  text("[data-context-title]", selected && selected.title ? selected.title : "No season");
  text(
    "[data-context-status]",
    selected ? `${selected.status} · OWNER VIEW` : "NO SEASON · OWNER VIEW",
  );
  text("[data-snapshot-version]", selected ? `season v${selected.version}` : "season v—");
  text("[data-rail-freshness]", formatSnapshot(meta.checked_at));
  text("[data-mobile-freshness]", `${String(meta.freshness).replaceAll("_", " ")} · ${formatTime(meta.checked_at)}`);
  all("[data-destination]").forEach((link) => {
    const href = currentDestinationHref(link.dataset.destination, context);
    if (href.startsWith("/v2/")) link.setAttribute("href", href);
  });
  setHref("[data-home-return]", currentDestinationHref("home", context));
}

function updateWorker(worker) {
  const evidence = one("[data-worker-evidence]");
  if (evidence) {
    evidence.className = `v2-evidence is-${worker.state}`;
    evidence.replaceChildren(element("i", ""), document.createTextNode(worker.label));
  }
  text("[data-worker-queue]", `${worker.queue_total} queued · ${worker.queue_due} due`);
}

function updateBanner(state, title, detail) {
  const banner = one("[data-global-state]");
  if (!banner) return;
  banner.dataset.tone = state;
  const strong = one("strong", banner);
  const span = one("span", banner);
  if (strong) strong.textContent = title;
  if (span) span.textContent = detail;
}

function successfulBanner(envelope) {
  const { data, meta } = envelope;
  if (data.state === "no_season") {
    updateBanner(
      "empty",
      "No season is stored yet",
      "Day Review will populate after a season has durable schedule or day evidence.",
    );
  } else if (meta.freshness === "partial") {
    const first = data.partial_reasons[0] || data.summary.message;
    const remaining = Math.max(data.partial_reasons.length - 1, 0);
    updateBanner(
      "partial",
      data.summary.heading,
      remaining ? `${first} ${remaining} more condition${remaining === 1 ? "" : "s"}.` : first,
    );
    return;
  }
  if (data.state === "no_season") {
    updateBanner("empty", data.summary.heading, data.summary.message);
    return;
  }
  if (data.attention.count && data.attention.highest_priority) {
    const item = data.attention.highest_priority;
    const remaining = data.attention.remaining_count;
    updateBanner(
      "attention",
      item.title,
      remaining ? `${item.detail} ${remaining} more item${remaining === 1 ? "" : "s"}.` : item.detail,
    );
    return;
  }
  updateBanner("calm", data.summary.heading, data.summary.message);
}

function renderMetrics(data) {
  const day = data.day_completion;
  if (!day.available) {
    text("[data-today-value]", "Not scheduled");
    text("[data-today-detail]", "No durable day slots stored");
  } else {
    text("[data-today-value]", `${day.resolved_runs} / ${day.scheduled_runs} runs`);
    const dayDetail = {
      closed: "Day complete · all scheduled runs resolved",
      closed_with_unresolved: `Day closed · ${day.scheduled_runs - day.resolved_runs} unresolved`,
      open: `Day ${day.day_number} remains open`,
      not_scheduled: "No durable day slots stored",
    };
    text("[data-today-detail]", dayDetail[day.state] || "Day state unavailable");
  }

  const diaryCounts = day.diary_counts || {};
  const diaryTotal = Object.values(diaryCounts).reduce((total, count) => total + Number(count || 0), 0);
  const due = Number(diaryCounts.EXPECTED || 0) + Number(diaryCounts.MISSING || 0);
  const held = Number(diaryCounts.PRIVATE || 0);
  text("[data-diary-value]", `${diaryTotal} record${diaryTotal === 1 ? "" : "s"}`);
  text("[data-diary-detail]", `${held} held private · ${due} expected or missing`);

  if (data.next_slot.available) {
    text("[data-next-value]", `Day ${data.next_slot.day_number} · slot ${data.next_slot.slot_number}`);
    text(
      "[data-next-detail]",
      `${formatTime(data.next_slot.scheduled_local)} · ${normalizeStatus(data.next_slot.status)}`,
    );
  } else {
    text("[data-next-value]", "No next slot");
    text("[data-next-detail]", "All stored schedule slots are resolved");
  }
  text("[data-attention-value]", data.attention.count ? String(data.attention.count) : "Nothing due");
  text(
    "[data-attention-detail]",
    data.attention.count ? "Durable operator review items" : "No unresolved operator item stored",
  );
}

function renderBeat(data) {
  const beat = data.last_accepted_beat;
  const reviewHref = currentDestinationHref("review", data.context);
  setHref("[data-beat-review]", reviewHref);
  if (!beat.available) {
    text("[data-beat-canon]", "No accepted record");
    text("[data-beat-title]", "No accepted beat stored");
    text("[data-beat-excerpt]", "The first accepted story beat will appear here without exposing its private path.");
    text("[data-beat-receipt]", "No receipt available");
    text("[data-beat-evidence]", "No accepted-turn evidence is stored for this season.");
    return;
  }
  const orderLabel = String(beat.evidence_basis || "").startsWith("Persisted order")
    ? "Accepted · persisted order"
    : "Accepted · derived order";
  text("[data-beat-canon]", orderLabel);
  text("[data-beat-title]", `Run ${String(beat.run_number).padStart(2, "0")} · slot ${beat.slot_number}`);
  const speaker = beat.speaker_name ? `${beat.speaker_name}: ` : "";
  text("[data-beat-excerpt]", beat.excerpt ? `${speaker}${beat.excerpt}` : "Accepted text is not readable inside private storage.");
  text("[data-beat-receipt]", `${beat.run_id} · ${beat.turn_count} turns · receipt ${beat.receipt}`);
  text("[data-beat-evidence]", beat.evidence_basis || "Ordering basis unavailable.");
}

function renderNext(data) {
  const next = data.next_slot;
  setHref("[data-schedule-link]", currentDestinationHref("seasons", data.context));
  if (next.available) {
    text("[data-next-title]", `Day ${next.day_number} · slot ${next.slot_number}`);
    text(
      "[data-next-copy]",
      `${formatTime(next.scheduled_local)} · ${normalizeStatus(next.status)} · run ${next.run_number}`,
    );
  } else {
    text("[data-next-title]", "No unresolved slot stored");
    text("[data-next-copy]", "Every durable schedule slot is resolved.");
  }
  const list = one("[data-cast-list]");
  if (list) {
    const cast = data.cast || [];
    const children = cast.length
      ? cast.map((member) => element("li", `${member.name} · ${normalizeStatus(member.status)}`))
      : [element("li", "No cast records stored")];
    list.replaceChildren(...children);
  }
}

function renderReview(data) {
  const day = data.day_completion;
  text("[data-review-eyebrow]", day.available ? `Day ${day.day_number} review` : "Day review");
  const unresolved = day.scheduled_runs - day.resolved_runs;
  const titles = {
    closed: "Durably complete",
    closed_with_unresolved: `Closed with ${unresolved} unresolved run${unresolved === 1 ? "" : "s"}`,
    open: "Day remains open",
    not_scheduled: "No day scheduled",
  };
  text("[data-review-title]", titles[day.state] || "Day state unavailable");
  text(
    "[data-review-copy]",
    day.complete
      ? "The stored day is closed and every scheduled run is resolved."
      : "Home will not call this day complete without both durable closure and resolved runs.",
  );
  setHref("[data-review-link]", day.review_href || currentDestinationHref("review", data.context));
}

function renderHealth(data) {
  const health = data.health;
  text("[data-health-integrity]", health.database_integrity === "ok" ? "SQLite check returned ok" : "SQLite check did not return ok");
  text("[data-health-worker]", data.worker.label);
  const storage = [
    health.state_storage_reachable,
    health.private_storage_reachable,
    health.public_storage_reachable,
  ];
  text("[data-health-storage]", storage.every(Boolean) ? "Configured roots readable" : "One or more roots unreadable");
  text("[data-health-outbox]", `${health.artifact_outbox_pending} pending artifact${health.artifact_outbox_pending === 1 ? "" : "s"}`);
  text("[data-health-models]", health.model_availability === "not_probed" ? "Availability not probed" : "Availability unknown");

  const recent = one("[data-recent-seasons]");
  if (recent) {
    const children = (data.recent_seasons || []).map((season) => {
      const item = document.createElement("li");
      const link = element("a", `${season.season_id} · ${season.title || "Untitled"} · ${normalizeStatus(season.status)}`);
      link.href = `/v2/home?season_id=${encodeURIComponent(season.season_id)}`;
      if (season.selected) link.setAttribute("aria-current", "page");
      item.append(link);
      return item;
    });
    recent.replaceChildren(...(children.length ? children : [element("li", "No season history stored")]));
  }
}

function renderHome(envelope) {
  const { data, meta } = envelope;
  updateSharedContext(data.context, meta);
  updateWorker(data.worker);
  const lifecycle = data.lifecycle;
  text("[data-home-eyebrow]", lifecycle ? `Home / ${lifecycle.title || lifecycle.season_id}` : "Home / no season");
  text("[data-home-summary]", data.summary.message);
  text(
    "[data-freshness-badge]",
    `Durable · ${String(meta.freshness).replaceAll("_", " ")} · ${formatTime(meta.checked_at)}`,
  );
  successfulBanner(envelope);
  renderMetrics(data);
  renderBeat(data);
  renderNext(data);
  renderReview(data);
  renderHealth(data);
  document.body.dataset.snapshotState = meta.freshness;
}

function reviewStateKey(data) {
  const season = data.context.selected_season_id || "none";
  const day = data.day ? data.day.day_number : "none";
  const run = data.selected_run_id || "none";
  return `dashboard-v2:review:${season}:day:${day}:run:${run}`;
}

function readReviewState(data) {
  try {
    const value = window.localStorage.getItem(reviewStateKey(data));
    const parsed = value ? JSON.parse(value) : null;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (error) {
    return {};
  }
}

function saveReviewPosition() {
  if (!lastReviewEnvelope || !lastReviewEnvelope.data) return;
  const data = lastReviewEnvelope.data;
  try {
    window.localStorage.setItem(
      reviewStateKey(data),
      JSON.stringify({
        scrollY: Math.max(0, Math.round(window.scrollY || 0)),
        tab: activeReviewTab,
        disclosedDiaryIds: Array.from(disclosedDiaryIds),
        savedAt: new Date().toISOString(),
      }),
    );
    const run = (data.runs || []).find((candidate) => candidate.selected);
    text(
      "[data-review-position]",
      data.day && run
        ? `Day ${data.day.day_number} · Run ${String(run.run_number).padStart(2, "0")} · position saved locally`
        : "Reading position saved locally",
    );
  } catch (error) {
    text("[data-review-position]", "Local position could not be saved");
  }
}

function scheduleReviewPositionSave() {
  if (page !== "review") return;
  if (reviewPositionTimer) window.clearTimeout(reviewPositionTimer);
  reviewPositionTimer = window.setTimeout(saveReviewPosition, 250);
}

function reviewRequestURL() {
  const params = new URLSearchParams(window.location.search);
  const query = new URLSearchParams();
  const season = params.get("season_id") || selectedSeason;
  if (season) query.set("season_id", season);
  if (params.get("day")) query.set("day", params.get("day"));
  if (params.get("run_id")) query.set("run_id", params.get("run_id"));
  const suffix = query.toString();
  return `/api/v2/review/day${suffix ? `?${suffix}` : ""}`;
}

function reviewPageHref(data, runId, options = {}) {
  const params = new URLSearchParams();
  if (data.context.selected_season_id) params.set("season_id", data.context.selected_season_id);
  if (data.day) params.set("day", String(data.day.day_number));
  if (runId) params.set("run_id", runId);
  if (options.tab) params.set("tab", options.tab);
  if (options.characterId) params.set("character_id", options.characterId);
  return `/v2/review?${params.toString()}`;
}

function formatReviewDateTime(value) {
  if (!value) return "not stored";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unavailable";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function reviewBadge(label, tone = "neutral") {
  const badge = element("span", label, "v2-review-badge");
  badge.dataset.tone = tone;
  return badge;
}

function selectedReviewRun(data) {
  return (data.runs || []).find((run) => run.run_id === data.selected_run_id) || data.runs[0] || null;
}

function buildRunRail(data) {
  const rail = element("aside", "", "v2-run-rail");
  const header = element("header", "");
  header.append(element("p", `Day ${data.day ? data.day.day_number : "—"}`, "v2-eyebrow"));
  header.append(element("h2", "Run selector"));
  rail.append(header);
  const list = element("nav", "", "v2-run-list");
  list.setAttribute("aria-label", "Runs in selected day");
  (data.runs || []).forEach((run) => {
    const link = element("a", "", "v2-run-option");
    link.href = reviewPageHref(data, run.run_id);
    if (run.selected) link.setAttribute("aria-current", "page");
    link.addEventListener("click", saveReviewPosition);
    const heading = element("span", "", "v2-run-option-heading");
    heading.append(
      element("strong", `Run ${String(run.run_number).padStart(2, "0")}`),
      reviewBadge(normalizeStatus(run.status), run.status === "COMPLETED" ? "calm" : "attention"),
    );
    link.append(
      heading,
      element("span", `${run.fiction_clock.label} · slot ${run.slot_number}`),
      element(
        "small",
        `${run.accepted_record_count} accepted record${run.accepted_record_count === 1 ? "" : "s"} · ${run.order_evidence} order`,
      ),
    );
    list.append(link);
  });
  if (!(data.runs || []).length) list.append(element("p", "No scheduled run record is stored for this day."));
  rail.append(list);
  if (data.day) {
    const close = element("section", "", "v2-day-close-card");
    close.append(
      element("p", "Day completion", "v2-eyebrow"),
      element("strong", data.day.closed ? "Closed in durable state" : "Still open"),
      element("span", `${data.day.resolved_runs} of ${data.day.scheduled_runs} scheduled runs resolved`),
    );
    rail.append(close);
  }
  return rail;
}

function buildScriptPanel(data) {
  const panel = element("article", "", "v2-review-primary v2-script-panel");
  const run = selectedReviewRun(data);
  if (!run) {
    panel.append(element("h2", "No run selected"), element("p", "This day has no durable run record to read."));
    return panel;
  }
  const header = element("header", "", "v2-script-header");
  const title = element("div", "");
  title.append(
    element("p", `${run.fiction_clock.label} / accepted story`, "v2-eyebrow"),
    element("h2", `Run ${String(run.run_number).padStart(2, "0")} · ${normalizeStatus(run.status)}`),
  );
  const badges = element("div", "", "v2-review-badges");
  badges.append(
    reviewBadge(`${run.accepted_record_count} accepted`, "calm"),
    reviewBadge(`${run.order_evidence} order`, run.order_evidence === "persisted" ? "calm" : "attention"),
  );
  header.append(title, badges);
  panel.append(header);

  const evidence = element("dl", "", "v2-run-evidence");
  [
    ["Completion reason", normalizeStatus(run.completion_reason)],
    ["Accepted actor turns", `${run.accepted_actor_turn_count} readable · ${run.stored_actor_turn_count} stored count`],
    ["Scheduled", formatReviewDateTime(run.scheduled_local)],
    ["Actual", run.actual_started_at ? formatReviewDateTime(run.actual_started_at) : "not started"],
    ["Delay", run.delay ? normalizeStatus(run.delay) : "not stored"],
  ].forEach(([term, detail]) => {
    const pair = element("div", "");
    pair.append(element("dt", term), element("dd", detail));
    evidence.append(pair);
  });
  panel.append(evidence, element("p", run.order_explanation, "v2-order-note"));

  const transcript = element("section", "", "v2-transcript");
  transcript.setAttribute("aria-label", `Accepted transcript for run ${run.run_number}`);
  (run.records || []).forEach((record) => {
    const item = element("article", "", `v2-story-record is-${record.kind}`);
    item.dataset.turnId = record.turn_id;
    const itemHeader = element("header", "");
    itemHeader.append(
      element("span", `Accepted ${String(record.accepted_sequence).padStart(2, "0")}`),
      element("strong", record.speaker_name),
      element("small", `Round ${record.round_number}`),
    );
    const content = element(
      "p",
      record.content || "Accepted text is unavailable inside readable private storage.",
    );
    item.append(itemHeader, content);
    if (record.evidence_note) item.append(element("small", record.evidence_note, "v2-record-note"));
    transcript.append(item);
  });
  if (!(run.records || []).length) {
    transcript.append(element("p", "No accepted story record is stored for this run.", "v2-review-empty"));
  }
  panel.append(transcript);
  if ((run.evidence_notes || []).length) {
    const notes = element("section", "", "v2-evidence-notes");
    notes.append(element("h3", "Evidence notes"));
    const list = element("ul", "");
    run.evidence_notes.forEach((note) => list.append(element("li", note)));
    notes.append(list);
    panel.append(notes);
  }
  return panel;
}

function diaryActionLabel(diary) {
  if (diary.evidence_state === "held_private") return "Open held attempt";
  if (diary.content_available) return "Open private entry";
  return "Open private evidence";
}

function buildDiaryCard(diary, compact = false) {
  const card = element("article", "", `v2-diary-card${compact ? " is-compact" : ""}`);
  card.dataset.diaryId = diary.diary_id;
  const header = element("header", "");
  const heading = element("div", "");
  heading.append(
    element("strong", diary.character_name),
    element(
      "small",
      diary.chosen_slot_number ? `Chosen after slot ${diary.chosen_slot_number}` : "No slot chosen",
    ),
  );
  header.append(
    heading,
    reviewBadge(normalizeStatus(diary.status), diary.evidence_state === "missing" ? "attention" : "neutral"),
  );
  card.append(header, element("p", diary.evidence_note));
  const facts = element("span", "", "v2-diary-facts");
  facts.textContent = [
    diary.word_count == null ? "word count unavailable" : `${diary.word_count} words`,
    diary.late ? "late" : "on recorded schedule",
  ].join(" · ");
  card.append(facts);
  if (diary.disclosure_href) {
    const button = element("button", diaryActionLabel(diary), "v2-disclosure-button");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    button.addEventListener("click", () => revealDiary(button, diary));
    card.append(button);
  }
  return card;
}

function buildDiaryDesk(data, compact = false) {
  const desk = element(compact ? "aside" : "article", "", compact ? "v2-diary-dock" : "v2-review-primary v2-diary-panel");
  const header = element("header", "", "v2-diary-desk-header");
  const title = element("div", "");
  title.append(element("p", "Private / deliberate disclosure", "v2-eyebrow"), element("h2", "Diary desk"));
  header.append(title, reviewBadge(`${(data.diaries || []).length} records`, "neutral"));
  desk.append(
    header,
    element(
      "p",
      "Cards show durable status only. Opening an entry is a read-only disclosure and never changes canon, wellness, or publication eligibility.",
      "v2-diary-boundary",
    ),
  );
  const list = element("div", "", "v2-diary-stack");
  (data.diaries || []).forEach((diary) => list.append(buildDiaryCard(diary, compact)));
  if (!(data.diaries || []).length) list.append(element("p", "No diary obligation is stored for this day.", "v2-review-empty"));
  desk.append(list);
  return desk;
}

async function revealDiary(button, diary, options = {}) {
  const card = button.closest("[data-diary-id]");
  if (!card || !diary.disclosure_href || !diary.disclosure_href.startsWith("/api/v2/review/diary-attempt?")) return;
  const existing = one("[data-diary-disclosure]", card);
  if (existing && !options.restore) {
    existing.remove();
    disclosedDiaryIds.delete(diary.diary_id);
    button.textContent = diaryActionLabel(diary);
    button.setAttribute("aria-expanded", "false");
    saveReviewPosition();
    return;
  }
  if (existing) return;
  button.disabled = true;
  button.textContent = "Opening private text…";
  try {
    const envelope = await requestJSON(diary.disclosure_href);
    const disclosure = envelope.data;
    const region = element("section", "", "v2-diary-disclosure");
    region.dataset.diaryDisclosure = "true";
    region.append(
      reviewBadge(
        disclosure.source === "private_attempt" ? "Held private attempt" : "Private diary entry",
        disclosure.wellness_signal_present ? "attention" : "calm",
      ),
      element(
        "p",
        disclosure.content || "Diary text could not be safely separated for display.",
        "v2-diary-text",
      ),
      element("small", disclosure.evidence_note),
    );
    if (disclosure.wellness_signal_present) {
      region.append(
        element(
          "strong",
          "Wellness signal present · wording withheld · status unchanged",
          "v2-wellness-presence",
        ),
      );
    }
    card.append(region);
    disclosedDiaryIds.add(diary.diary_id);
    button.textContent = "Close private text";
    button.setAttribute("aria-expanded", "true");
    saveReviewPosition();
  } catch (error) {
    const region = element("section", "Private diary text could not be read. The diary record was not changed.", "v2-diary-disclosure is-error");
    region.dataset.diaryDisclosure = "true";
    card.append(region);
    button.textContent = "Close private text";
    button.setAttribute("aria-expanded", "true");
  } finally {
    button.disabled = false;
  }
}

function hydrateOpenDiaryDisclosures(data) {
  (data.diaries || []).forEach((diary) => {
    if (!disclosedDiaryIds.has(diary.diary_id)) return;
    all(`[data-diary-id="${CSS.escape(diary.diary_id)}"] .v2-disclosure-button`).forEach((button) => {
      revealDiary(button, diary, { restore: true });
    });
  });
}

function buildCastPanel(data) {
  const panel = element("article", "", "v2-review-primary v2-cast-panel");
  const selectedCharacterId = new URLSearchParams(window.location.search).get("character_id");
  const selectedCharacter = (data.cast || []).find(
    (member) => member.character_id === selectedCharacterId,
  );
  panel.append(
    element("p", "Accepted context / no role sheets", "v2-eyebrow"),
    element("h2", "Cast & continuity"),
    element("p", "Status and memory version links are visible here; private memory content and role sheets are not."),
  );
  if (selectedCharacter) {
    const selectedContext = element("section", "", "v2-selected-memory-context");
    selectedContext.append(
      element("strong", `${selectedCharacter.name} · approved card ${selectedCharacter.character_card_version ? `v${selectedCharacter.character_card_version}` : "unavailable"}`),
      element(
        "span",
        selectedCharacter.public_brief || "No approved character card is stored.",
      ),
      element("span", selectedCharacter.pronouns ? `Pronouns: ${selectedCharacter.pronouns}` : "Pronouns unavailable"),
      element("span", `Voice: ${(selectedCharacter.voice_anchors || []).join(" · ") || "unavailable"}`),
      element("small", "Private memory content and role sheets remain excluded from Review."),
    );
    panel.append(selectedContext);
  }
  const cast = element("div", "", "v2-review-cast-grid");
  (data.cast || []).forEach((member) => {
    const card = element("article", "", "v2-review-cast-card");
    if (member.character_id === selectedCharacterId) {
      card.dataset.selected = "true";
      card.setAttribute("aria-current", "true");
    }
    card.append(
      element("strong", member.name),
      element("span", normalizeStatus(member.status)),
      element("small", `Card ${member.character_card_version ? `v${member.character_card_version}` : "unavailable"} · memory v${member.memory_version}`),
    );
    const link = element(
      "a",
      member.character_id === selectedCharacterId ? "Selected reading context" : "Open saved reading context",
    );
    link.href = member.memory_href;
    link.addEventListener("click", saveReviewPosition);
    card.append(link);
    cast.append(card);
  });
  panel.append(cast);
  const canon = element("section", "", "v2-canon-list");
  canon.append(element("h3", "Accepted canon ledger"));
  if ((data.continuity.canon || []).length) {
    const list = element("ol", "");
    data.continuity.canon.forEach((item) => {
      list.append(element("li", `v${item.version} · ${normalizeStatus(item.status)} · ${item.claim}`));
    });
    canon.append(list);
  } else {
    canon.append(element("p", "No canon entry is stored for this season."));
  }
  panel.append(canon);
  const unresolved = element("section", "", "v2-continuity-unavailable");
  unresolved.append(element("h3", `Unresolved continuity · ${normalizeStatus(data.continuity.unresolved_state)}`));
  (data.continuity.unresolved_notes || []).forEach((note) => unresolved.append(element("p", note)));
  panel.append(unresolved);
  return panel;
}

function buildSummaryPanel(data) {
  const panel = element("article", "", "v2-review-primary v2-summary-panel");
  panel.append(element("p", "Day evidence", "v2-eyebrow"), element("h2", `Day ${data.day ? data.day.day_number : "—"} summary`));
  if (data.day) {
    const metrics = element("dl", "", "v2-day-summary-grid");
    [
      ["Day close", data.day.closed ? "closed" : "open"],
      ["Runs resolved", `${data.day.resolved_runs} of ${data.day.scheduled_runs}`],
      ["Accepted records", String(data.accepted_record_count)],
      ["Diary records", String((data.diaries || []).length)],
      ["Original date", data.day.original_date || "unavailable"],
      ["Cutoff", formatReviewDateTime(data.day.cutoff_at)],
    ].forEach(([term, detail]) => {
      const pair = element("div", "");
      pair.append(element("dt", term), element("dd", detail));
      metrics.append(pair);
    });
    panel.append(metrics);
  }
  const runs = element("section", "", "v2-summary-runs");
  runs.append(element("h3", "Run evidence"));
  (data.runs || []).forEach((run) => {
    const card = element("article", "");
    card.append(
      element("strong", `Run ${String(run.run_number).padStart(2, "0")} · ${normalizeStatus(run.status)}`),
      element("span", `Completion: ${normalizeStatus(run.completion_reason)}`),
      element("small", `${run.accepted_record_count} accepted · ${run.order_evidence} order`),
    );
    runs.append(card);
  });
  panel.append(runs);
  const exceptions = element("section", "", "v2-evidence-notes");
  exceptions.append(element("h3", "Known limits and exceptions"));
  const list = element("ul", "");
  (data.partial_reasons || []).forEach((reason) => list.append(element("li", reason)));
  if (!(data.partial_reasons || []).length) list.append(element("li", "No partial evidence condition is reported for this day."));
  exceptions.append(list);
  panel.append(exceptions);
  return panel;
}

function buildActiveReviewPanel(data) {
  if (activeReviewTab === "diaries") return buildDiaryDesk(data, false);
  if (activeReviewTab === "cast") return buildCastPanel(data);
  if (activeReviewTab === "summary") return buildSummaryPanel(data);
  return buildScriptPanel(data);
}

function syncReviewTabs() {
  document.body.dataset.reviewTab = activeReviewTab;
  all("[data-review-tab]").forEach((button) => {
    const selected = button.dataset.reviewTab === activeReviewTab;
    button.setAttribute("aria-selected", selected ? "true" : "false");
    button.tabIndex = selected ? 0 : -1;
  });
}

function renderReviewPage(envelope, options = {}) {
  const { data, meta } = envelope;
  const reader = one("[data-review-reader]");
  if (!reader) return;
  const saved = readReviewState(data);
  const urlTab = new URLSearchParams(window.location.search).get("tab");
  const validTabs = new Set(["script", "diaries", "cast", "summary"]);
  let restoredScroll = null;
  if (!reviewStateInitialized) {
    if (validTabs.has(urlTab)) activeReviewTab = urlTab;
    else if (validTabs.has(saved.tab)) activeReviewTab = saved.tab;
    disclosedDiaryIds = new Set(
      Array.isArray(saved.disclosedDiaryIds) ? saved.disclosedDiaryIds.map(String) : [],
    );
    restoredScroll = Number.isFinite(Number(saved.scrollY)) ? Number(saved.scrollY) : null;
    reviewStateInitialized = true;
  } else if (options.preserveScroll) {
    restoredScroll = window.scrollY;
  }

  lastReviewEnvelope = envelope;
  pendingReviewEnvelope = null;
  const newer = one("[data-review-newer]");
  if (newer) newer.hidden = true;
  updateSharedContext(data.context, meta);
  document.body.dataset.snapshotState = meta.freshness;
  const selected = selectedReviewRun(data);
  const url = new URL(window.location.href);
  if (data.context.selected_season_id) url.searchParams.set("season_id", data.context.selected_season_id);
  if (data.day) url.searchParams.set("day", String(data.day.day_number));
  if (selected) url.searchParams.set("run_id", selected.run_id);
  window.history.replaceState({ review: true }, "", url);

  const layout = element("div", "", "v2-review-layout");
  layout.dataset.reviewView = activeReviewTab;
  layout.append(buildRunRail(data), buildActiveReviewPanel(data));
  if (activeReviewTab !== "diaries") layout.append(buildDiaryDesk(data, true));
  reader.replaceChildren(layout);
  reader.setAttribute("aria-busy", "false");
  syncReviewTabs();
  hydrateOpenDiaryDisclosures(data);
  text(
    "[data-review-position]",
    data.day && selected
      ? `Day ${data.day.day_number} · Run ${String(selected.run_number).padStart(2, "0")} · position saved locally`
      : "No saved run position",
  );
  if (meta.freshness === "partial") {
    updateBanner(
      "partial",
      "Readable with evidence limits",
      data.partial_reasons[0] || "One or more durable records are incomplete.",
    );
  } else {
    updateBanner(
      "calm",
      "Accepted review is ready",
      `${data.accepted_record_count} accepted record${data.accepted_record_count === 1 ? "" : "s"} · diary text remains closed until requested`,
    );
  }
  if (restoredScroll !== null) {
    const restoreReadingPosition = () => window.scrollTo({ top: restoredScroll, behavior: "auto" });
    window.requestAnimationFrame(restoreReadingPosition);
    window.setTimeout(restoreReadingPosition, 350);
  } else {
    const targetTurn = new URLSearchParams(window.location.search).get("turn_id");
    const target = targetTurn
      ? all("[data-turn-id]", reader).find((item) => item.dataset.turnId === targetTurn)
      : null;
    if (target) {
      target.dataset.diagnosticsTarget = "true";
      window.requestAnimationFrame(() => target.scrollIntoView({ block: "center", behavior: "auto" }));
    }
  }
}

function reviewSignature(envelope) {
  const data = envelope.data;
  return JSON.stringify({
    accepted: data.accepted_record_count,
    day: data.day ? [data.day.closed, data.day.resolved_runs, data.day.scheduled_runs] : null,
    runs: (data.runs || []).map((run) => [run.run_id, run.status, run.accepted_record_count, run.completion_reason]),
    diaries: (data.diaries || []).map((diary) => [diary.diary_id, diary.status, diary.content_available, diary.attempt_available]),
  });
}

async function loadReview(options = {}) {
  try {
    const envelope = options.usePending && pendingReviewEnvelope
      ? pendingReviewEnvelope
      : await requestJSON(reviewRequestURL());
    lastSuccessfulRead = Date.now();
    transportState = "connected";
    renderReviewPage(envelope, { preserveScroll: Boolean(lastReviewEnvelope) });
  } catch (error) {
    transportState = "disconnected";
    document.body.dataset.snapshotState = "disconnected";
    if (lastReviewEnvelope) {
      updateBanner(
        "disconnected",
        "Disconnected · open review retained",
        "No reading pane, diary disclosure, or scroll position was replaced.",
      );
    } else {
      const reader = one("[data-review-reader]");
      if (reader) reader.replaceChildren(element("p", "The durable day review could not be read.", "v2-review-empty"));
      updateBanner("disconnected", "Review could not connect", "No prior reading snapshot is available in this page session.");
    }
  }
}

async function probeReview() {
  if (!lastReviewEnvelope) return;
  try {
    const envelope = await requestJSON(reviewRequestURL());
    lastSuccessfulRead = Date.now();
    transportState = "connected";
    if (reviewSignature(envelope) !== reviewSignature(lastReviewEnvelope)) {
      pendingReviewEnvelope = envelope;
      const newer = one("[data-review-newer]");
      if (newer) newer.hidden = false;
    }
  } catch (error) {
    transportState = "disconnected";
    document.body.dataset.snapshotState = "disconnected";
    updateBanner(
      "disconnected",
      "Disconnected · open review retained",
      "Operational truth may have changed. The reading DOM and local position remain untouched.",
    );
  }
}

async function refreshReviewOperationalContext() {
  try {
    const envelope = await requestJSON(`/api/v2/home${querySuffix()}`);
    updateSharedContext(envelope.data.context, envelope.meta);
    updateWorker(envelope.data.worker);
    lastSuccessfulRead = Date.now();
  } catch (error) {
    if (!lastReviewEnvelope) return;
    transportState = "disconnected";
    document.body.dataset.snapshotState = "disconnected";
    updateBanner(
      "disconnected",
      "Operational context disconnected · review retained",
      "The accepted transcript and open diary disclosures have not moved.",
    );
  }
}

function bindReviewControls() {
  if (page !== "review") return;
  all("[data-review-tab]").forEach((button, index, buttons) => {
    button.addEventListener("click", () => {
      activeReviewTab = button.dataset.reviewTab || "script";
      const url = new URL(window.location.href);
      url.searchParams.set("tab", activeReviewTab);
      window.history.replaceState({ review: true }, "", url);
      if (lastReviewEnvelope) renderReviewPage(lastReviewEnvelope, { preserveScroll: true });
      saveReviewPosition();
    });
    button.addEventListener("keydown", (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      let target = index;
      if (event.key === "ArrowRight") target = (index + 1) % buttons.length;
      if (event.key === "ArrowLeft") target = (index - 1 + buttons.length) % buttons.length;
      if (event.key === "Home") target = 0;
      if (event.key === "End") target = buttons.length - 1;
      buttons[target].focus();
      buttons[target].click();
    });
  });
  const reload = one("[data-review-reload]");
  if (reload) reload.addEventListener("click", () => loadReview());
  const loadNew = one("[data-review-load-new]");
  if (loadNew) loadNew.addEventListener("click", () => loadReview({ usePending: true }));
  const keep = one("[data-review-keep]");
  if (keep) keep.addEventListener("click", () => {
    const newer = one("[data-review-newer]");
    if (newer) newer.hidden = true;
  });
  window.addEventListener("scroll", scheduleReviewPositionSave, { passive: true });
  window.addEventListener("pagehide", saveReviewPosition);
}

function diagnosticsRequestURL() {
  const params = new URLSearchParams(window.location.search);
  if (selectedSeason) params.set("season_id", selectedSeason);
  const callId = params.get("call_id");
  params.delete("call_id");
  const suffix = params.toString();
  return callId
    ? `/api/v2/diagnostics/calls/${encodeURIComponent(callId)}${suffix ? `?${suffix}` : ""}`
    : `/api/v2/diagnostics/calls${suffix ? `?${suffix}` : ""}`;
}

function diagnosticsValue(value, fallback = "Unavailable") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function buildDiagnosticsCallRail(data) {
  const rail = element("aside", "", "v2-diagnostics-rail");
  rail.append(
    element("p", "Calls in this filter", "v2-eyebrow"),
    element("small", "Selecting a call changes only this evidence view."),
  );
  const list = element("div", "", "v2-diagnostics-call-list");
  (data.calls || []).forEach((call) => {
    const link = element("a", "", "v2-diagnostics-call");
    link.href = call.detail_href;
    if (call.selected) link.setAttribute("aria-current", "true");
    link.append(
      element("strong", `${call.character_id || "Director"} · attempt ${call.attempt}`),
      element("span", normalizeStatus(call.status)),
      element("small", `${call.response_format_mode || "format unavailable"} · ${call.latency_ms === null ? "latency unavailable" : `${(call.latency_ms / 1000).toFixed(1)} s`}`),
    );
    list.append(link);
  });
  if (!(data.calls || []).length) list.append(element("p", "No call matches these filters.", "v2-review-empty"));
  rail.append(list, element("small", `${data.excluded_private_attempt_count} private non-run attempt${data.excluded_private_attempt_count === 1 ? "" : "s"} excluded.`));
  return rail;
}

function buildDiagnosticsDetail(call) {
  const panel = element("article", "", "v2-diagnostics-detail");
  if (!call) {
    panel.append(element("h2", "No call selected"), element("p", "Adjust the filters or select a stored run call."));
    return panel;
  }
  const header = element("header", "", "v2-diagnostics-detail-header");
  const heading = element("div", "");
  heading.append(
    element("p", `Selected call · attempt ${call.attempt}`, "v2-eyebrow"),
    element("h2", `${call.character_id || "Director"} · ${normalizeStatus(call.status)}`),
  );
  header.append(heading, reviewBadge(call.error_type ? "Failed evidence" : "Stored evidence", call.error_type ? "attention" : "calm"));
  panel.append(header);

  const identity = element("dl", "", "v2-diagnostics-identity");
  [
    ["Call", call.call_id], ["Purpose", call.purpose],
    ["Binding", `${diagnosticsValue(call.backend)} / ${diagnosticsValue(call.model)}`],
    ["Response mode", diagnosticsValue(call.response_format_mode)],
    ["Timing", `${formatReviewDateTime(call.started_at)} → ${formatReviewDateTime(call.ended_at)}`],
    ["Finish", `${diagnosticsValue(call.finish_reason)} · ${call.latency_ms === null ? "latency unavailable" : `${(call.latency_ms / 1000).toFixed(1)} s`}`],
    ["Transport", call.error_type ? `${call.error_type}${call.cancelled ? " · cancelled" : ""}` : "No stored transport error"],
    ["Usage", call.total_tokens === null ? "Token count unavailable" : `${call.total_tokens} total tokens`],
  ].forEach(([term, value]) => {
    const pair = element("div", "");
    pair.append(element("dt", term), element("dd", value));
    identity.append(pair);
  });
  panel.append(identity, element("h3", "Raw-to-rendered sequence"));
  const stages = element("ol", "", "v2-diagnostics-stages");
  (call.stages || []).forEach((stage, index) => {
    const item = element("li", "");
    item.dataset.state = stage.state;
    item.append(
      element("span", String(index + 1), "v2-stage-number"),
      element("strong", `${stage.stage} · ${normalizeStatus(stage.state)}`),
      element("p", stage.summary),
    );
    if (stage.content) item.append(element("blockquote", stage.content));
    if (stage.stage === "raw" && call.raw_disclosure_href) {
      const button = element("button", "Reveal raw output");
      button.type = "button";
      button.dataset.rawHref = call.raw_disclosure_href;
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const envelope = await requestJSON(call.raw_disclosure_href);
          item.append(element("pre", envelope.data.content, "v2-diagnostics-raw"));
          button.remove();
        } catch (error) {
          button.disabled = false;
          button.textContent = "Raw output unavailable";
        }
      });
      item.append(button);
    }
    stages.append(item);
  });
  panel.append(stages);
  if (call.validator_code || call.validator_detail) {
    const finding = element("section", "", "v2-diagnostics-finding");
    finding.append(element("p", "Validator finding", "v2-eyebrow"), element("strong", diagnosticsValue(call.validator_code)), element("span", diagnosticsValue(call.validator_detail)));
    panel.append(finding);
  }
  if (call.correction_of_call_id || (call.correction_call_ids || []).length) {
    panel.append(element("p", `Correction links · source ${call.correction_of_call_id || "this call"} · related ${(call.correction_call_ids || []).join(", ") || "none"}`, "v2-diagnostics-corrections"));
  }
  const provenance = element("dl", "", "v2-diagnostics-provenance");
  Object.entries({ Prompt: call.provenance.prompt_version_id, Context: call.provenance.context_version_id, Schema: call.provenance.schema_version_id, "Role sheet": call.provenance.role_sheet_version_id, "Character card": call.provenance.character_card_version_id }).forEach(([term, value]) => {
    const pair = element("div", ""); pair.append(element("dt", term), element("dd", diagnosticsValue(value))); provenance.append(pair);
  });
  panel.append(element("h3", "Version provenance"), provenance);
  const review = element("section", "", "v2-diagnostics-return");
  review.append(element("p", "Return to Review", "v2-eyebrow"), element("span", call.review_position));
  if (call.review_href) {
    const link = element("a", "Return to the exact causal position →"); link.href = call.review_href; review.append(link);
  }
  panel.append(review);
  return panel;
}

function renderDiagnostics(envelope) {
  lastDiagnosticsEnvelope = envelope;
  const { data, meta } = envelope;
  updateSharedContext(data.context, meta);
  const reader = one("[data-diagnostics-reader]");
  if (!reader) return;
  const layout = element("div", "", "v2-diagnostics-layout");
  layout.append(buildDiagnosticsCallRail(data), buildDiagnosticsDetail(data.selected_call));
  reader.replaceChildren(layout);
  reader.setAttribute("aria-busy", "false");
  updateBanner(
    meta.freshness === "partial" ? "partial" : "calm",
    data.selected_call ? "Stored call evidence is ready" : "No matching call evidence",
    data.partial_reasons[0] || "Reading this view performs no model call and writes no state.",
  );
}

async function loadDiagnostics() {
  try {
    renderDiagnostics(await requestJSON(diagnosticsRequestURL()));
    lastSuccessfulRead = Date.now();
    transportState = "connected";
  } catch (error) {
    transportState = "disconnected";
    updateBanner("disconnected", "Diagnostics could not connect", "No model call or state change was attempted.");
  }
}

function bindDiagnosticsControls() {
  if (page !== "diagnostics") return;
  const form = one("[data-diagnostics-filters]");
  if (!form) return;
  const params = new URLSearchParams(window.location.search);
  Array.from(form.elements).forEach((control) => {
    if (control.name && params.has(control.name)) control.value = params.get(control.name);
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const target = new URL(window.location.href);
    target.searchParams.delete("call_id");
    new FormData(form).forEach((value, key) => {
      if (String(value).trim()) target.searchParams.set(key, String(value).trim());
      else target.searchParams.delete(key);
    });
    window.location.assign(target.toString());
  });
  const clear = one("[data-diagnostics-clear]");
  if (clear) clear.addEventListener("click", () => {
    const target = new URL(window.location.href);
    ["call_id", "run_id", "character_id", "purpose", "status", "attempt", "error"].forEach((key) => target.searchParams.delete(key));
    window.location.assign(target.toString());
  });
}

function prepareRequestURL() {
  const params = new URLSearchParams(window.location.search);
  const query = new URLSearchParams();
  const season = params.get("season_id") || selectedSeason;
  if (season) query.set("season_id", season);
  if (params.get("step")) query.set("step", params.get("step"));
  if (params.get("character_id")) query.set("character_id", params.get("character_id"));
  const suffix = query.toString();
  return `/api/v2/prepare${suffix ? `?${suffix}` : ""}`;
}

function preparePageHref(data, step, characterId = null) {
  const params = new URLSearchParams();
  if (data.context.selected_season_id) params.set("season_id", data.context.selected_season_id);
  params.set("step", step);
  if (characterId) params.set("character_id", characterId);
  return `/v2/prepare?${params.toString()}`;
}

function prepareStatusBadge(status) {
  const labels = {
    approved: "Approved",
    complete: "Complete",
    ready: "Ready",
    ready_for_review: "Ready for review",
    blocked: "Blocked",
    not_started: "Not started",
  };
  const badge = element("span", labels[status] || normalizeStatus(status), "v2-prepare-status");
  badge.dataset.status = status;
  return badge;
}

function buildPrepareChecklist(data) {
  const rail = element("aside", "", "v2-prepare-checklist");
  rail.append(element("p", "Pre-season runbook", "v2-eyebrow"), element("h2", "Eight deliberate steps"));
  const list = element("nav", "", "v2-prepare-steps");
  list.setAttribute("aria-label", "Preparation steps");
  (data.steps || []).forEach((step) => {
    const link = element("a", "", "v2-prepare-step");
    link.href = preparePageHref(data, step.key, step.key === "character_cards" ? data.selected_character_id : null);
    if (step.selected) link.setAttribute("aria-current", "step");
    const number = element("span", String(step.number).padStart(2, "0"), "v2-prepare-step-number");
    const copy = element("span", "", "v2-prepare-step-copy");
    copy.append(element("strong", step.label), element("small", step.detail));
    link.append(number, copy, prepareStatusBadge(step.status));
    list.append(link);
  });
  rail.append(list, element("small", `Workspace v${data.workspace_version} · every action creates an immutable receipt.`));
  return rail;
}

function prepareField(label, value, name, multiline = false) {
  const wrapper = element("label", "", "v2-prepare-field");
  wrapper.append(element("span", label));
  const control = document.createElement(multiline ? "textarea" : "input");
  control.name = name;
  control.value = value || "";
  if (multiline) control.rows = 3;
  wrapper.append(control);
  return wrapper;
}

function prepareListValue(value) {
  return Array.isArray(value) ? value.join("\n") : "";
}

function prepareApprovedTruth(card) {
  const truth = element("aside", "", "v2-approved-truth");
  truth.append(element("p", "Current approved truth", "v2-eyebrow"));
  if (!card.approved_truth) {
    truth.append(element("strong", `Version ${card.version} is the current approved card`), element("p", "No earlier approved version is needed beside it."));
    return truth;
  }
  truth.append(
    element("strong", `Approved v${card.approved_truth.version}`),
    element("p", card.approved_truth.public_brief),
    element("small", `Pronouns: ${card.approved_truth.pronouns}`),
    element("small", `Voice: ${card.approved_truth.voice_anchors.join(" · ")}`),
  );
  return truth;
}

function prepareImpact(title, detail, tone = "neutral") {
  const box = element("section", "", "v2-prepare-impact");
  box.dataset.tone = tone;
  box.append(element("strong", title), element("span", detail));
  return box;
}

async function performPrepareAction(action, options = {}) {
  if (!lastPrepareEnvelope) return;
  const data = lastPrepareEnvelope.data;
  const token = one('meta[name="csrf-token"]');
  const payload = {
    request_id: window.crypto && window.crypto.randomUUID
      ? window.crypto.randomUUID()
      : `prepare-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    season_id: data.context.selected_season_id,
    action,
    expected_version: data.workspace_version,
    ...options,
  };
  updateBanner("loading", "Recording a versioned rehearsal action", "No production command or model call is being submitted.");
  try {
    const response = await fetch("/api/v2/prepare/action", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRF-Token": token ? token.content : "",
      },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || `action failed (${response.status})`);
    await loadPrepare();
    updateBanner(
      "calm",
      `Receipt recorded · workspace v${result.workspace_version}`,
      `${normalizeStatus(result.action)} changed rehearsal evidence only. Production state remains unchanged.`,
    );
  } catch (error) {
    updateBanner("attention", "Preparation action was not recorded", error.message || "Reload the workspace and try again.");
  }
}

function buildCharacterCardsStep(data) {
  const panel = element("article", "", "v2-prepare-focus");
  const cards = data.cards || [];
  const selected = cards.find((card) => card.character_id === data.selected_character_id) || cards[0];
  const approved = cards.filter((card) => card.status === "APPROVED").length;
  panel.append(element("p", "Step 3 of 8 / creator-authored stable input", "v2-eyebrow"), element("h2", `Character cards · ${approved} of ${cards.length} approved`));
  const tabs = element("nav", "", "v2-character-tabs");
  tabs.setAttribute("aria-label", "Character cards");
  cards.forEach((card) => {
    const link = element("a", "", "v2-character-tab");
    link.href = preparePageHref(data, "character_cards", card.character_id);
    if (card.character_id === data.selected_character_id) link.setAttribute("aria-current", "true");
    link.append(element("strong", card.name), element("small", `v${card.version} · ${normalizeStatus(card.status)}`));
    tabs.append(link);
  });
  panel.append(tabs);
  if (!selected) {
    panel.append(element("p", "No character cards are stored in this rehearsal."));
    return panel;
  }
  const header = element("header", "", "v2-prepare-focus-header");
  const heading = element("div", "");
  heading.append(element("p", `Draft and approval history / opening v${selected.derived_opening_version}`, "v2-eyebrow"), element("h3", `${selected.name} · version ${selected.version}`));
  header.append(heading, prepareStatusBadge(selected.status === "APPROVED" ? "approved" : "ready_for_review"));
  panel.append(header);
  const comparison = element("div", "", "v2-card-comparison");
  const form = element("form", "", "v2-character-form");
  form.append(
    prepareField("Pronouns", selected.pronouns, "pronouns"),
    prepareField("Public brief", selected.public_brief, "public_brief", true),
    prepareField("Occupation / skills · one per line", prepareListValue(selected.occupation_skills), "occupation_skills", true),
    prepareField("Voice anchors · one per line", prepareListValue(selected.voice_anchors), "voice_anchors", true),
    prepareField("Habits · one per line", prepareListValue(selected.habits), "habits", true),
  );
  comparison.append(form, prepareApprovedTruth(selected));
  panel.append(comparison);
  const impact = selected.status === "APPROVED"
    ? prepareImpact("Revision impact", "Saving creates a new draft version and invalidates model assignment plus every later receipt. The approved version remains readable.", "attention")
    : prepareImpact("Approval impact", "Approval locks this card version. At 4/4 it unlocks model assignment. It does not choose a model, run preflight, create role sheets, or Green the season.", "calm");
  panel.append(impact);
  const actions = element("div", "", "v2-prepare-actions");
  const save = element("button", "Save as new draft version");
  save.type = "button";
  save.addEventListener("click", () => {
    const values = new FormData(form);
    const lines = (name) => String(values.get(name) || "").split("\n").map((item) => item.trim()).filter(Boolean);
    performPrepareAction("save_card_revision", {
      character_id: selected.character_id,
      card: {
        pronouns: String(values.get("pronouns") || "").trim(),
        public_brief: String(values.get("public_brief") || "").trim(),
        occupation_skills: lines("occupation_skills"),
        voice_anchors: lines("voice_anchors"),
        habits: lines("habits"),
      },
    });
  });
  actions.append(save);
  if (["DRAFT", "STALE_APPROVED"].includes(selected.status)) {
    const approve = element("button", "Review and approve this version", "is-primary");
    approve.type = "button";
    approve.addEventListener("click", () => performPrepareAction("approve_card", { character_id: selected.character_id }));
    actions.append(approve);
  }
  panel.append(actions, element("small", `Version history: ${[selected.version, ...(selected.prior_versions || [])].map((version) => `v${version}`).join(" · ")}`));
  return panel;
}

function buildPrepareEvidence(data, step) {
  const panel = element("article", "", "v2-prepare-focus");
  panel.append(element("p", `Step ${step.number} of 8 / manual evidence`, "v2-eyebrow"), element("h2", step.label), prepareStatusBadge(step.status));
  const receipt = data.latest_receipts[step.key];
  if (receipt) {
    panel.append(prepareImpact("Durable receipt", `${receipt.receipt_id} · workspace v${receipt.workspace_version} · ${normalizeStatus(receipt.status)}`, "calm"));
  }
  const descriptions = {
    idea: ["Approved season idea", data.idea || "No idea stored", `Version ${data.idea_version}`],
    opening: ["Approved opening", `Opening version ${data.opening_version} is the stable source for all character cards.`, "A revision preserves this version and invalidates every dependent approval."],
    model_assignment: ["Stored assignment evidence", data.model_assignment ? `${data.model_assignment.manifest_name} · version ${data.model_assignment.version}` : "No assignment manifest stored", "The dashboard displays candidate bindings only here. It never auto-selects."],
    preflight: ["Stored-only preflight", "Record database, path, and binding evidence without contacting a model.", "Model availability remains unprobed."],
    private_preparation: ["Private preparation evidence", "Confirm that role-sheet and orientation fixtures were reviewed.", "Private text stays closed until deliberate reveal, and no actor is called."],
    schedule_preview: ["Schedule preview", "Review 7 days and 21 slots in America/Los_Angeles.", "The preview does not change the durable production schedule."],
    green_review: ["Green review", "Record that the preparation evidence is ready for a separate operator decision.", "This receipt does not arm S02, submit a command, or start the worker."],
  };
  const copy = descriptions[step.key] || [step.label, step.detail, "No automatic action is available."];
  panel.append(element("h3", copy[0]), element("p", copy[1]), element("small", copy[2]));
  if (step.key === "model_assignment" && data.model_assignment) {
    const assignments = element("dl", "", "v2-assignment-list");
    Object.entries(data.model_assignment.assignments || {}).forEach(([role, model]) => {
      const pair = element("div", ""); pair.append(element("dt", role), element("dd", model)); assignments.append(pair);
    });
    panel.append(assignments);
  }
  if (step.key === "private_preparation") {
    panel.append(buildPrivatePreparationReview(data));
  }
  if (step.key === "opening") {
    panel.append(prepareImpact("Explicit invalidation", "Creating opening v" + (Number(data.opening_version) + 1) + " marks approved cards stale and removes every dependent receipt. Prior versions remain readable.", "attention"));
  } else {
    panel.append(prepareImpact("Action boundary", copy[2], step.key === "green_review" ? "attention" : "neutral"));
  }
  const actionNames = {
    opening: ["revise_opening", "Create versioned rehearsal revision"],
    model_assignment: ["approve_model_assignment", "Approve stored assignments"],
    preflight: ["record_preflight", "Record stored-only preflight"],
    private_preparation: ["record_private_preparation", "Record private evidence reviewed"],
    schedule_preview: ["record_schedule_preview", "Record schedule preview"],
    green_review: ["record_green_review", "Record Green readiness receipt"],
  };
  const action = actionNames[step.key];
  if (action && !receipt) {
    const button = element("button", action[1], "v2-prepare-primary-action");
    button.type = "button";
    button.disabled = step.status === "blocked";
    button.addEventListener("click", () => performPrepareAction(action[0]));
    panel.append(button);
  }
  return panel;
}

function buildPrivatePreparationReview(data) {
  const review = element("section", "", "v2-private-preparation-review");
  review.append(element("h3", "Approved cards and generated private extensions"));
  (data.cards || []).forEach((card) => {
    const row = element("article", "", "v2-private-artifact-row");
    const approved = element("section", "", "v2-private-card-source");
    approved.append(
      element("p", `${card.name} / approved source`, "v2-eyebrow"),
      element("strong", `Character card v${card.version}`),
      element("span", card.public_brief),
      element("small", `Voice: ${card.voice_anchors.join(" · ")}`),
    );
    const artifacts = element("section", "", "v2-private-artifact-summaries");
    (data.private_artifacts || []).filter((item) => item.character_id === card.character_id).forEach((item) => {
      const artifact = element("article", "", "v2-private-artifact-summary");
      artifact.append(
        element("strong", `${normalizeStatus(item.artifact_kind)} v${item.version}`),
        element("span", `${normalizeStatus(item.status)} · from card v${item.source_character_card_version}`),
      );
      const button = element("button", `Reveal ${normalizeStatus(item.artifact_kind)}`);
      button.type = "button";
      button.addEventListener("click", async () => {
        const existing = one("[data-private-artifact-disclosure]", artifact);
        if (existing) { existing.remove(); button.textContent = `Reveal ${normalizeStatus(item.artifact_kind)}`; return; }
        button.disabled = true;
        try {
          const envelope = await requestJSON(item.disclosure_href);
          const disclosure = element("section", "", "v2-private-artifact-disclosure");
          disclosure.dataset.privateArtifactDisclosure = "true";
          disclosure.append(
            element("pre", JSON.stringify(envelope.data.content, null, 2)),
            element("small", envelope.data.evidence_note),
          );
          artifact.append(disclosure);
          button.textContent = "Close private evidence";
        } catch (error) {
          artifact.append(element("p", "Private fixture evidence could not be read.", "v2-review-empty"));
        } finally {
          button.disabled = false;
        }
      });
      artifact.append(button);
      artifacts.append(artifact);
    });
    row.append(approved, artifacts);
    review.append(row);
  });
  return review;
}

function buildPrepareHistory(data) {
  const history = element("aside", "", "v2-prepare-history");
  history.append(element("p", "Version and invalidation ledger", "v2-eyebrow"));
  const events = data.invalidations || [];
  if (!events.length) {
    history.append(element("strong", "No invalidation event recorded"), element("span", "Dependent evidence still follows the approved opening and card versions."));
    return history;
  }
  events.slice(0, 5).forEach((event) => {
    const item = element("article", "");
    item.append(element("strong", `${normalizeStatus(event.source_step)} v${event.source_version}`), element("span", event.reason), element("small", `Invalidated: ${event.invalidated_steps.join(" · ")}`));
    history.append(item);
  });
  return history;
}

function renderPrepare(envelope) {
  lastPrepareEnvelope = envelope;
  const { data, meta } = envelope;
  updateSharedContext(data.context, meta);
  const reader = one("[data-prepare-reader]");
  if (!reader) return;
  if (data.state !== "ready") {
    reader.replaceChildren(element("p", data.partial_reasons[0] || "No preparation rehearsal is stored for this season.", "v2-review-empty"));
    updateBanner("partial", "Preparation rehearsal unavailable", data.partial_reasons[0] || "Select an isolated season with a preparation ledger.");
    return;
  }
  text("[data-prepare-boundary]", `${data.model_calls_performed} model calls · production state ${data.production_state_unchanged ? "unchanged" : "unknown"} · workspace v${data.workspace_version}`);
  const selectedStep = (data.steps || []).find((step) => step.selected) || data.steps[0];
  const focus = selectedStep && selectedStep.key === "character_cards"
    ? buildCharacterCardsStep(data)
    : buildPrepareEvidence(data, selectedStep || { number: 1, key: "idea", label: "Season idea", status: "not_started", detail: "Unavailable" });
  const layout = element("div", "", "v2-prepare-layout");
  layout.append(buildPrepareChecklist(data), focus, buildPrepareHistory(data));
  reader.replaceChildren(layout);
  reader.setAttribute("aria-busy", "false");
  const complete = (data.steps || []).filter((step) => ["approved", "complete", "ready"].includes(step.status)).length;
  updateBanner("calm", `${complete} of 8 preparation steps have durable evidence`, "Continue one deliberate step at a time. No production state or model has been touched.");
}

async function loadPrepare() {
  try {
    renderPrepare(await requestJSON(prepareRequestURL()));
    lastSuccessfulRead = Date.now();
    transportState = "connected";
  } catch (error) {
    transportState = "disconnected";
    updateBanner("disconnected", "Preparation workspace could not connect", "No rehearsal action, model call, or production command was attempted.");
  }
}

function formatDuration(seconds) {
  if (seconds === null || seconds === undefined) return "not started";
  const total = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = Math.floor(total % 60);
  return [hours, minutes, secs].map((part) => String(part).padStart(2, "0")).join(":");
}

function livePanel(eyebrow, title, className = "") {
  const panel = element("article", "", `v2-live-panel ${className}`.trim());
  panel.append(element("p", eyebrow, "v2-eyebrow"), element("h2", title));
  return panel;
}

function liveActionButton(label, action) {
  const button = element("button", label);
  button.type = "button";
  button.dataset.liveReviewAction = action;
  return button;
}

function renderLiveOperational(envelope) {
  const data = envelope.data;
  const grid = element("div", "", "v2-live-grid");
  if (data.state === "no_season") {
    const empty = livePanel("Live", "No season is selected");
    empty.append(element("p", "Live supervision appears after a season has durable state."));
    grid.append(empty);
    return grid;
  }
  const run = data.run;
  const recovery = data.recovery;
  if (recovery) {
    const truth = livePanel("Current durable truth", `${recovery.run_id} · stopped safely`, "v2-live-wide v2-live-recovery-truth");
    truth.append(
      element("p", recovery.reason),
      element("small", `Recovery ${recovery.recovery_id} · v${recovery.version} · ${recovery.queue_effect}`),
    );
    grid.append(truth);
  } else if (run) {
    const performance = livePanel("Current performance", `Run ${run.run_number} · ${normalizeStatus(run.status)}`, "v2-live-wide");
    performance.append(
      element("p", run.active_purpose),
      element("small", `Day ${run.day_number} · slot ${run.slot_number} · scheduled ${formatTime(run.scheduled_local)} · actual ${formatTime(run.actual_started_at)} · elapsed ${formatDuration(run.elapsed_seconds)} · delay ${run.delay || "not recorded"}`),
      element("strong", `${run.accepted_count} accepted records · ${run.accepted_rounds} rounds`, "v2-live-count"),
    );
    if (run.call.call_id) {
      const call = element("a", `${run.call.character_id || "Director"} · attempt ${run.call.attempt} · ${normalizeStatus(run.call.status)}`);
      call.href = run.call.detail_href;
      performance.append(call);
    }
    grid.append(performance);
  }

  const beat = livePanel("Last accepted beat", data.last_accepted_beat.available ? (data.last_accepted_beat.speaker_name || "Accepted story") : "No accepted beat stored");
  beat.append(
    element("blockquote", data.last_accepted_beat.excerpt || "Recovery and retries will remain anchored to durable accepted evidence."),
    element("small", data.last_accepted_beat.receipt || "No accepted receipt available"),
  );
  if (data.transcript_href) {
    const open = element("button", liveTranscriptEnvelope ? "Transcript open" : "Open transcript");
    open.type = "button";
    open.dataset.liveTranscriptOpen = "";
    if (liveTranscriptEnvelope) open.disabled = true;
    beat.append(open);
  }
  grid.append(beat);

  const queue = livePanel("Worker and queue", data.worker.label);
  const lease = data.active_work
    ? `${data.active_work.work_id} · lease ${data.active_work.lease_until ? `to ${formatTime(data.active_work.lease_until)}` : "deadline unavailable"}`
    : "No active lease";
  queue.append(
    element("p", lease),
    element("small", `${data.queued_work.length} queued work item${data.queued_work.length === 1 ? "" : "s"} · ${data.next_direction}`),
  );
  grid.append(queue);

  if (recovery) {
    const paths = livePanel("Choose a recovery path", "No choice selected", "v2-live-wide v2-recovery-paths");
    paths.append(element("p", "Each path opens a separate consequence review. Navigating away does not resolve recovery."));
    const cards = element("div", "", "v2-recovery-cards");
    [
      ["retry", "Retry", "Preserve failed attempts and place a new run attempt ahead of later work."],
      ["skip", "Skip this run", "Keep the last accepted beat, record a visible gap, and allow later work."],
      ["private_close", "End season privately", "Open the separate read-only private-close journey; submit nothing here."],
    ].forEach(([action, title, copy]) => {
      const card = element("section", "");
      card.append(element("h3", title), element("p", copy), liveActionButton(`Review ${action === "private_close" ? "private end" : action}`, action));
      cards.append(card);
    });
    paths.append(cards);
    grid.append(paths);
  } else {
    const controls = livePanel("Valid controls", "Review impact before submitting");
    data.controls.forEach((control) => {
      const row = element("div", "", "v2-live-control");
      row.append(element("strong", control.action === "pause" ? "Pause after current checkpoint" : "Resume durable work"));
      if (control.available) row.append(liveActionButton(`Review ${control.action}`, control.action));
      else row.append(element("small", control.disabled_reason));
      controls.append(row);
    });
    grid.append(controls);
    const day = livePanel("Day completion", data.day_completion.available ? `Day ${data.day_completion.day_number}` : "Not scheduled");
    day.append(element("p", `${data.day_completion.resolved_runs} of ${data.day_completion.scheduled_runs} scheduled runs resolved.`), element("small", `Closure ${normalizeStatus(data.day_completion.state)}.`));
    grid.append(day);
  }
  return grid;
}

function renderLive(envelope, { preserveTranscript = true } = {}) {
  lastLiveEnvelope = envelope;
  updateSharedContext(envelope.data.context, envelope.meta);
  updateWorker(envelope.data.worker);
  const recovery = Boolean(envelope.data.recovery);
  text("[data-live-summary]", recovery ? "The story is stopped safely before canon. Review evidence and consequences; nothing advances without one explicit choice." : "The worker continues autonomously. Accepted story evidence stays still while you read.");
  text("[data-live-attention]", recovery ? "Action required" : "No attention");
  updateBanner(recovery ? "attention" : "calm", recovery ? "Recovery required · safe stop" : "Live supervision is healthy", recovery ? "Invalid output is excluded from canon, transcript, and accepted counts." : "Closing this dashboard does not alter worker progress.");
  const reader = one("[data-live-reader]");
  if (!reader) return;
  const operational = renderLiveOperational(envelope);
  operational.classList.add("v2-live-operational");
  const existing = one(".v2-live-operational", reader);
  if (existing && preserveTranscript) existing.replaceWith(operational);
  else {
    reader.replaceChildren(operational);
    if (!preserveTranscript) liveTranscriptEnvelope = null;
  }
  reader.setAttribute("aria-busy", "false");
  const newer = one("[data-live-newer]", reader);
  if (newer && liveTranscriptEnvelope) {
    const difference = Math.max(0, Number(envelope.data.transcript_accepted_count) - Number(liveTranscriptEnvelope.data.accepted_count));
    newer.hidden = difference === 0;
    const label = one("strong", newer);
    if (label) label.textContent = `${difference} newer accepted record${difference === 1 ? "" : "s"} available`;
  }
}

function renderLiveTranscript(envelope) {
  liveTranscriptEnvelope = envelope;
  const reader = one("[data-live-reader]");
  if (!reader) return;
  one(".v2-live-transcript", reader)?.remove();
  const panel = livePanel("Stable transcript", `Opened at ${envelope.data.accepted_count} accepted records`, "v2-live-wide v2-live-transcript");
  const newer = element("section", "", "v2-new-material");
  newer.dataset.liveNewer = "";
  newer.hidden = true;
  newer.append(element("strong", "New accepted material is available"), element("span", "This pane has not moved or redrawn."));
  const load = element("button", "Load new records");
  load.type = "button";
  load.dataset.liveLoadNew = "";
  newer.append(load);
  panel.append(newer);
  const records = element("div", "", "v2-live-transcript-records");
  envelope.data.records.forEach((record) => {
    const item = element("article", "");
    item.append(element("small", `Accepted ${record.accepted_sequence} · round ${record.round_number}`), element("strong", record.speaker_name), element("p", record.content || "Accepted content is unavailable."));
    records.append(item);
  });
  panel.append(records, element("small", "Operational polling continues outside this pane. Reloading accepted material is always creator-triggered."));
  reader.append(panel);
  const open = one("[data-live-transcript-open]");
  if (open) { open.textContent = "Transcript open"; open.disabled = true; }
}

async function openLiveTranscript() {
  const href = lastLiveEnvelope?.data?.transcript_href;
  if (!href) return;
  renderLiveTranscript(await requestJSON(href));
}

async function openLiveImpact(action) {
  const seasonId = lastLiveEnvelope?.data?.context?.selected_season_id;
  if (!seasonId) return;
  const review = await requestJSON(`/api/v2/live/impact-review?season_id=${encodeURIComponent(seasonId)}&action=${encodeURIComponent(action)}`);
  const dialog = one("[data-live-impact]");
  const body = one("[data-live-impact-body]");
  if (!dialog || !body) return;
  body.replaceChildren(element("p", "Impact review", "v2-eyebrow"), element("h2", review.title));
  const list = element("ul", "");
  review.consequences.forEach((item) => list.append(element("li", item)));
  body.append(list, element("code", `snapshot ${review.snapshot_hash.slice(0, 12)} · season v${review.snapshot.season_version}${review.snapshot.run_version === null ? "" : ` · run v${review.snapshot.run_version}`}`));
  if (review.typed_confirmation) {
    const label = element("label", "", "v2-impact-confirmation");
    label.append(element("span", `Type ${review.typed_confirmation} to confirm`));
    const input = document.createElement("input");
    input.dataset.liveTypedConfirmation = "";
    input.autocomplete = "off";
    label.append(input);
    body.append(label);
  }
  if (review.executable) {
    const submit = element("button", `Confirm ${review.action}`, "v2-live-submit");
    submit.type = "button";
    submit.addEventListener("click", () => submitLiveAction(review, submit));
    body.append(submit);
  } else {
    const link = element("a", "Continue to private-close review");
    link.href = review.private_close_href;
    body.append(link, element("small", "Recovery remains unchanged. DASH-06 implements this destination."));
  }
  dialog.showModal();
}

async function submitLiveAction(review, button) {
  const csrf = one('meta[name="csrf-token"]')?.content || "";
  const typed = one("[data-live-typed-confirmation]")?.value || null;
  button.disabled = true;
  try {
    const response = await fetch("/api/v2/live/action", {
      method: "POST", credentials: "same-origin",
      headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({
        request_id: `live-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        season_id: review.snapshot.season_id, action: review.action,
        snapshot_hash: review.snapshot_hash,
        expected_season_version: review.snapshot.season_version,
        expected_run_version: review.snapshot.run_version,
        expected_recovery_version: review.snapshot.recovery_version,
        typed_confirmation: typed,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Live action was rejected");
    const body = one("[data-live-impact-body]");
    if (body) body.replaceChildren(element("p", "Durable receipt", "v2-eyebrow"), element("h2", `${normalizeStatus(result.action)} recorded`), element("code", result.receipt_id), element("p", `Reviewed snapshot ${result.review_snapshot_hash.slice(0, 12)} · exact replay ${result.replayed ? "yes" : "no"}.`));
    liveTranscriptEnvelope = null;
    await loadLive({ preserveTranscript: false });
  } catch (error) {
    button.disabled = false;
    const message = element("p", error.message || "Live action was rejected", "v2-live-action-error");
    button.before(message);
  }
}

function bindLiveControls() {
  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    const review = target?.closest("[data-live-review-action]");
    if (review) openLiveImpact(review.dataset.liveReviewAction).catch(() => updateBanner("disconnected", "Impact review could not open", "No action was submitted."));
    if (target?.closest("[data-live-transcript-open]")) openLiveTranscript().catch(() => updateBanner("partial", "Transcript could not open", "Operational truth remains visible and unchanged."));
    if (target?.closest("[data-live-load-new]")) openLiveTranscript().catch(() => {});
  });
}

async function loadLive(options = {}) {
  try {
    const envelope = await requestJSON(`/api/v2/live${querySuffix()}`);
    renderLive(envelope, options);
    lastSuccessfulRead = Date.now();
    transportState = "connected";
  } catch (error) {
    transportState = "disconnected";
    updateBanner("disconnected", "Live supervision could not connect", "The last readable evidence remains visible; no command was attempted.");
  }
}

function seasonsPanel(title, detail = "") {
  const panel = element("article", "", "v2-seasons-panel");
  panel.append(element("p", "Seasons / private operator", "v2-eyebrow"), element("h2", title));
  if (detail) panel.append(element("p", detail));
  return panel;
}

function seasonsList(items, empty = "None") {
  const list = element("ul", "", "v2-seasons-list");
  if (!items.length) list.append(element("li", empty));
  else items.forEach((item) => list.append(element("li", item)));
  return list;
}

function renderPrivateClose(review) {
  lastSeasonsReview = review;
  const snapshot = review.snapshot;
  const reader = one("[data-seasons-reader]");
  if (!reader) return;
  const grid = element("section", "", "v2-seasons-grid");
  const state = seasonsPanel(
    review.executable ? "Private-close review is ready" : "Private-close review is not actionable",
    review.executable ? "This is a versioned review only. The command appears after you open the impact review." : `Season is ${normalizeStatus(snapshot.season_status)}. A close command is not available from this state.`,
  );
  const facts = element("dl", "", "v2-seasons-facts");
  [
    ["Lifecycle", `${normalizeStatus(snapshot.season_status)} · v${snapshot.season_version}`],
    ["Accepted records", String(snapshot.accepted_story_records)],
    ["Archive", snapshot.archive_reachable ? "reachable" : "not reachable"],
    ["Integrity", snapshot.database_integrity],
    ["Outbox", `${snapshot.artifact_outbox_pending} pending`],
  ].forEach(([label, value]) => {
    const row = element("div", "");
    row.append(element("dt", label), element("dd", value));
    facts.append(row);
  });
  state.append(facts);
  if (review.executable) {
    const button = element("button", "Review private close", "v2-seasons-primary");
    button.type = "button";
    button.dataset.seasonsPrivateClose = "";
    state.append(button);
  }
  const unresolved = seasonsPanel("Unresolved work remains visible", "Private close retains this evidence in the snapshot, handoff, and receipt.");
  unresolved.append(seasonsList((snapshot.unresolved || []).map((item) => `${item.kind} · ${item.id} · ${normalizeStatus(item.status)}`), "No unresolved run or diary evidence."));
  const boundary = seasonsPanel("Boundaries", "The close command will not publish, expose, delete, rewrite, or clear private evidence.");
  boundary.append(seasonsList((review.effects?.will || []).map((item) => `Will: ${item}`)), seasonsList((review.effects?.will_not || []).map((item) => `Will not: ${item}`)));
  grid.append(state, unresolved, boundary);
  reader.replaceChildren(grid);
  reader.setAttribute("aria-busy", "false");
  updateBanner("calm", "Private-close evidence is readable", `Snapshot ${review.snapshot_hash.slice(0, 12)} · opening, refresh, and navigation do not submit a command.`);
}

function renderPublicationPreview(review) {
  lastPublicationPreview = review;
  const reader = one("[data-seasons-reader]");
  if (!reader) return;
  const snapshot = review.snapshot;
  const grid = element("section", "", "v2-seasons-grid");
  const gates = seasonsPanel("Separate publication review", `Private close receipt ${snapshot.closure_receipt_id} is verified. ${snapshot.publication_eligible ? "No pending model calls block this review." : `${snapshot.pending_model_calls} pending model call${snapshot.pending_model_calls === 1 ? "" : "s"} still blocks publication.`} This release has no access to plans, prompts, raw calls, model identities, role sheets, memory, wellness text, or held, missing, and revoked diaries.`);
  gates.append(element("code", `private archive ${snapshot.private_archive_sha256.slice(0, 12)} · projection v${snapshot.projection_version}`));
  const choices = seasonsPanel("Diary allowlist", "Only written or late diaries can be marked cleared. All other diaries remain private.");
  const form = element("div", "", "v2-seasons-decisions");
  const diaries = review.preview?.diaries || [];
  const excluded = review.preview?.excluded || [];
  const allIds = new Set([...diaries.map((entry) => entry.diary_id), ...excluded.map((entry) => entry.diary_id)]);
  [...allIds].forEach((diaryId) => {
    const cleared = (review.snapshot.resolved_diary_decisions || {})[diaryId] === "CLEARED";
    const isEligible = diaries.some((entry) => entry.diary_id === diaryId) || (excluded.find((entry) => entry.diary_id === diaryId)?.reason || "").startsWith("written") || (excluded.find((entry) => entry.diary_id === diaryId)?.reason || "").startsWith("late");
    const label = element("label", "", "v2-seasons-decision");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = cleared;
    input.disabled = !isEligible;
    input.dataset.seasonsDiaryId = diaryId;
    input.addEventListener("change", () => { seasonsDecisions[diaryId] = input.checked ? "CLEARED" : "PRIVATE"; });
    label.append(input, element("strong", diaryId), element("small", isEligible ? "Clear for the reviewed public projection" : "Must remain private"));
    form.append(label);
  });
  const previewButton = element("button", "Update exact preview");
  previewButton.type = "button";
  previewButton.dataset.seasonsPreview = "";
  choices.append(form, previewButton);
  const projection = seasonsPanel("Exact public projection", "Only the following diary files and manifest fields enter the immutable output.");
  projection.append(seasonsList(diaries.map((entry) => `${entry.diary_id} → ${entry.path}`), "No diary is currently allowlisted."));
  const publish = element("button", "Review publication impact", "v2-seasons-primary");
  publish.type = "button";
  publish.dataset.seasonsPublish = "";
  publish.disabled = !snapshot.publication_eligible;
  projection.append(publish);
  grid.append(gates, choices, projection);
  reader.replaceChildren(grid);
  reader.setAttribute("aria-busy", "false");
  updateBanner("calm", "Publication preview is separate and allowlisted", `Snapshot ${review.snapshot_hash.slice(0, 12)} · the private archive remains unchanged.`);
}

async function openPrivateCloseImpact() {
  const review = lastSeasonsReview;
  if (!review) return;
  const dialog = one("[data-seasons-impact]");
  const body = one("[data-seasons-impact-body]");
  if (!dialog || !body) return;
  const input = document.createElement("input");
  input.autocomplete = "off";
  input.dataset.seasonsTypedConfirmation = "";
  const label = element("label", "", "v2-impact-confirmation");
  label.append(element("span", `Type ${review.typed_confirmation} to confirm`), input);
  const submit = element("button", "End this season privately", "v2-live-submit");
  submit.type = "button";
  submit.addEventListener("click", () => submitPrivateClose(review, submit));
  body.replaceChildren(element("p", "Impact review", "v2-eyebrow"), element("h2", "End this season privately"), seasonsList(review.effects.will || []), seasonsList(review.effects.will_not || []), label, submit);
  dialog.showModal();
}

async function submitPrivateClose(review, button) {
  button.disabled = true;
  try {
    const result = await postJSON("/api/v2/seasons/private-close", {
      request_id: `private-close-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      season_id: review.snapshot.season_id,
      snapshot_hash: review.snapshot_hash,
      expected_season_version: review.snapshot.season_version,
      typed_confirmation: one("[data-seasons-typed-confirmation]")?.value || "",
    });
    const body = one("[data-seasons-impact-body]");
    if (body) body.replaceChildren(element("p", "Durable private-close receipt", "v2-eyebrow"), element("h2", "Private complete"), element("code", result.receipt_id), element("p", `Verified handoff ${result.handoff.handoff_id}. Unresolved work remains recorded.`));
    await loadSeasons();
  } catch (error) {
    button.disabled = false;
    button.before(element("p", error.message || "Private close was rejected", "v2-live-action-error"));
  }
}

async function refreshPublicationPreview() {
  const seasonId = selectedSeason;
  if (!seasonId) return;
  const review = await postJSON("/api/v2/seasons/publication-preview", { season_id: seasonId, diary_decisions: seasonsDecisions });
  Object.assign(seasonsDecisions, review.snapshot.resolved_diary_decisions || {});
  renderPublicationPreview(review);
}

async function openPublicationImpact() {
  const review = lastPublicationPreview;
  if (!review) return;
  const dialog = one("[data-seasons-impact]");
  const body = one("[data-seasons-impact-body]");
  if (!dialog || !body) return;
  const typed = document.createElement("input");
  typed.autocomplete = "off";
  typed.dataset.seasonsTypedPublish = "";
  const label = element("label", "", "v2-impact-confirmation");
  label.append(element("span", `Type publish ${review.snapshot.season_id} to confirm`), typed);
  const checks = ["Wellness review is complete", "Privacy review is complete", "Consent decisions are complete"].map((copy, index) => {
    const label = element("label", "", "v2-seasons-confirmation");
    const input = document.createElement("input");
    input.type = "checkbox"; input.dataset.seasonsConfirmation = String(index);
    label.append(input, document.createTextNode(copy));
    return label;
  });
  const submit = element("button", "Publish reviewed projection", "v2-live-submit");
  submit.type = "button";
  submit.addEventListener("click", () => submitPublication(review, submit));
  body.replaceChildren(element("p", "Separate release confirmation", "v2-eyebrow"), element("h2", "Publish only the reviewed projection"), element("code", `snapshot ${review.snapshot_hash.slice(0, 12)}`), label, ...checks, submit);
  dialog.showModal();
}

async function submitPublication(review, button) {
  button.disabled = true;
  try {
    const checks = all("[data-seasons-confirmation]").map((input) => input.checked);
    const result = await postJSON("/api/v2/seasons/publish", {
      request_id: `publish-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      season_id: review.snapshot.season_id, snapshot_hash: review.snapshot_hash,
      expected_season_version: review.snapshot.season_version,
      typed_confirmation: one("[data-seasons-typed-publish]")?.value || "",
      diary_decisions: seasonsDecisions,
      wellness_confirmed: checks[0], privacy_reviewed: checks[1], consent_confirmed: checks[2],
    });
    const body = one("[data-seasons-impact-body]");
    if (body) body.replaceChildren(element("p", "Immutable publication receipt", "v2-eyebrow"), element("h2", "Projection published"), element("code", result.receipt_id), element("p", `The private archive hash remains ${result.private_archive_sha256.slice(0, 12)}.`));
    await loadSeasons();
  } catch (error) {
    button.disabled = false;
    button.before(element("p", error.message || "Publication was rejected", "v2-live-action-error"));
  }
}

function bindSeasonsControls() {
  document.addEventListener("click", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest("[data-seasons-private-close]")) openPrivateCloseImpact();
    if (target?.closest("[data-seasons-preview]")) refreshPublicationPreview().catch(() => updateBanner("partial", "Publication preview could not update", "No publication was submitted."));
    if (target?.closest("[data-seasons-publish]")) openPublicationImpact();
  });
}

async function loadSeasons() {
  try {
    const base = `/api/v2/seasons${querySuffix()}`;
    let review = await requestJSON(base);
    if (review.snapshot?.season_status === "PRIVATE_COMPLETE") {
      seasonsDecisions = review.snapshot.resolved_diary_decisions || seasonsDecisions;
      review = await postJSON("/api/v2/seasons/publication-preview", { season_id: selectedSeason, diary_decisions: seasonsDecisions });
      Object.assign(seasonsDecisions, review.snapshot.resolved_diary_decisions || {});
      renderPublicationPreview(review);
    } else {
      renderPrivateClose(review);
    }
    lastSuccessfulRead = Date.now();
    transportState = "connected";
  } catch (error) {
    transportState = "disconnected";
    updateBanner("disconnected", "Seasons review could not connect", "The last readable evidence remains visible; no close or publication command was attempted.");
  }
}

async function requestJSON(url) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) throw new Error(`snapshot request failed (${response.status})`);
  return response.json();
}

async function postJSON(url, payload) {
  const csrf = one('meta[name="csrf-token"]')?.content || "";
  const response = await fetch(url, {
    method: "POST", credentials: "same-origin",
    headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `request failed (${response.status})`);
  return result;
}

function querySuffix() {
  return selectedSeason ? `?season_id=${encodeURIComponent(selectedSeason)}` : "";
}

async function refreshHome() {
  try {
    const envelope = await requestJSON(`/api/v2/home${querySuffix()}`);
    lastEnvelope = envelope;
    lastSuccessfulRead = Date.now();
    transportState = "connected";
    renderHome(envelope);
  } catch (error) {
    transportState = "disconnected";
    document.body.dataset.snapshotState = "disconnected";
    if (lastEnvelope) {
      updateBanner(
        "disconnected",
        "Disconnected · last snapshot retained",
        "Operational truth may have changed. The visible content has not been cleared or replaced.",
      );
      text("[data-freshness-badge]", "Disconnected · last snapshot retained");
    } else {
      updateBanner(
        "disconnected",
        "Dashboard could not read durable state",
        "No prior snapshot is available in this page session.",
      );
      text("[data-freshness-badge]", "Disconnected · no snapshot");
    }
  }
}

async function refreshContext() {
  try {
    const envelope = await requestJSON(`/api/v2/context${querySuffix()}`);
    transportState = "connected";
    lastSuccessfulRead = Date.now();
    updateSharedContext(envelope.data, envelope.meta);
    updateBanner(
      "context",
      `${envelope.data.selected_season_id || "No season"} context retained`,
      `${envelope.meta.environment} · checked ${formatTime(envelope.meta.checked_at)} · no workflow commands available`,
    );
    document.body.dataset.snapshotState = envelope.meta.freshness;
  } catch (error) {
    transportState = "disconnected";
    document.body.dataset.snapshotState = "disconnected";
    updateBanner(
      "disconnected",
      "Shared context is disconnected",
      "The server-rendered selection remains visible; no command was attempted.",
    );
  }
}

async function refresh() {
  if (page === "home") await refreshHome();
  else if (page === "prepare") {
    if (!lastPrepareEnvelope) await loadPrepare();
    else await refreshContext();
  }
  else if (page === "live") await loadLive({ preserveTranscript: true });
  else if (page === "review") {
    if (!lastReviewEnvelope) {
      await Promise.all([loadReview(), refreshReviewOperationalContext()]);
    } else {
      await Promise.all([probeReview(), refreshReviewOperationalContext()]);
    }
  }
  else if (page === "diagnostics") {
    if (!lastDiagnosticsEnvelope) await loadDiagnostics();
    else await refreshContext();
  }
  else if (page === "seasons") await loadSeasons();
  else await refreshContext();
}

function checkSnapshotAge() {
  if (!lastSuccessfulRead || transportState === "disconnected") return;
  if (Date.now() - lastSuccessfulRead <= 90000) return;
  transportState = "stale_readable";
  document.body.dataset.snapshotState = "stale_readable";
  updateBanner(
    "stale_readable",
    "Stale but readable",
    "The last durable snapshot remains visible while a newer read is unavailable.",
  );
  text("[data-freshness-badge]", "Stale readable · last snapshot retained");
}

bindSeasonPickers();
bindReviewControls();
bindDiagnosticsControls();
bindLiveControls();
bindSeasonsControls();
refresh();
window.setInterval(() => refresh(), 60000);
window.setInterval(checkSnapshotAge, 15000);
