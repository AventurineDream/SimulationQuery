CREATE TABLE IF NOT EXISTS closure_snapshots (
    snapshot_hash TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    season_version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    private_archive_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id)
);

CREATE TABLE IF NOT EXISTS closure_receipts (
    receipt_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    season_id TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL,
    season_version_before INTEGER NOT NULL,
    season_version_after INTEGER NOT NULL,
    private_archive_sha256_before TEXT NOT NULL,
    private_archive_sha256_after TEXT NOT NULL,
    handoff_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (snapshot_hash) REFERENCES closure_snapshots(snapshot_hash)
);

CREATE TABLE IF NOT EXISTS closure_handoffs (
    handoff_id TEXT PRIMARY KEY,
    season_id TEXT NOT NULL,
    receipt_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    FOREIGN KEY (season_id) REFERENCES seasons(season_id),
    FOREIGN KEY (receipt_id) REFERENCES closure_receipts(receipt_id)
);

CREATE TABLE IF NOT EXISTS seasons_action_receipts (
    request_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
