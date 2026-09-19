ALTER TABLE model_calls ADD COLUMN character_id TEXT;
ALTER TABLE model_calls ADD COLUMN response_format_mode TEXT;
ALTER TABLE model_calls ADD COLUMN prompt_version_id TEXT;
ALTER TABLE model_calls ADD COLUMN schema_version_id TEXT;
ALTER TABLE model_calls ADD COLUMN context_version_id TEXT;
ALTER TABLE model_calls ADD COLUMN role_sheet_version_id TEXT;
ALTER TABLE model_calls ADD COLUMN character_card_version_id TEXT;
ALTER TABLE model_calls ADD COLUMN parse_status TEXT;
ALTER TABLE model_calls ADD COLUMN validation_status TEXT;
ALTER TABLE model_calls ADD COLUMN acceptance_status TEXT;
ALTER TABLE model_calls ADD COLUMN render_status TEXT;
ALTER TABLE model_calls ADD COLUMN parsed_path TEXT;
ALTER TABLE model_calls ADD COLUMN validated_path TEXT;
ALTER TABLE model_calls ADD COLUMN accepted_path TEXT;
ALTER TABLE model_calls ADD COLUMN rendered_path TEXT;
ALTER TABLE model_calls ADD COLUMN validator_code TEXT;
ALTER TABLE model_calls ADD COLUMN validator_detail TEXT;
ALTER TABLE model_calls ADD COLUMN correction_of_call_id TEXT;
ALTER TABLE model_calls ADD COLUMN review_turn_id TEXT;

CREATE INDEX IF NOT EXISTS model_calls_diagnostics_filter
ON model_calls (run_id, character_id, purpose, status, attempt, error_type);
