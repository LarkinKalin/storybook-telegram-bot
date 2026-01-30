from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_WORD_RE = re.compile(r"[^a-zа-я0-9\s]+", flags=re.IGNORECASE)


@dataclass(frozen=True)
class WhyAnswer:
    text: str
    matched: bool
    matched_id: str | None
    score: int


class WhyQA:
    def __init__(self, data_path: Path) -> None:
        self._data_path = data_path
        self._items: list[dict[str, object]] = []
        self._loaded = False

    def load(self) -> None:
        if not self._data_path.exists():
            raise FileNotFoundError(f"Missing why_qa data: {self._data_path}")
        with self._data_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            raise ValueError("why_qa.json must contain object root")
        items = raw.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("why_qa.json must contain non-empty items list")
        self._items = [self._validate_item(item) for item in items]
        self._loaded = True

    def answer(self, question: str, audience: str) -> WhyAnswer:
        self._ensure_loaded()
        normalized = normalize_text(question)
        if not normalized:
            return WhyAnswer(text=self._fallback(audience), matched=False, matched_id=None, score=0)

        best_item: dict[str, object] | None = None
        best_score = 0
        best_hits = 0
        for item in self._items:
            score, hits = self._score_item(item, normalized)
            if score > best_score or (score == best_score and hits > best_hits):
                best_score = score
                best_hits = hits
                best_item = item

        if not best_item or best_score < 2:
            return WhyAnswer(text=self._fallback(audience), matched=False, matched_id=None, score=0)

        answer_key = "answer_kid" if audience == "kid" else "answer_adult"
        answer = best_item.get(answer_key)
        if not isinstance(answer, str) or not answer.strip():
            return WhyAnswer(text=self._fallback(audience), matched=False, matched_id=None, score=0)

        item_id = best_item.get("id")
        return WhyAnswer(
            text=answer,
            matched=True,
            matched_id=item_id if isinstance(item_id, str) else None,
            score=best_score,
        )

    def _score_item(self, item: dict[str, object], normalized: str) -> tuple[int, int]:
        keywords = item.get("keywords")
        if not isinstance(keywords, list):
            return 0, 0
        tokens = normalized.split()
        score = 0
        hits = 0
        for keyword in keywords:
            if not isinstance(keyword, str):
                continue
            kw = normalize_text(keyword)
            if not kw:
                continue
            if " " in kw:
                if kw in normalized:
                    score += 2
                    hits += 1
                continue

            if kw in tokens:
                score += 2
                hits += 1
                continue

            if len(kw) >= 4 and any(kw in token for token in tokens):
                score += 1
                hits += 1

        return score, hits

    def _fallback(self, audience: str) -> str:
        sample_questions = self._sample_questions()
        prompt = "Попробуй спросить по-другому или, например:\n"
        prompt += "\n".join(f"• {q}" for q in sample_questions)
        if audience == "adult":
            return (
                "Похоже, я ещё не знаю такой ответ. "
                + prompt
                + "\nЕсли хочешь, уточни детали — я постараюсь разобраться."
            )
        return (
            "Пока не нашла ответ, но я учусь! "
            + prompt
            + "\nМожно задать вопрос проще или короче."
        )

    def _sample_questions(self) -> list[str]:
        samples: list[str] = []
        for item in self._items:
            item_samples = item.get("sample_questions")
            if not isinstance(item_samples, list):
                continue
            for sample in item_samples:
                if isinstance(sample, str) and sample.strip():
                    samples.append(sample.strip())
        return samples[:3] if samples else ["Почему небо голубое?", "Откуда берётся дождь?"]

    def _validate_item(self, item: object) -> dict[str, object]:
        if not isinstance(item, dict):
            raise ValueError("why_qa item must be object")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError("why_qa item id is empty")
        keywords = item.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            raise ValueError(f"why_qa item {item_id} keywords invalid")
        answer_kid = item.get("answer_kid")
        answer_adult = item.get("answer_adult")
        if not isinstance(answer_kid, str) or not answer_kid.strip():
            raise ValueError(f"why_qa item {item_id} answer_kid invalid")
        if not isinstance(answer_adult, str) or not answer_adult.strip():
            raise ValueError(f"why_qa item {item_id} answer_adult invalid")
        return item

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()


def normalize_text(text: str) -> str:
    cleaned = text.lower().replace("ё", "е")
    cleaned = _WORD_RE.sub(" ", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


_src_root = Path(__file__).resolve().parents[1]
whyqa = WhyQA(_src_root / "data" / "why_qa.json")
