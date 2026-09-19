CREATE TABLE IF NOT EXISTS seasons (
    season_id TEXT PRIMARY KEY,
    season_number INTEGER NOT NULL UNIQUE,
    title TEXT,
    status TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS one_nonterminal_season
ON seasons ((1))
WHERE status IN (
    'DRAFT', 'AWAITING_GREEN', 'ARMED', 'RUNNING', 'PAUSED',
    'RECOVERY_REQUIRED', 'CLOSING'
);

CREATE TABLE IF NOT EXISTS season_opening_versions (
    season_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    set_text TEXT NOT NULL,
    setting TEXT NOT NULL,
    cast_json TEXT NOT NULL,
    world_rules_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (season_id, version),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS schedule_slots (
    slot_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    day_number INTEGER NOT NULL,
    slot_number INTEGER NOT NULL,
    run_number INTEGER NOT NULL,
    scheduled_local TEXT NOT NULL,
    scheduled_utc TEXT NOT NULL,
    utc_offset TEXT NOT NULL,
    UNIQUE (season_id, day_number, slot_number),
    UNIQUE (season_id, run_number),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS days (
    season_id TEXT NOT NULL,
    day_number INTEGER NOT NULL,
    original_date TEXT NOT NULL,
    cutoff_at TEXT,
    closed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (season_id, day_number),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS cast_members (
    season_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    role_sheet_version INTEGER NOT NULL DEFAULT 0,
    memory_version INTEGER NOT NULL DEFAULT 0,
    distress_signal_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (season_id, character_id),
    UNIQUE (season_id, name),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS role_sheet_versions (
    season_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (season_id, character_id, version),
    FOREIGN KEY (season_id, character_id)
        REFERENCES cast_members(season_id, character_id)
);

CREATE TABLE IF NOT EXISTS actor_memory_versions (
    season_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (season_id, character_id, version),
    FOREIGN KEY (season_id, character_id)
        REFERENCES cast_members(season_id, character_id)
);

CREATE TABLE IF NOT EXISTS canon_entries (
    canon_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    claim TEXT NOT NULL,
    status TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (season_id, version),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    status TEXT NOT NULL,
    turn_count INTEGER NOT NULL DEFAULT 0,
    completion_reason TEXT,
    actual_started_at TEXT,
    actual_completed_at TEXT,
    delay TEXT,
    version INTEGER NOT NULL DEFAULT 0,
    UNIQUE (season_id, slot_id),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (slot_id) REFERENCES schedule_slots(slot_id)
);

CREATE TABLE IF NOT EXISTS turns (
    turn_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    character_id TEXT NOT NULL,
    disposition TEXT NOT NULL,
    content_path TEXT,
    UNIQUE (run_id, round_number, character_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS model_calls (
    call_id TEXT PRIMARY KEY,
    run_id TEXT,
    purpose TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    status TEXT NOT NULL,
    backend TEXT,
    model TEXT,
    started_at TEXT,
    ended_at TEXT,
    latency_ms INTEGER,
    prompt_path TEXT,
    output_path TEXT,
    prompt_sha256 TEXT,
    output_sha256 TEXT,
    finish_reason TEXT,
    cancelled INTEGER NOT NULL DEFAULT 0,
    error_type TEXT,
    usage_json TEXT,
    UNIQUE (run_id, purpose, attempt),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS model_call_identity
ON model_calls (COALESCE(run_id, ''), purpose, attempt);

CREATE TABLE IF NOT EXISTS diaries (
    diary_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    day_number INTEGER NOT NULL,
    chosen_slot_number INTEGER,
    status TEXT NOT NULL,
    word_count INTEGER,
    late INTEGER NOT NULL DEFAULT 0,
    content_path TEXT,
    UNIQUE (season_id, character_id, day_number),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS wellness_events (
    event_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    context TEXT NOT NULL,
    signal_number INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    intervention TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS consent_decisions (
    consent_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    UNIQUE (season_id, character_id, decided_at)
);

CREATE TABLE IF NOT EXISTS recovery_requests (
    recovery_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL,
    decision TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    season_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT
);

CREATE TABLE IF NOT EXISTS publications (
    publication_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    eligible_diary_ids_json TEXT NOT NULL,
    output_path TEXT,
    manifest_sha256 TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (season_id, version),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS publication_checks (
    publication_id TEXT PRIMARY KEY,
    wellness_confirmed INTEGER NOT NULL DEFAULT 0,
    privacy_reviewed INTEGER NOT NULL DEFAULT 0,
    consent_confirmed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (publication_id) REFERENCES publications(publication_id)
);

CREATE TABLE IF NOT EXISTS publication_diary_reviews (
    publication_id TEXT NOT NULL,
    diary_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (publication_id, diary_id),
    FOREIGN KEY (publication_id) REFERENCES publications(publication_id),
    FOREIGN KEY (diary_id) REFERENCES diaries(diary_id)
);

CREATE TABLE IF NOT EXISTS domain_events (
    event_id TEXT PRIMARY KEY,
    natural_key TEXT NOT NULL UNIQUE,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS command_requests (
    request_id TEXT PRIMARY KEY,
    command_type TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_items (
    work_id TEXT PRIMARY KEY,
    natural_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    available_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_until TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS artifact_outbox (
    outbox_id TEXT PRIMARY KEY,
    artifact_key TEXT NOT NULL UNIQUE,
    visibility TEXT NOT NULL DEFAULT 'private',
    relative_path TEXT NOT NULL,
    content BLOB NOT NULL,
    immutable INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'PENDING',
    projected_path TEXT,
    sha256 TEXT,
    byte_length INTEGER,
    created_at TEXT NOT NULL,
    projected_at TEXT
);
