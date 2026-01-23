from __future__ import annotations

from typing import Dict, List, Optional, TypedDict


class Delta(TypedDict):
    trait: str
    delta: int


class MilestoneVote(TypedDict):
    vote: str
    reason: str


class Choice(TypedDict):
    choice_id: str
    deltas: List[Delta]
    milestone_vote: MilestoneVote


class ContentStep(TypedDict):
    step_type: str
    choices: List[Choice]


class Turn(TypedDict, total=False):
    kind: str
    choice_id: Optional[str]
    text: Optional[str]


class EngineStateV01(TypedDict):
    v: str
    n: int
    step0: int
    traits: Dict[str, int]
    noise_streak: int
    free_text_allowed_after: bool
    milestone_votes: Dict[str, MilestoneVote]


class FinalMetaV01(TypedDict, total=False):
    rule_hit: int
    max_core: int
    min_core: int
    gap_core: int
    leader_core: str
    tie_break_used: bool
    tie_break_votes: Dict[str, int]
    tie_break_winner: Optional[str]
    f5_reason: Optional[str]
    f4_tone: Optional[str]


class StepLogV01(TypedDict):
    v: str
    n: int
    step0: int
    step_type: str
    turn_kind: str
    choice_id: Optional[str]
    user_input_present: bool
    noise_input: bool
    noise_streak_before: int
    noise_streak_after: int
    free_text_allowed_after: bool
    neutral_reason: Optional[str]
    applied_deltas: List[Delta]
    traits_before: Dict[str, int]
    traits_after: Dict[str, int]
    milestone_id: Optional[str]
    milestone_vote_current: Optional[MilestoneVote]
    milestone_vote_missing: List[str]
    final_id: Optional[str]
    final_meta: Optional[FinalMetaV01]
    content_delta_clamped: bool
    classifier_delta_clamped: bool
    content_missing_mapping: bool
