CREATE TABLE IF NOT EXISTS preparation_workspaces (
    season_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    idea TEXT NOT NULL,
    idea_version INTEGER NOT NULL,
    opening_version INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS character_card_versions (
    season_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    name TEXT NOT NULL,
    pronouns TEXT NOT NULL,
    public_brief TEXT NOT NULL,
    occupation_skills_json TEXT NOT NULL,
    voice_anchors_json TEXT NOT NULL,
    habits_json TEXT NOT NULL,
    derived_opening_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    PRIMARY KEY (season_id, character_id, version),
    FOREIGN KEY (season_id, character_id)
        REFERENCES cast_members(season_id, character_id)
);

CREATE TABLE IF NOT EXISTS model_assignment_versions (
    season_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    manifest_name TEXT NOT NULL,
    assignments_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    PRIMARY KEY (season_id, version),
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS private_preparation_versions (
    season_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    artifact_kind TEXT NOT NULL,
    version INTEGER NOT NULL,
    source_character_card_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    PRIMARY KEY (season_id, character_id, artifact_kind, version),
    FOREIGN KEY (season_id, character_id)
        REFERENCES cast_members(season_id, character_id),
    CHECK (artifact_kind IN ('role_sheet', 'orientation'))
);

CREATE TABLE IF NOT EXISTS preparation_receipts (
    receipt_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    step TEXT NOT NULL,
    workspace_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS preparation_invalidation_events (
    event_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    source_step TEXT NOT NULL,
    source_version INTEGER NOT NULL,
    invalidated_steps_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS preparation_actions (
    request_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    action TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);
