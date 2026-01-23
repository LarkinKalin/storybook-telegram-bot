# Engine v0.1 (pure library)

## Run tests

```bash
python -m venv .venv
. .venv/bin/activate
python -m pytest -q packages/engine/tests
```

## Minimal usage example

```python
from packages.engine.src.engine_v0_1 import apply_turn, init_state_v01

state = init_state_v01(8)
content_step = {
    "step_type": "NORMAL",
    "choices": [
        {
            "choice_id": "A",
            "deltas": [{"trait": "t1", "delta": 1}],
            "milestone_vote": {"vote": "none", "reason": "none"},
        }
    ],
}
turn = {"kind": "choice", "choice_id": "A"}
state, step_log = apply_turn(state, turn, content_step)
print(step_log)
```

Example `step_log` (JSON-ready):

```json
{
  "v": "0.1",
  "n": 8,
  "step0": 0,
  "step_type": "NORMAL",
  "turn_kind": "choice",
  "choice_id": "A",
  "user_input_present": true,
  "noise_input": false,
  "noise_streak_before": 0,
  "noise_streak_after": 0,
  "free_text_allowed_after": true,
  "neutral_reason": null,
  "applied_deltas": [
    {"trait": "t1", "delta": 1}
  ],
  "traits_before": {"t1": 5, "t2": 5, "t3": 5, "t4": 5, "t5": 5, "t6": 5},
  "traits_after": {"t1": 6, "t2": 5, "t3": 5, "t4": 5, "t5": 5, "t6": 5},
  "milestone_id": null,
  "milestone_vote_current": null,
  "milestone_vote_missing": [],
  "final_id": null,
  "final_meta": null,
  "content_delta_clamped": false,
  "classifier_delta_clamped": false,
  "content_missing_mapping": false
}
```

Example `final_meta` (from `pick_final`):

```json
{
  "rule_hit": 4,
  "max_core": 8,
  "min_core": 5,
  "gap_core": 0,
  "leader_core": "tie",
  "tie_break_used": false,
  "tie_break_votes": {"t1": 0, "t2": 0, "t3": 0, "t4": 0, "t5": 0},
  "tie_break_winner": null,
  "f5_reason": null,
  "f4_tone": "success"
}
```
