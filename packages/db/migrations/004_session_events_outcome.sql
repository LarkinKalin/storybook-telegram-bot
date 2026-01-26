-- Schema update: add outcome/result/meta columns to session_events

ALTER TABLE session_events
  ADD COLUMN IF NOT EXISTS outcome text NULL;

ALTER TABLE session_events
  ADD COLUMN IF NOT EXISTS step0 integer NULL;

ALTER TABLE session_events
  ADD COLUMN IF NOT EXISTS step_result_json jsonb NULL;

ALTER TABLE session_events
  ADD COLUMN IF NOT EXISTS meta_json jsonb NULL;
