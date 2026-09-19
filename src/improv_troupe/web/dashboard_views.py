"""Escaped HTML composition and packaged static assets for the private dashboard."""

from __future__ import annotations

import html
from importlib.resources import files


_ASSETS = {
    "dashboard-login.css": "text/css",
    "dashboard-legacy.css": "text/css",
    "dashboard-legacy.js": "text/javascript",
    "dashboard.css": "text/css",
    "dashboard.js": "text/javascript",
}


def static_asset(name: str) -> tuple[bytes, str] | None:
    """Return one allowlisted packaged asset without accepting filesystem paths."""
    content_type = _ASSETS.get(name)
    if content_type is None:
        return None
    resource = files("improv_troupe.web").joinpath("static", name)
    return resource.read_bytes(), content_type


def login_html() -> str:
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Simulation Query — sign in</title><link rel="stylesheet" href="/assets/dashboard-login.css"></head>
<body><main class="card"><p class="eyebrow">AI Improv Troupe / private console</p><h1>Simulation Query</h1><p>Sign in to inspect the troupe’s operational state. Season records, diaries, and recovery controls stay on the private network.</p><form method="post"><label for="username">Username<input id="username" name="username" autocomplete="username" autofocus required></label><label for="password">Password<input id="password" name="password" type="password" autocomplete="current-password" required></label><button type="submit">Enter the console</button></form><small>This is an owner-only dashboard. It does not expose prompts, private role sheets, or raw wellness notes.</small></main></body></html>"""


def legacy_dashboard_html(csrf: str) -> str:
    token = html.escape(csrf, quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="csrf-token" content="{token}"><title>Simulation Query — private dashboard</title><link rel="stylesheet" href="/assets/dashboard-legacy.css"><script src="/assets/dashboard-legacy.js" defer></script></head>
<body><div class="shell">
  <header class="topbar"><div class="brand"><span class="brand-mark" aria-hidden="true">✦</span><div><p class="eyebrow">AI Improv Troupe / operator console</p><h1>Simulation Query</h1></div></div><div class="top-actions"><span id="connection" class="connection"><span class="connection-dot" aria-hidden="true"></span><span id="connection-label">Connecting</span></span><button id="refresh" class="button button-quiet" type="button">Refresh</button><form method="post" action="/logout"><input type="hidden" name="csrf_token" value="{token}"><button class="button button-quiet" type="submit">Sign out</button></form></div></header>
  <main><section class="hero"><div class="hero-copy"><p class="eyebrow">Private / season control</p><h2>Keep the troupe in view.</h2><p>A calm operational snapshot for the server doing the work: progress, timing, diaries, and the few decisions that genuinely need you.</p></div><div class="heartbeat"><span>Last checked</span><strong id="checked-at">—</strong></div></section>
    <div id="global-alert" class="alert" role="status" aria-live="polite"><span aria-hidden="true">✦</span><span>Connecting to the service…</span></div>
    <section class="metric-grid" aria-label="At a glance"><article class="metric"><p class="eyebrow">Season state</p><strong id="metric-state">—</strong><span id="metric-state-detail" class="metric-detail">Loading current season</span></article><article class="metric"><p class="eyebrow">Run progress</p><strong id="metric-queue">—</strong><span id="metric-queue-detail" class="metric-detail">Loading queue</span></article><article class="metric"><p class="eyebrow">Next beat</p><strong id="metric-next">—</strong><span id="metric-next-detail" class="metric-detail">Loading schedule</span></article><article class="metric"><p class="eyebrow">Needs attention</p><strong id="metric-attention">—</strong><span id="metric-attention-detail" class="metric-detail">Loading alerts</span></article></section>
    <section class="content-grid"><article class="panel panel-wide"><div class="panel-header"><div><h2>Seasons</h2><p>Durable progress from the service database.</p></div><span class="faint">Read-only snapshot</span></div><div id="seasons" class="season-stack"><div class="empty-state"><strong>Loading seasons</strong><span>Waiting for the first status response.</span></div></div></article>
      <article class="panel panel-attention"><div class="panel-header"><div><h2>Operator attention</h2><p>Recovery choices are deliberately explicit.</p></div></div><div id="attention" class="attention-stack"><div class="empty-state"><strong>Loading alerts</strong><span>Checking the recovery queue.</span></div></div></article>
      <article class="panel panel-diary"><div class="panel-header"><div><h2>Diary desk</h2><p>Authenticated reading view; held private attempts remain reviewable.</p></div></div><div class="controls"><label class="control" for="diary-season">Season<select id="diary-season"><option value="">Loading…</option></select></label><label class="control" for="diary-day">Day<select id="diary-day"><option value="">All days</option><option value="1">Day 1</option><option value="2">Day 2</option><option value="3">Day 3</option><option value="4">Day 4</option><option value="5">Day 5</option><option value="6">Day 6</option><option value="7">Day 7</option></select></label></div><p id="diary-summary" class="diary-summary">Choose a season to inspect private diary records.</p><div id="diaries" class="diary-list"><div class="empty-state"><strong>Diary desk is ready</strong><span>Entries will appear here after selection.</span></div></div></article>
      <article class="panel panel-review"><div class="panel-header"><div><h2>End-of-day review</h2><p>One owner-only reading surface for the day’s shared script and every diary attempt.</p></div><button id="review-reload" class="button button-small button-quiet" type="button">Reload review</button></div><div class="controls"><label class="control" for="review-season">Season<select id="review-season"><option value="">Loading…</option></select></label><label class="control" for="review-day">Day<select id="review-day"><option value="1">Day 1</option><option value="2">Day 2</option><option value="3">Day 3</option><option value="4">Day 4</option><option value="5">Day 5</option><option value="6">Day 6</option><option value="7">Day 7</option></select></label></div><p id="review-summary" class="review-summary">Choose a day to assemble its durable review record.</p><div id="day-review" class="review-list"><div class="empty-state"><strong>End-of-day review is ready</strong><span>The shared script and private diary review material will load here.</span></div></div></article>
      <article class="panel panel-publication"><div class="panel-header"><div><h2>Publication gate</h2><p>Public release remains a separate, owner-approved projection.</p></div></div><div id="publication" class="publication-list"><div class="empty-state"><strong>Loading publication state</strong><span>No private material is published from this view automatically.</span></div></div><div class="note">This console never shows hidden plans, role sheets, raw prompts, or model identities. The signed-in owner may explicitly expand private diary review output; that material remains nonaccepted and nonpublishable until the separate publication gate.</div></article>
    </section></main>
  <footer>Private operator view · the worker continues if this window is closed</footer>
</div></body></html>"""


def v2_dashboard_html(*, page: str, environment: str, context: dict[str, object], csrf: str) -> str:
    """Render the shared read-only shell with escaped, stable season context."""
    seasons = list(context.get("seasons") or [])
    selected_id = str(context.get("selected_season_id") or "")
    selected = next(
        (item for item in seasons if str(item.get("season_id") or "") == selected_id),
        None,
    )
    season_title = str(selected.get("title") or "Untitled season") if selected else "No season"
    season_status = str(selected.get("status") or "NO SEASON") if selected else "NO SEASON"
    season_version = str(selected.get("version") or "—") if selected else "—"
    selected_label = selected_id or "None"
    navigation = list(context.get("navigation") or [])
    nav_by_destination = {
        str(item.get("destination")): item for item in navigation if isinstance(item, dict)
    }
    desktop_nav = _v2_navigation(navigation, current_page=page)
    bottom_nav = _v2_bottom_navigation(nav_by_destination, current_page=page)
    season_options = _v2_season_options(seasons, selected_id)
    page_label = page.capitalize()
    home_href = _v2_nav_href(nav_by_destination, "home")
    review_href = _v2_nav_href(nav_by_destination, "review")
    seasons_href = _v2_nav_href(nav_by_destination, "seasons")
    main_content = (
        _v2_home_content(season_title, review_href=review_href, seasons_href=seasons_href)
        if page == "home"
        else (
            _v2_prepare_content(season_title)
            if page == "prepare"
            else (
                _v2_live_content(season_title)
                if page == "live"
                else (
                    _v2_review_content(season_title)
                    if page == "review"
                    else (
                    _v2_diagnostics_content(season_title)
                    if page == "diagnostics"
                        else (
                            _v2_seasons_content(season_title)
                            if page == "seasons"
                            else _v2_placeholder(page, home_href=home_href)
                        )
                    )
                )
            )
        )
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="csrf-token" content="{html.escape(csrf, quote=True)}"><title>Simulation Query — {html.escape(page_label)}</title><link rel="stylesheet" href="/assets/dashboard.css"><script src="/assets/dashboard.js" defer></script></head>
<body data-dashboard-page="{html.escape(page, quote=True)}" data-selected-season="{html.escape(selected_id, quote=True)}"><div class="v2-shell">
  <header class="v2-mobile-context"><div class="v2-mobile-brand"><span class="v2-mark" aria-hidden="true">SQ</span><span><strong>Simulation Query</strong><small>PRIVATE OPERATOR</small></span></div><label class="v2-mobile-season"><span>Selected context</span><select data-season-picker aria-label="Selected season">{season_options}</select><small data-mobile-freshness>Loading snapshot</small></label></header>
  <aside class="v2-rail"><div class="v2-brand"><span class="v2-mark" aria-hidden="true">SQ</span><span><strong>Simulation Query</strong><small>PRIVATE OPERATOR</small></span></div><p class="v2-rail-label">Workspace</p>{desktop_nav}<div class="v2-context"><p class="v2-rail-label">Selected context</p><label class="v2-season-picker"><span class="sr-only">Selected season</span><select data-season-picker>{season_options}</select></label><strong data-context-season>{html.escape(selected_label)}</strong><span data-context-title>{html.escape(season_title)}</span><span class="v2-context-state" data-context-status>{html.escape(season_status)} · PRIVATE</span><p class="v2-rail-label v2-worker-label">Worker evidence</p><span class="v2-evidence" data-worker-evidence><i aria-hidden="true"></i>Loading lease state</span><span class="v2-queue" data-worker-queue>Queue not read yet</span><p class="v2-rail-label v2-freshness-label">Freshness</p><span data-rail-freshness>Loading snapshot</span><code data-snapshot-version>season v{html.escape(season_version)}</code></div><div class="v2-owner"><span class="v2-owner-mark" aria-hidden="true">A</span><span><strong>Aven</strong><small>Owner-only console · {html.escape(environment)}</small></span></div></aside>
  <main class="v2-main" id="main-content">{main_content}</main>
  {bottom_nav}
</div></body></html>"""


def _v2_navigation(navigation: list[object], *, current_page: str) -> str:
    items: list[str] = []
    for raw in navigation:
        if not isinstance(raw, dict):
            continue
        destination = str(raw.get("destination") or "")
        label = html.escape(str(raw.get("label") or destination.capitalize()))
        href = html.escape(str(raw.get("href") or "/v2/home"), quote=True)
        current = ' aria-current="page"' if destination == current_page else ""
        availability = "" if bool(raw.get("implemented")) else '<small>Later</small>'
        items.append(
            f'<a href="{href}" data-destination="{html.escape(destination, quote=True)}"{current}><i aria-hidden="true"></i><span>{label}</span>{availability}</a>'
        )
    return '<nav class="v2-nav" aria-label="Workspace">' + "".join(items) + "</nav>"


def _v2_bottom_navigation(navigation: dict[str, object], *, current_page: str) -> str:
    items: list[str] = []
    for destination, label in (
        ("home", "Home"),
        ("prepare", "Prepare"),
        ("live", "Live"),
        ("review", "Review"),
        ("seasons", "More"),
    ):
        raw = navigation.get(destination)
        href = str(raw.get("href") or f"/v2/{destination}") if isinstance(raw, dict) else f"/v2/{destination}"
        current = ' aria-current="page"' if destination == current_page else ""
        items.append(
            f'<a href="{html.escape(href, quote=True)}" data-destination="{destination}"{current}><i aria-hidden="true"></i><span>{label}</span></a>'
        )
    return '<nav class="v2-bottom" aria-label="Narrow workspace">' + "".join(items) + "</nav>"


def _v2_nav_href(navigation: dict[str, object], destination: str) -> str:
    raw = navigation.get(destination)
    if isinstance(raw, dict):
        return str(raw.get("href") or f"/v2/{destination}")
    return f"/v2/{destination}"


def _v2_season_options(seasons: list[object], selected_id: str) -> str:
    if not seasons:
        return '<option value="" selected>No season</option>'
    options: list[str] = []
    for raw in seasons:
        if not isinstance(raw, dict):
            continue
        season_id = str(raw.get("season_id") or "")
        title = str(raw.get("title") or "Untitled season")
        selected = " selected" if season_id == selected_id else ""
        options.append(
            f'<option value="{html.escape(season_id, quote=True)}"{selected}>{html.escape(season_id)} · {html.escape(title)}</option>'
        )
    return "".join(options)


def _v2_home_content(season_title: str, *, review_href: str, seasons_href: str) -> str:
    title = html.escape(season_title)
    review = html.escape(review_href, quote=True)
    seasons = html.escape(seasons_href, quote=True)
    return f"""<section class="v2-hero" aria-labelledby="home-title"><div><p class="v2-eyebrow" data-home-eyebrow>Home / {title}</p><h1 id="home-title">Keep the troupe in view.</h1><p data-home-summary>Loading durable season evidence…</p></div><span class="v2-snapshot-badge" data-freshness-badge>Loading snapshot</span></section>
<section class="v2-state-banner" data-global-state data-tone="loading" role="status" aria-live="polite"><strong>Reading durable state</strong><span>The current snapshot will stay visible if a later refresh cannot connect.</span></section>
<section class="v2-metrics" aria-label="At a glance"><article><p class="v2-eyebrow">Today</p><strong data-today-value>—</strong><span data-today-detail>Reading scheduled runs</span></article><article><p class="v2-eyebrow">Diaries</p><strong data-diary-value>—</strong><span data-diary-detail>Reading durable records</span></article><article class="v2-metric-secondary"><p class="v2-eyebrow">Next slot</p><strong data-next-value>—</strong><span data-next-detail>Reading schedule</span></article><article class="v2-metric-secondary" data-attention-metric><p class="v2-eyebrow">Operator attention</p><strong data-attention-value>—</strong><span data-attention-detail>Reading durable items</span></article></section>
<section class="v2-home-grid"><article class="v2-panel v2-beat" data-beat-card><header><p class="v2-eyebrow">Last accepted beat</p><span data-beat-canon>Durable acceptance</span></header><h2 data-beat-title>No accepted beat stored</h2><blockquote data-beat-excerpt>The first accepted story beat will appear here without exposing its private path.</blockquote><div class="v2-beat-receipt"><code data-beat-receipt>No receipt available</code><small data-beat-evidence>Accepted ordering is reported only to the level supported by durable evidence.</small></div><a data-beat-review href="{review}">Open review context</a></article>
<article class="v2-panel v2-next"><p class="v2-eyebrow">Next up</p><h2 data-next-title>No unresolved slot stored</h2><p data-next-copy>The schedule read will appear here.</p><div class="v2-cast"><p class="v2-eyebrow">Cast</p><ul data-cast-list><li>Loading cast</li></ul></div><a data-schedule-link href="{seasons}">Open schedule context</a></article>
<article class="v2-panel v2-review"><p class="v2-eyebrow" data-review-eyebrow>Day review</p><h2 data-review-title>Waiting for durable day state</h2><p data-review-copy>Read-only review context will remain stable while Home refreshes operational truth.</p><a data-review-link href="{review}">Open Day Review</a><small>DASH-01 preserves context; the causal reading surface follows in DASH-02.</small></article>
<article class="v2-panel v2-notes"><p class="v2-eyebrow">Private system notes</p><h2>Evidence, not inference</h2><dl><div><dt>Integrity</dt><dd data-health-integrity>Not checked</dd></div><div><dt>Worker</dt><dd data-health-worker>Lease state not read</dd></div><div><dt>Storage</dt><dd data-health-storage>Not checked</dd></div><div><dt>Outbox</dt><dd data-health-outbox>Not checked</dd></div><div><dt>Models</dt><dd data-health-models>Not probed</dd></div></dl><p>Home never exposes hidden plans, raw prompts, role sheets, model identities, raw wellness text, or private artifact paths.</p><div class="v2-recent"><p class="v2-eyebrow">Recent seasons</p><ul data-recent-seasons><li>Loading recent context</li></ul></div></article></section>"""


def _v2_review_content(season_title: str) -> str:
    title = html.escape(season_title)
    return f"""<section class="v2-review-hero" aria-labelledby="review-title"><div><p class="v2-eyebrow">Review / {title}</p><h1 id="review-title">Read what actually happened.</h1><p>The accepted story stays in causal order. Diary text opens only when you deliberately ask for it.</p></div><div class="v2-review-actions"><button type="button" data-review-reload>Reload review</button><small data-review-position>Reading position not saved yet</small></div></section>
<section class="v2-state-banner" data-global-state data-tone="loading" role="status" aria-live="polite"><strong>Loading durable review</strong><span>The reading pane will not be replaced by operational polling.</span></section>
<nav class="v2-review-tabs" role="tablist" aria-label="Day Review views"><button type="button" role="tab" data-review-tab="script" aria-selected="true">Script</button><button type="button" role="tab" data-review-tab="diaries" aria-selected="false">Diary desk</button><button type="button" role="tab" data-review-tab="cast" aria-selected="false">Cast &amp; continuity</button><button type="button" role="tab" data-review-tab="summary" aria-selected="false">Day summary</button></nav>
<section class="v2-new-material" data-review-newer hidden aria-live="polite"><div><strong>New accepted material is available.</strong><span>Your open pane and reading position have not moved.</span></div><div><button type="button" data-review-load-new>Load new material</button><button type="button" data-review-keep>Keep reading here</button></div></section>
<section data-review-reader class="v2-review-reader" aria-busy="true"><div class="v2-review-loading"><strong>Assembling accepted evidence</strong><span>Reading runs, diary statuses, and continuity records.</span></div></section>"""


def _v2_prepare_content(season_title: str) -> str:
    title = html.escape(season_title)
    return f"""<section class="v2-review-hero v2-prepare-hero" aria-labelledby="prepare-title"><div><p class="v2-eyebrow">Prepare / {title}</p><h1 id="prepare-title">Make every pre-season decision visible.</h1><p>This isolated rehearsal records versions and approvals. It never chooses a model, calls one, writes the production schedule, or arms the season.</p></div><span class="v2-snapshot-badge">Sandbox rehearsal</span></section>
<section class="v2-state-banner" data-global-state data-tone="loading" role="status" aria-live="polite"><strong>Loading preparation evidence</strong><span>The approved version stays visible beside any draft.</span></section>
<section class="v2-prepare-boundary" aria-label="Rehearsal boundary"><strong>No production command path</strong><span data-prepare-boundary>0 model calls · production state unchanged · Green remains a separate review receipt</span></section>
<section class="v2-prepare-reader" data-prepare-reader aria-busy="true"><div class="v2-review-loading"><strong>Assembling the eight-step workspace</strong><span>Reading versions, approvals, dependencies, and invalidation history.</span></div></section>"""


def _v2_live_content(season_title: str) -> str:
    title = html.escape(season_title)
    return f"""<section class="v2-review-hero v2-live-hero" aria-labelledby="live-title"><div><p class="v2-eyebrow">Live / {title}</p><h1 id="live-title">Performance supervision.</h1><p data-live-summary>Reading worker, queue, run, and accepted story evidence…</p></div><span class="v2-snapshot-badge" data-live-attention>Loading</span></section>
<section class="v2-state-banner" data-global-state data-tone="loading" role="status" aria-live="polite"><strong>Loading durable Live truth</strong><span>Closing this dashboard does not change worker progress.</span></section>
<section class="v2-live-reader" data-live-reader aria-busy="true"><div class="v2-review-loading"><strong>Assembling supervision evidence</strong><span>No operator command is available until its impact review is open.</span></div></section>
<dialog class="v2-impact-dialog" data-live-impact><form method="dialog"><button value="cancel" aria-label="Close impact review">Close</button></form><div data-live-impact-body></div></dialog>"""


def _v2_diagnostics_content(season_title: str) -> str:
    title = html.escape(season_title)
    return f"""<section class="v2-review-hero v2-diagnostics-hero" aria-labelledby="diagnostics-title"><div><p class="v2-eyebrow">Diagnostics / {title}</p><h1 id="diagnostics-title">Explain one call without changing anything.</h1><p>Inspecting evidence cannot rerun a model, accept text, resolve recovery, or alter canon.</p></div><span class="v2-snapshot-badge">Read-only</span></section>
<section class="v2-state-banner" data-global-state data-tone="loading" role="status" aria-live="polite"><strong>Loading call evidence</strong><span>Raw wellness text is excluded. Private raw output remains closed until deliberately requested.</span></section>
<form class="v2-diagnostics-filters" data-diagnostics-filters><label>Run<input name="run_id" placeholder="All runs"></label><label>Character<input name="character_id" placeholder="All characters"></label><label>Purpose<input name="purpose" placeholder="All purposes"></label><label>Status<input name="status" placeholder="All statuses"></label><label>Attempt<input name="attempt" inputmode="numeric" placeholder="All"></label><label>Error<input name="error" placeholder="All errors"></label><button type="submit">Apply filters</button><button type="button" data-diagnostics-clear>Clear</button></form>
<section class="v2-diagnostics-reader" data-diagnostics-reader aria-busy="true"><div class="v2-review-loading"><strong>Assembling call evidence</strong><span>Reading immutable transport and downstream-stage records.</span></div></section>"""


def _v2_seasons_content(season_title: str) -> str:
    title = html.escape(season_title)
    return f"""<section class="v2-review-hero v2-seasons-hero" aria-labelledby="seasons-title"><div><p class="v2-eyebrow">Seasons / {title}</p><h1 id="seasons-title">Preserve before release.</h1><p>Private close records what remains, stops later scheduled work, and creates a handoff. Publication is a separate, allowlisted review after that private state is complete.</p></div><span class="v2-snapshot-badge">Sandbox rehearsal</span></section>
<section class="v2-state-banner" data-global-state data-tone="loading" role="status" aria-live="polite"><strong>Loading close review</strong><span>Nothing closes or publishes because this page was opened or refreshed.</span></section>
<section class="v2-seasons-reader" data-seasons-reader aria-busy="true"><div class="v2-review-loading"><strong>Assembling closure evidence</strong><span>Reading the season, archive reachability, and unresolved work.</span></div></section>
<dialog class="v2-impact-dialog" data-seasons-impact><form method="dialog"><button value="cancel" aria-label="Close Seasons impact review">Close</button></form><div data-seasons-impact-body></div></dialog>"""


def _v2_placeholder(page: str, *, home_href: str) -> str:
    label = html.escape(page.capitalize())
    home_href = html.escape(home_href, quote=True)
    return f"""<section class="v2-placeholder"><p class="v2-eyebrow">{label} / stable context</p><h1>{label} is not implemented in DASH-01.</h1><p>This read-only destination proves that the selected season and environment survive navigation. Its workflow arrives in a separately reviewed ticket.</p><section class="v2-state-banner" data-global-state data-tone="loading" role="status" aria-live="polite"><strong>Loading shared context</strong><span>No season command or private disclosure is available here.</span></section><a class="v2-dark-link" data-home-return href="{home_href}">Return to Home</a></section>"""


__all__ = ["legacy_dashboard_html", "login_html", "static_asset", "v2_dashboard_html"]
