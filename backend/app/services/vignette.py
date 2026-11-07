from __future__ import annotations

import re
import unicodedata

from app.services.llm import LLMProvider


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value or "").casefold()
    normalized = normalized.replace("\u0307", "")
    return re.sub(r"\s+", " ", normalized).strip()


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^\wçğıöşü]+", _normalize(value)) if len(token) >= 4]


def _criterion_keywords(criterion: dict) -> list[str]:
    keywords = [_normalize(str(item)) for item in criterion.get("keywords", []) if str(item).strip()]
    if keywords:
        return keywords
    return _tokens(str(criterion.get("description", ""))) [:4] or _tokens(
        str(criterion.get("label", ""))
    )[:4]


def _criteria_scores(
    answer_text: str,
    rubric: list[dict],
    llm_scores: dict[str, float] | None = None,
) -> tuple[list[dict], float, float]:
    answer = _normalize(answer_text)
    criteria: list[dict] = []
    earned = 0.0
    possible = 0.0
    for criterion in rubric:
        weight = float(criterion.get("weight", 1.0) or 1.0)
        keywords = _criterion_keywords(criterion)
        hits = [keyword for keyword in keywords if keyword in answer]
        min_hits = max(1, int(criterion.get("min_hits", 1) or 1))
        deterministic = min(1.0, len(hits) / min_hits) if keywords else 0.0
        label = str(criterion.get("label", "")).strip()
        score = deterministic
        if llm_scores is not None and label.casefold() in llm_scores:
            score = max(0.0, min(1.0, float(llm_scores[label.casefold()])))
        criteria.append(
            {
                "label": label,
                "weight": weight,
                "score": round(score, 4),
                "hits": hits[:10],
                "feedback": str(criterion.get("description", "")),
            }
        )
        earned += weight * score
        possible += weight
    normalized_score = earned / possible if possible else 0.0
    return criteria, round(normalized_score, 4), round(possible, 4)


def _llm_scores(
    provider: LLMProvider | None,
    answer_text: str,
    rubric: list[dict],
    vignette_text: str,
) -> dict[str, float] | None:
    if provider is None or provider.name == "fake":
        return None
    schema = {
        "type": "object",
        "properties": {
            "criteria": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "score": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["label", "score"],
                },
            }
        },
        "required": ["criteria"],
    }
    prompt = (
        "Aşağıdaki klinik vaka cevabını verilen rubrikle değerlendir. "
        "Her kriter için yalnızca 0-1 arası bir puan ver; tıbbi doğruluk ve "
        "kaynakla uyum esas alınmalı. JSON döndür.\n\n"
        f"Vaka:\n{vignette_text}\n\n"
        f"Rubrik:\n{rubric}\n\n"
        f"Öğrenci cevabı:\n{answer_text}"
    )
    try:
        raw = provider.complete_json(
            "Rubrik tabanlı tıp eğitimi değerlendiricisisin. Sadece JSON üret.",
            prompt,
            schema,
            "evaluate_vignette",
        )
        scores: dict[str, float] = {}
        for item in raw.get("criteria", []):
            label = str(item.get("label", "")).casefold().strip()
            if label:
                scores[label] = float(item.get("score", 0.0))
        return scores or None
    except Exception:
        return None


def evaluate(
    answer_text: str,
    payload: dict,
    *,
    provider: LLMProvider | None = None,
    pass_score: float = 0.65,
) -> dict:
    rubric = payload.get("rubric") or []
    llm_scores = _llm_scores(provider, answer_text, rubric, str(payload.get("vignette", "")))
    criteria, score, possible = _criteria_scores(answer_text, rubric, llm_scores)
    passed = score >= pass_score
    missed = [item["label"] for item in criteria if item["score"] < 0.5]
    if passed:
        feedback = "Rubrikteki temel kriterleri karşıladınız."
    else:
        feedback = "Rubrikte eksik kalan kriterler: " + ", ".join(missed or ["genel gerekçe"])
    return {
        "score": score,
        "possible": possible,
        "passed": passed,
        "criteria": criteria,
        "feedback": feedback,
        "evaluator": "llm+rubric" if llm_scores is not None else "rubric",
        "model_answer": payload.get("model_answer", ""),
    }
