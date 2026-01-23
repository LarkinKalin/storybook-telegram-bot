from __future__ import annotations

from typing import Dict

from packages.engine.src.engine_v0_1 import milestones_for_N

TRAIT_LABELS = {
    "t1": "Смелость",
    "t2": "Доброта",
    "t3": "Мудрость",
    "t4": "Честность",
    "t5": "Ответственность",
    "t6": "Фантазия",
}


def _step_type_for(step0: int, n: int) -> str:
    milestones = milestones_for_N(n)
    if step0 == milestones["m2"]:
        return "SEMI"
    if step0 in {milestones["m6"], milestones["m7"]}:
        return "HEAVY"
    return "NORMAL"


def _choice_traits(step0: int) -> list[str]:
    variants = [
        ["t1", "t2", "t3"],
        ["t4", "t5", "t6"],
        ["t1", "t5", "t6"],
    ]
    return variants[step0 % len(variants)]


def build_content_step(theme_id: str, step0: int, engine_state: Dict) -> Dict:
    n = engine_state["n"]
    step_type = _step_type_for(step0, n)
    traits = _choice_traits(step0)
    choices = []
    milestone_id = None
    milestones = milestones_for_N(n)
    for mid, milestone_step in milestones.items():
        if milestone_step == step0:
            milestone_id = mid
            break
    for idx, trait in enumerate(traits):
        choice_id = chr(ord("A") + idx)
        choices.append(
            {
                "choice_id": choice_id,
                "label": f"{choice_id} — {TRAIT_LABELS[trait]}",
                "deltas": [{"trait": trait, "delta": 1}],
                "milestone_vote": (
                    {"vote": trait, "reason": "content"}
                    if milestone_id
                    else {"vote": "none", "reason": "none"}
                ),
            }
        )
    scene_text = (
        f"Тема {theme_id}: сцена {step0 + 1}.\n"
        "Герой оказывается перед выбором, который меняет ход истории."
    )
    return {
        "scene_text": scene_text,
        "step_type": step_type,
        "choices": choices,
        "milestone_id": milestone_id,
    }
