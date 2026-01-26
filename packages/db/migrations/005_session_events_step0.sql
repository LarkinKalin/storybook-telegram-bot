-- Schema update: add step0 to session_events

ALTER TABLE session_events
  ADD COLUMN IF NOT EXISTS step0 int NULL;

UPDATE session_events
SET step0 = step
WHERE step0 IS NULL;
