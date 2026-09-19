ALTER TABLE recovery_requests ADD COLUMN version INTEGER NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS recovery_by_season_status
ON recovery_requests(season_id, status, created_at);
