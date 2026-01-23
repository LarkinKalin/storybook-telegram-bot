import copy
import json

from packages.engine.src.engine_v0_1 import (
    apply_turn,
    init_state_v01,
    milestones_for_N,
    pick_final,
)


def make_choice(choice_id, deltas, milestone_vote=None):
    return {
        "choice_id": choice_id,
        "deltas": deltas,
        "milestone_vote": milestone_vote or {"vote": "none", "reason": "none"},
    }


def make_content_step(step_type="NORMAL", choices=None):
    return {
        "step_type": step_type,
        "choices": choices or [make_choice("A", [])],
    }


def test_milestones_for_N():
    assert milestones_for_N(8) == {"m2": 2, "m6": 5, "m7": 6}
    assert milestones_for_N(10) == {"m2": 2, "m6": 6, "m7": 7}
    assert milestones_for_N(12) == {"m2": 2, "m6": 7, "m7": 9}


def test_milestones_collision():
    result = milestones_for_N(4)
    assert result["m6"] == 2
    assert result["m7"] == 3


def test_apply_turn_step_increment():
    state = init_state_v01(8)
    content = make_content_step(
        choices=[make_choice("A", [{"trait": "t1", "delta": 1}])]
    )
    new_state, log = apply_turn(state, {"kind": "choice", "choice_id": "A"}, content)
    assert new_state["step0"] == 1
    assert log["final_id"] is None


def test_apply_turn_early_final_no_increment():
    state = init_state_v01(8)
    state["noise_streak"] = 4
    content = make_content_step()
    new_state, log = apply_turn(
        state, {"kind": "free_text", "text": "..."}, content
    )
    assert new_state["step0"] == state["step0"]
    assert log["final_id"] == "F5"
    assert log["final_meta"]["f5_reason"] == "noise_abort"


def test_noise_gating_after_three():
    state = init_state_v01(8)
    state["noise_streak"] = 2
    content = make_content_step()
    new_state, log = apply_turn(
        state, {"kind": "free_text", "text": "..."}, content
    )
    assert new_state["noise_streak"] == 3
    assert log["free_text_allowed_after"] is False


def test_noise_five_triggers_final():
    state = init_state_v01(8)
    state["noise_streak"] = 4
    content = make_content_step()
    new_state, log = apply_turn(
        state, {"kind": "free_text", "text": "угу"}, content
    )
    assert log["final_id"] == "F5"
    assert log["final_meta"]["f5_reason"] == "noise_abort"
    assert new_state["step0"] == state["step0"]


def test_missing_mapping_sets_neutral():
    state = init_state_v01(8)
    content = make_content_step(choices=[make_choice("A", [])])
    _, log = apply_turn(state, {"kind": "choice", "choice_id": "B"}, content)
    assert log["neutral_reason"] == "missing_mapping"
    assert log["applied_deltas"] == []
    assert log["content_missing_mapping"] is True


def test_milestone_neutral_vote_missing():
    state = init_state_v01(8)
    state["step0"] = 2
    content = make_content_step(choices=[make_choice("A", [])])
    _, log = apply_turn(state, {"kind": "choice", "choice_id": "B"}, content)
    assert log["milestone_id"] == "m2"
    assert log["milestone_vote_missing"] == ["m2"]
    assert log["milestone_vote_current"] == {"vote": "none", "reason": "none"}


def test_content_delta_clamped():
    state = init_state_v01(8)
    content = make_content_step(
        choices=[
            make_choice(
                "A",
                [
                    {"trait": "t1", "delta": 2},
                    {"trait": "t2", "delta": 2},
                ],
            )
        ]
    )
    _, log = apply_turn(state, {"kind": "choice", "choice_id": "A"}, content)
    assert log["content_delta_clamped"] is True
    assert sum(abs(d["delta"]) for d in log["applied_deltas"]) <= 2


def test_final_rule1_chaos_dominant():
    state = init_state_v01(8)
    state["traits"].update({"t1": 8, "t2": 8, "t3": 8, "t4": 8, "t5": 8, "t6": 9})
    final_id, meta = pick_final(state)
    assert final_id == "F5"
    assert meta["f5_reason"] == "chaos_dominant"
    assert meta["rule_hit"] == 1


def test_final_rule2_unique_leader():
    state = init_state_v01(8)
    state["traits"].update({"t1": 10, "t2": 7, "t3": 6, "t4": 6, "t5": 6})
    final_id, meta = pick_final(state)
    assert final_id == "F1"
    assert meta["rule_hit"] == 2


def test_final_rule3_tiebreak_winner():
    state = init_state_v01(8)
    state["traits"].update({"t1": 9, "t2": 9, "t3": 5, "t4": 5, "t5": 5})
    state["milestone_votes"]["m2"] = {"vote": "t2", "reason": "content"}
    state["milestone_votes"]["m6"] = {"vote": "t2", "reason": "content"}
    final_id, meta = pick_final(state)
    assert final_id == "F2"
    assert meta["tie_break_used"] is True
    assert meta["tie_break_winner"] == "t2"


def test_final_rule3_tiebreak_none():
    state = init_state_v01(8)
    state["traits"].update({"t1": 9, "t2": 9, "t3": 5, "t4": 5, "t5": 5})
    final_id, meta = pick_final(state)
    assert final_id == "F4"
    assert meta["rule_hit"] == 3


def test_final_rule4_default():
    state = init_state_v01(8)
    state["traits"].update({"t1": 8, "t2": 8, "t3": 8, "t4": 8, "t5": 8})
    final_id, meta = pick_final(state)
    assert final_id == "F4"
    assert meta["rule_hit"] == 4


def test_determinism_and_json_serializable():
    state = init_state_v01(8)
    content = make_content_step(
        choices=[make_choice("A", [{"trait": "t1", "delta": 1}])]
    )
    turn = {"kind": "choice", "choice_id": "A"}
    first_state, first_log = apply_turn(copy.deepcopy(state), turn, content)
    second_state, second_log = apply_turn(copy.deepcopy(state), turn, content)
    assert first_state == second_state
    assert first_log == second_log
    json.dumps(first_state)
    json.dumps(first_log)


def test_free_text_low_confidence_neutral():
    state = init_state_v01(8)
    content = make_content_step()
    turn = {
        "kind": "free_text",
        "text": "понятный текст",
        "classifier_result": {
            "confidence": 0.4,
            "safety": "clear",
            "deltas": [{"trait": "t1", "delta": 1}],
        },
    }
    new_state, log = apply_turn(state, turn, content)
    assert log["neutral_reason"] == "low_confidence"
    assert log["applied_deltas"] == []
    assert new_state["traits"] == state["traits"]


def test_free_text_safety_unclear_neutral():
    state = init_state_v01(8)
    content = make_content_step()
    turn = {
        "kind": "free_text",
        "text": "понятный текст",
        "classifier_result": {
            "confidence": 0.9,
            "safety": "unclear",
            "deltas": [{"trait": "t1", "delta": 1}],
        },
    }
    new_state, log = apply_turn(state, turn, content)
    assert log["neutral_reason"] == "safety_unclear"
    assert log["applied_deltas"] == []
    assert new_state["traits"] == state["traits"]


def test_free_text_high_confidence_applies_deltas_and_clamps():
    state = init_state_v01(8)
    content = make_content_step()
    turn = {
        "kind": "free_text",
        "text": "понятный текст",
        "classifier_result": {
            "confidence": 0.9,
            "safety": "clear",
            "deltas": [
                {"trait": "t1", "delta": 2},
                {"trait": "t2", "delta": 2},
            ],
        },
    }
    new_state, log = apply_turn(state, turn, content)
    assert log["neutral_reason"] is None
    assert log["classifier_delta_clamped"] is True
    assert sum(abs(d["delta"]) for d in log["applied_deltas"]) <= 2
    assert new_state["traits"]["t1"] + new_state["traits"]["t2"] <= 12
