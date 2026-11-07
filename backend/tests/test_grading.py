from app.models import Exercise
from app.services.study import grade


def _exercise(exercise_type: str, payload: dict) -> Exercise:
    return Exercise(
        type=exercise_type,
        payload=payload,
        difficulty=0.5,
        discrimination=1.0,
        guessing=0.0,
        status="approved",
        source_chunk_id="chunk-grading",
        created_by_ai=True,
        dedupe_hash=f"grading-{exercise_type}",
    )


def test_cloze_grading_normalizes_answer_and_accepts_alternatives():
    exercise = _exercise(
        "cloze",
        {
            "text": "Anestezi indüksiyonunda {{blank}} kullanılır.",
            "answer": "Propofol",
            "alternatives": ["propofol"],
            "explanation": "İndüksiyon ajanı.",
        },
    )
    correct, answer, _ = grade(exercise, {"text": "  PROPofol "})
    assert correct is True
    assert answer == {"text": "Propofol"}

    wrong, _, _ = grade(exercise, {"text": "Ketamin"})
    assert wrong is False


def test_matching_grading_requires_all_pairs():
    exercise = _exercise(
        "matching",
        {
            "pairs": [
                {"left": "Propofol", "right": "İndüksiyon"},
                {"left": "Süksinilkolin", "right": "Depolarizan blokör"},
            ],
            "explanation": "İlaç-etki eşleştirmesi.",
        },
    )
    correct, answer, _ = grade(
        exercise,
        {"pairs": {"Propofol": "İndüksiyon", "Süksinilkolin": "Depolarizan blokör"}},
    )
    assert correct is True
    assert len(answer["pairs"]) == 2

    wrong, _, _ = grade(
        exercise,
        {"pairs": {"Propofol": "Depolarizan blokör", "Süksinilkolin": "İndüksiyon"}},
    )
    assert wrong is False


def test_vignette_grading_uses_rubric_keywords():
    exercise = _exercise(
        "vignette",
        {
            "vignette": "Kardiyak cerrahi öncesi hastada taşikardi gelişiyor.",
            "prompt": "Anahtar kararı ve gerekçeyi açıklayın.",
            "rubric": [
                {
                    "label": "Karar",
                    "description": "Beta blokör ile hız kontrolü",
                    "keywords": ["beta blokör", "hız kontrolü"],
                    "weight": 2,
                },
                {
                    "label": "Gerekçe",
                    "description": "Miyokard iskemisini azaltmak",
                    "keywords": ["miyokard iskemisi"],
                    "weight": 1,
                },
            ],
            "model_answer": "Beta blokör ile hız kontrolü sağlanır.",
        },
    )
    correct, answer, feedback = grade(
        exercise,
        {"text": "Beta blokör başlanarak hız kontrolü sağlanmalı; miyokard iskemisi azalır."},
    )
    assert correct is True
    assert answer["score"] == 1.0
    assert len(answer["criteria"]) == 2
    assert "karşıladınız" in feedback

    wrong, wrong_answer, _ = grade(exercise, {"text": "Hastayı taburcu edin."})
    assert wrong is False
    assert wrong_answer["score"] == 0.0


def test_vignette_grading_accepts_llm_scores():
    class MockProvider:
        name = "mock"

        def complete_json(self, system, user, schema, schema_name):
            return {
                "criteria": [
                    {"label": "Karar", "score": 0.9},
                    {"label": "Gerekçe", "score": 0.8},
                ]
            }

    exercise = _exercise(
        "vignette",
        {
            "vignette": "Kardiyak cerrahi öncesi hastada taşikardi gelişiyor.",
            "prompt": "Anahtar kararı ve gerekçeyi açıklayın.",
            "rubric": [
                {"label": "Karar", "keywords": ["beta blokör"], "weight": 2},
                {"label": "Gerekçe", "keywords": ["iskemi"], "weight": 1},
            ],
            "model_answer": "Beta blokör.",
            "explanation": "Rubrik değerlendirmesi.",
        },
    )
    correct, answer, _ = grade(exercise, {"text": "Beta blokör ile hız kontrolü."}, provider=MockProvider())
    assert correct is True
    assert answer["score"] == 0.8667
    assert answer["criteria"][0]["score"] == 0.9
