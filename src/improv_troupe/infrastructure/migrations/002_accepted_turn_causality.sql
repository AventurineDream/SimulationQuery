ALTER TABLE turns ADD COLUMN accepted_sequence INTEGER;
ALTER TABLE turns ADD COLUMN caused_by_turn_id TEXT;
ALTER TABLE turns ADD COLUMN accepted_at TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS accepted_turn_sequence_per_run
ON turns (run_id, accepted_sequence)
WHERE accepted_sequence IS NOT NULL;

CREATE INDEX IF NOT EXISTS accepted_turn_cause_lookup
ON turns (run_id, caused_by_turn_id)
WHERE caused_by_turn_id IS NOT NULL;
