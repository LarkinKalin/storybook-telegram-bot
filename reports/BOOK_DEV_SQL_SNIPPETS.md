# Book v1 dev SQL snippets

```sql
-- Latest jobs
SELECT id, session_id, kind, status, result_pdf_asset_id, script_json_asset_id, updated_at
FROM book_jobs
ORDER BY id DESC
LIMIT 20;

-- Latest PDF/JSON assets
SELECT id, kind, storage_backend, storage_key, mime, bytes, created_at
FROM assets
WHERE kind IN ('pdf', 'json')
ORDER BY id DESC
LIMIT 20;

-- Session protocol source (book input)
SELECT session_id, step, outcome, choice_id, step_result_json
FROM session_events
WHERE session_id = :session_id
ORDER BY step ASC;
```
