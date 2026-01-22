# Database schema (v0.1)

**Owner:** TG Bot / Skazka team

**Version:** v0.1

**Apply:** use your standard compose/psql/runner workflow (no inline commands here by policy).

**Spec:** “DB Schema v0.1 — Field Spec (FINAL)”.

## Tables overview

- `users`: Telegram users, subscription plan metadata, and audit timestamps.
- `sessions`: Story sessions with player context, progress, and lifecycle markers.
- `session_events`: Per-step events and LLM payloads tied to a session.
- `payments`: Payment records and subscription period tagging.
- `confirm_requests`: Confirmation workflows (e.g., clicks/decisions) with TTL.
- `usage_windows`: Rolling 12h usage window counters and throttling hints.
- `ui_events`: UI delivery/ack tracking with retry state.

## Canon notes

- `sessions.sid8` must be generated cryptographically random in application code.
- Session lookup is always by `(tg_id, sid8)`, never by `sid8` alone.
- `sessions.expires_at` is TTL/archive only, not business status.
- **Invariant:** at most one `ACTIVE` session per `user_id` (enforced via partial unique index).
- `confirm_requests` lookup is strictly by `(tg_id, rid8)`.
- `confirm_requests` consistency rules (documented invariant):
  - `PENDING` ⇒ `result` is `NULL`, `used_at` is `NULL`.
  - `USED` ⇒ `used_at` is not `NULL`, `result` in `(YES|NO|FAIL)`.
  - `EXPIRED` ⇒ `used_at` is `NULL`, `result` is `NULL`.
- Payments: if `kind=SUB_MONTH` and `status=CONFIRMED` ⇒ `period_yyyymm` is required.
- `usage_windows` uses a rolling 12h window; “one active window” is enforced via transactional upsert in code.
- `ui_events` consistency: `state=PENDING` ⇒ `pending_since` is not `NULL`.
- `ui_events.content_hash` format canon: `sha256:<hex>`.
