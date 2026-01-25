-- Schema update: enforce ui_events idempotency on (session_id, step, kind)

WITH ranked AS (
  SELECT
    id,
    ROW_NUMBER() OVER (
      PARTITION BY session_id, step, kind
      ORDER BY updated_at DESC, id DESC
    ) AS rn
  FROM ui_events
)
DELETE FROM ui_events
USING ranked
WHERE ui_events.id = ranked.id
  AND ranked.rn > 1;

ALTER TABLE ui_events
  DROP CONSTRAINT IF EXISTS ui_events_session_step_kind_hash_unique;

ALTER TABLE ui_events
  DROP CONSTRAINT IF EXISTS ui_events_session_step_kind_unique;

ALTER TABLE ui_events
  ADD CONSTRAINT ui_events_session_step_kind_unique
  UNIQUE (session_id, step, kind);
