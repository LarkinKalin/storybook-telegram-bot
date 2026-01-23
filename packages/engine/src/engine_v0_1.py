from __future__ import annotations

import copy
import re
from typing import Dict, List, Optional, Tuple

from .models import (
    Choice,
    ContentStep,
    Delta,
    EngineStateV01,
    FinalMetaV01,
    MilestoneVote,
    StepLogV01,
    Turn,
)

CORE_TRAITS = ["t1", "t2", "t3", "t4", "t5"]
ALL_TRAITS = ["t1", "t2", "t3", "t4", "t5", "t6"]

STEP_LIMITS = {"NORMAL": 2, "SEMI": 3, "HEAVY": 4}

NOISE_WORDS = {
    "не знаю",
    "незнаю",
    "хз",
    "лол",
    "ок",
    "угу",
    "ээ",
    "а",
    "мм",
    "...",
    "…",
}

NOISE_REGEX = re.compile(r"^[\s.\…]+$")


def init_state_v01(n: int) -> EngineStateV01:
    return {
        "v": "0.1",
        "n": n,
        "step0": 0,
        "traits": {trait: 5 for trait in ALL_TRAITS},
        "noise_streak": 0,
        "free_text_allowed_after": True,
        "milestone_votes": {
            "m2": {"vote": "none", "reason": "none"},
            "m6": {"vote": "none", "reason": "none"},
            "m7": {"vote": "none", "reason": "none"},
        },
    }


def milestones_for_N(n: int) -> Dict[str, int]:
    m2 = 2
    m6 = round(0.65 * (n - 1))
    m7 = round(0.80 * (n - 1))
    if m6 == m7:
        m7 = min(n - 1, m7 + 1)
    return {"m2": m2, "m6": m6, "m7": m7}


def is_noise(text: Optional[str]) -> bool:
    if text is None:
        return True
    trimmed = text.strip()
    if len(trimmed) < 3:
        return True
    if NOISE_REGEX.fullmatch(text):
        return True
    if trimmed.lower() in NOISE_WORDS:
        return True
    return False


def clamp_trait(value: int) -> int:
    return max(0, min(10, value))


def normalize_deltas(
    deltas: List[Delta], step_type: str, is_choice: bool
) -> Tuple[List[Delta], bool]:
    original = copy.deepcopy(deltas)
    normalized: List[Delta] = []
    for delta in deltas[:2]:
        value = int(delta["delta"])
        trait = delta["trait"]
        if value > 2:
            value = 2
        if value < -2:
            value = -2
        if is_choice and trait in CORE_TRAITS and value < 0:
            value = 0
        normalized.append({"trait": trait, "delta": value})

    limit = STEP_LIMITS[step_type]
    sum_abs = sum(abs(d["delta"]) for d in normalized)
    if sum_abs > limit:
        remaining = limit
        adjusted: List[Delta] = []
        for delta in normalized:
            value = delta["delta"]
            if remaining <= 0 or value == 0:
                adj = 0
            else:
                adj = min(abs(value), remaining)
                if value < 0:
                    adj = -adj
            adjusted.append({"trait": delta["trait"], "delta": adj})
            remaining -= abs(adj)
        normalized = adjusted

    normalized = [d for d in normalized if d["delta"] != 0]
    clamped = normalized != original
    return normalized, clamped


def apply_deltas(traits: Dict[str, int], deltas: List[Delta]) -> Dict[str, int]:
    updated = copy.deepcopy(traits)
    for delta in deltas:
        trait = delta["trait"]
        updated[trait] = clamp_trait(updated.get(trait, 0) + delta["delta"])
    return updated


def map_leader_to_final(leader: str) -> str:
    if leader in {"t1", "t5"}:
        return "F1"
    if leader in {"t2", "t4"}:
        return "F2"
    return "F3"


def tie_break_winner(state: EngineStateV01) -> Tuple[Optional[str], Dict[str, int]]:
    votes = {trait: 0 for trait in CORE_TRAITS}
    for milestone_vote in state["milestone_votes"].values():
        vote = milestone_vote["vote"]
        if vote in votes:
            votes[vote] += 1
    max_votes = max(votes.values())
    if max_votes == 0:
        return None, votes
    leaders = [trait for trait, count in votes.items() if count == max_votes]
    if len(leaders) != 1:
        return None, votes
    return leaders[0], votes


def pick_final(state: EngineStateV01) -> Tuple[str, FinalMetaV01]:
    traits = state["traits"]
    core_values = {trait: traits[trait] for trait in CORE_TRAITS}
    sorted_values = sorted(core_values.values(), reverse=True)
    max_core = sorted_values[0]
    top2 = sorted_values[1] if len(sorted_values) > 1 else sorted_values[0]
    gap = max_core - top2
    min_core = min(core_values.values())
    leaders = [trait for trait, value in core_values.items() if value == max_core]
    leader_core = leaders[0] if len(leaders) == 1 else "tie"

    final_id: str
    final_meta: FinalMetaV01 = {
        "max_core": max_core,
        "min_core": min_core,
        "gap_core": gap,
        "leader_core": leader_core,
        "tie_break_used": False,
        "tie_break_votes": {trait: 0 for trait in CORE_TRAITS},
        "tie_break_winner": None,
        "f5_reason": None,
        "f4_tone": None,
    }

    if state["noise_streak"] >= 5:
        final_id = "F5"
        final_meta.update({"rule_hit": 0, "f5_reason": "noise_abort"})
        return final_id, final_meta

    if traits["t6"] >= 9 and max_core <= 8:
        final_id = "F5"
        final_meta.update({"rule_hit": 1, "f5_reason": "chaos_dominant"})
        return final_id, final_meta

    if max_core >= 9 and gap >= 2 and leader_core != "tie":
        final_id = map_leader_to_final(leader_core)
        final_meta.update({"rule_hit": 2})
        return final_id, final_meta

    if max_core >= 9:
        winner, votes = tie_break_winner(state)
        final_meta.update({
            "rule_hit": 3,
            "tie_break_used": True,
            "tie_break_votes": votes,
            "tie_break_winner": winner,
        })
        if winner:
            final_id = map_leader_to_final(winner)
            return final_id, final_meta
        final_id = "F4"
        final_meta["f4_tone"] = "growth" if min_core <= 3 else "success"
        return final_id, final_meta

    final_id = "F4"
    final_meta.update({"rule_hit": 4, "f4_tone": "growth" if min_core <= 3 else "success"})
    return final_id, final_meta


def find_choice(content_step: ContentStep, choice_id: str) -> Optional[Choice]:
    for choice in content_step["choices"]:
        if choice["choice_id"] == choice_id:
            return choice
    return None


def apply_turn(
    state: EngineStateV01, turn: Turn, content_step: ContentStep
) -> Tuple[EngineStateV01, StepLogV01]:
    old_state = copy.deepcopy(state)
    step0 = old_state["step0"]
    step_type = content_step["step_type"]
    milestones = milestones_for_N(old_state["n"])
    milestone_id = None
    for mid, step in milestones.items():
        if step0 == step:
            milestone_id = mid
            break

    traits_before = copy.deepcopy(old_state["traits"])
    applied_deltas: List[Delta] = []
    neutral_reason: Optional[str] = None
    content_missing_mapping = False
    content_delta_clamped = False
    classifier_delta_clamped = False

    turn_kind = turn.get("kind")
    choice_id = turn.get("choice_id") if turn_kind == "choice" else None
    text = turn.get("text") if turn_kind == "free_text" else None

    noise_input = False
    if turn_kind == "free_text":
        noise_input = is_noise(text)
        if noise_input:
            neutral_reason = "noise_input"
        else:
            neutral_reason = "parse_fail"

    if turn_kind == "choice":
        if not choice_id:
            neutral_reason = "missing_mapping"
            content_missing_mapping = True
        else:
            choice = find_choice(content_step, choice_id)
            if choice is None:
                neutral_reason = "missing_mapping"
                content_missing_mapping = True
            else:
                applied_deltas, content_delta_clamped = normalize_deltas(
                    choice["deltas"], step_type, True
                )

    noise_streak_before = old_state["noise_streak"]
    if turn_kind == "free_text" and noise_input:
        noise_streak_after = noise_streak_before + 1
    else:
        noise_streak_after = 0
    free_text_allowed_after = noise_streak_after < 3

    final_id: Optional[str] = None
    final_meta: Optional[FinalMetaV01] = None

    milestone_vote_current: Optional[MilestoneVote] = None
    milestone_vote_missing: List[str] = []

    new_state = copy.deepcopy(old_state)
    new_state["noise_streak"] = noise_streak_after
    new_state["free_text_allowed_after"] = free_text_allowed_after

    if noise_streak_after >= 5:
        final_id = "F5"
        final_meta = {
            "rule_hit": 0,
            "max_core": max(traits_before[trait] for trait in CORE_TRAITS),
            "min_core": min(traits_before[trait] for trait in CORE_TRAITS),
            "gap_core": 0,
            "leader_core": "tie",
            "tie_break_used": False,
            "tie_break_votes": {trait: 0 for trait in CORE_TRAITS},
            "tie_break_winner": None,
            "f5_reason": "noise_abort",
            "f4_tone": None,
        }

    if neutral_reason is None and final_id is None:
        new_state["traits"] = apply_deltas(new_state["traits"], applied_deltas)

    if milestone_id:
        if neutral_reason is None:
            if turn_kind == "choice" and choice_id:
                choice = find_choice(content_step, choice_id)
                if choice is not None:
                    milestone_vote_current = copy.deepcopy(choice["milestone_vote"])
                    new_state["milestone_votes"][milestone_id] = milestone_vote_current
                else:
                    milestone_vote_current = {"vote": "none", "reason": "none"}
            else:
                milestone_vote_current = {"vote": "none", "reason": "none"}
        else:
            milestone_vote_current = {"vote": "none", "reason": "none"}
            milestone_vote_missing.append(milestone_id)

    if final_id is None and step0 == old_state["n"] - 1:
        final_id, final_meta = pick_final(new_state)

    if final_id is None:
        new_state["step0"] = step0 + 1

    user_input_present = False
    if turn_kind == "choice":
        user_input_present = bool(choice_id)
    elif turn_kind == "free_text":
        user_input_present = bool(text)

    step_log: StepLogV01 = {
        "v": old_state["v"],
        "n": old_state["n"],
        "step0": step0,
        "step_type": step_type,
        "turn_kind": turn_kind or "",
        "choice_id": choice_id,
        "user_input_present": user_input_present,
        "noise_input": noise_input,
        "noise_streak_before": noise_streak_before,
        "noise_streak_after": noise_streak_after,
        "free_text_allowed_after": free_text_allowed_after,
        "neutral_reason": neutral_reason,
        "applied_deltas": applied_deltas,
        "traits_before": traits_before,
        "traits_after": copy.deepcopy(new_state["traits"]),
        "milestone_id": milestone_id,
        "milestone_vote_current": milestone_vote_current,
        "milestone_vote_missing": milestone_vote_missing,
        "final_id": final_id,
        "final_meta": final_meta,
        "content_delta_clamped": content_delta_clamped,
        "classifier_delta_clamped": classifier_delta_clamped,
        "content_missing_mapping": content_missing_mapping,
    }

    return new_state, step_log
