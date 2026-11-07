from __future__ import annotations

from functools import lru_cache
import json
import re

import httpx

from app.core.config import settings
from app.models import ContentChunk
from app.services.llm_schemas import (
    ConceptCandidate,
    ConceptExtractionResult,
    GeneratedCloze,
    GeneratedExercises,
    GeneratedMCQ,
    GeneratedMatching,
    GeneratedVignette,
    MatchingPair,
    RubricCriterion,
)


class LLMError(Exception):
    pass


class LLMConfigError(LLMError):
    pass


class LLMGenerationError(LLMError):
    pass


PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """Sen anestezi tıp eğitimi için içerik üreten bir asistansın.
Kurallar:
- Yalnızca verilen kaynak metne dayan; kaynakta olmayan tıbbi bilgi, doz veya iddia ekleme.
- Yanıtını SADECE geçerli JSON olarak döndür; markdown, açıklama veya kod bloğu kullanma.
- Türkçe yaz.
- Her üretilen öğe, verilen source_chunk_id değerini taşımalı.
- Emin olmadığın bilgiyi üretme.
"""


def _json_schema_prompt(schema: dict) -> str:
    return (
        "Çıktı şu JSON şemasına tam uymalıdır:\n"
        + json.dumps(schema, ensure_ascii=False)
    )


def _concept_prompt(chunk: ContentChunk, max_concepts: int) -> str:
    schema = ConceptExtractionResult.model_json_schema()
    return (
        f"Kaynak chunk_id: {chunk.id}\n"
        f"Bölüm: {chunk.section_title}\n"
        f"Metin:\n{chunk.raw_text[:12000]}\n\n"
        f"Bu metinden en fazla {max_concepts} anahtar kavram çıkar. "
        "Her kavram için term, category, key_facts ve source_chunk_id alanlarını doldur. "
        "key_facts maddeleri yalnızca metinde geçen bilgiler olmalı.\n\n"
        + _json_schema_prompt(schema)
    )


def _exercise_prompt(chunk: ContentChunk, concept: ConceptCandidate, types: list[str]) -> str:
    schema = GeneratedExercises.model_json_schema()
    facts = "\n".join(f"- {fact}" for fact in concept.key_facts) or chunk.raw_text[:4000]
    return (
        f"Kaynak chunk_id: {chunk.id}\n"
        f"Bölüm: {chunk.section_title}\n"
        f"Kavram: {concept.term}\n"
        f"Kavram bilgileri:\n{facts}\n\n"
        f"Kaynak metin:\n{chunk.raw_text[:10000]}\n\n"
        f"Şu egzersiz tiplerini üret: {', '.join(types)}.\n"
        "- mcq: tek doğru seçenekli, 4 seçenekli soru; options içinde is_correct alanı.\n"
        "- cloze: metinde {{blank}} yer tutucusu ve answer alanı.\n"
        "- matching: en az 2 left/right çifti.\n"
        "- vignette: kısa klinik vaka, açık uçlu soru, en az 2 rubrik kriteri ve model_answer.\n"
        "Her egzersizde source_chunk_id, difficulty (0-1) ve explanation olsun.\n\n"
        + _json_schema_prompt(schema)
    )


class LLMProvider:
    name = "base"
    model = ""

    def extract_concepts(self, chunk: ContentChunk, max_concepts: int = 5) -> ConceptExtractionResult:
        def validate(result: ConceptExtractionResult) -> None:
            if not result.concepts:
                raise ValueError("En az bir kavram üretilmelidir")
            for concept in result.concepts:
                if not concept.key_facts:
                    raise ValueError("Her kavram en az bir key_fact içermelidir")
                concept.source_chunk_id = chunk.id

        return self._generate(
            SYSTEM_PROMPT,
            _concept_prompt(chunk, max_concepts),
            ConceptExtractionResult,
            "extract_concepts",
            validate,
        )

    def generate_exercises(
        self, chunk: ContentChunk, concept: ConceptCandidate, types: list[str]
    ) -> GeneratedExercises:
        supported = [item for item in types if item in {"mcq", "cloze", "matching", "vignette"}]
        if not supported:
            return GeneratedExercises(exercises=[])

        def validate(result: GeneratedExercises) -> None:
            if not result.exercises:
                raise ValueError("En az bir egzersiz üretilmelidir")
            for exercise in result.exercises:
                exercise.source_chunk_id = chunk.id

        return self._generate(
            SYSTEM_PROMPT,
            _exercise_prompt(chunk, concept, supported),
            GeneratedExercises,
            "generate_exercises",
            validate,
        )

    def _generate(self, system: str, user: str, model_cls, schema_name: str, validator=None):
        last_error = "bilinmeyen hata"
        for attempt in range(settings.llm_max_retries + 1):
            prompt = user
            if attempt > 0:
                prompt += (
                    "\n\nÖNCEKİ ÇIKTI GEÇERSİZDİ: "
                    + last_error
                    + "\nLütfen şemaya tam uyan yeni bir JSON üret."
                )
            try:
                raw = self.complete_json(system, prompt, model_cls.model_json_schema(), schema_name)
                result = model_cls.model_validate(raw)
                if validator is not None:
                    validator(result)
                return result
            except LLMConfigError:
                raise
            except Exception as exc:
                last_error = str(exc)[:2000]
        raise LLMGenerationError(
            f"LLM çıktısı {settings.llm_max_retries + 1} denemede doğrulanamadı: {last_error}"
        )

    def complete_json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        raise NotImplementedError


class FakeLLMProvider(LLMProvider):
    """Deterministic offline provider for development and tests.

    It produces structurally valid exercises from the source text. The content is
    intentionally generic and must never be used as medical learning material.
    """

    name = "fake"
    model = "fake-deterministic"

    def extract_concepts(self, chunk: ContentChunk, max_concepts: int = 5) -> ConceptExtractionResult:
        sentences = _sentences(chunk.raw_text)
        facts = [sentence for sentence in sentences if len(sentence.split()) >= 4][:max_concepts]
        if not facts:
            facts = [chunk.raw_text.strip()[:300]]
        term = chunk.section_title.strip() or " ".join(facts[0].split()[:5])
        concept = ConceptCandidate(
            term=term[:255],
            category="genel",
            key_facts=facts[:5],
            source_chunk_id=chunk.id,
        )
        return ConceptExtractionResult(concepts=[concept])

    def generate_exercises(
        self, chunk: ContentChunk, concept: ConceptCandidate, types: list[str]
    ) -> GeneratedExercises:
        facts = [fact.strip() for fact in concept.key_facts if fact.strip()]
        if not facts:
            facts = [chunk.raw_text.strip()[:400]]
        exercises = []
        if "mcq" in types:
            correct = facts[0][:900]
            distractors = [
                "Bu bilgi verilen kaynak metinde yer almamaktadır.",
                "Bu ifade kaynak metindeki kavramla çelişmektedir.",
                "Kaynak metin bu konuda farklı bir sonuç belirtmektedir.",
            ]
            options = [{"text": correct, "is_correct": True}] + [
                {"text": text, "is_correct": False} for text in distractors
            ]
            exercises.append(
                GeneratedMCQ(
                    stem=f"{concept.term} hakkında aşağıdakilerden hangisi kaynakla uyumludur?",
                    options=options,
                    explanation=correct,
                    difficulty=0.5,
                    source_chunk_id=chunk.id,
                )
            )
        if "cloze" in types:
            sentence = facts[0]
            words = sentence.split()
            if len(words) >= 4:
                index = min(2, len(words) - 1)
                answer = words[index].strip(".,;:()[]")
                if answer:
                    words[index] = "{{blank}}"
                    exercises.append(
                        GeneratedCloze(
                            text=" ".join(words),
                            answer=answer,
                            alternatives=[],
                            explanation=sentence,
                            difficulty=0.5,
                            source_chunk_id=chunk.id,
                        )
                    )
        if "matching" in types and len(facts) >= 2:
            pairs = [
                MatchingPair(left=f"{concept.term} — {index + 1}", right=fact[:500])
                for index, fact in enumerate(facts[:3])
            ]
            exercises.append(
                GeneratedMatching(
                    pairs=pairs,
                    explanation="Kavram bilgileriyle eşleştirin.",
                    difficulty=0.5,
                    source_chunk_id=chunk.id,
                )
            )
        if "vignette" in types:
            keywords = [
                word.strip(".,;:()[]").casefold()
                for word in facts[0].split()
                if len(word.strip(".,;:()[]")) >= 6
            ][:5]
            if not keywords:
                keywords = [
                    word.strip(".,;:()[]").casefold()
                    for word in facts[0].split()
                    if len(word.strip(".,;:()[]")) >= 3
                ][:3]
            exercises.append(
                GeneratedVignette(
                    vignette=f"Klinik senaryo: {facts[0][:1200]}",
                    prompt="Bu vakada anahtar kararı ve gerekçenizi açıklayın.",
                    rubric=[
                        RubricCriterion(
                            label="Kaynakla uyumlu ana karar",
                            description=facts[0][:700],
                            keywords=keywords,
                            weight=2.0,
                        ),
                        RubricCriterion(
                            label="Gerekçe",
                            description=facts[1][:700] if len(facts) > 1 else "Kararın gerekçesi",
                            keywords=keywords[:2],
                            weight=1.0,
                        ),
                    ],
                    model_answer=facts[0][:2000],
                    explanation="Rubrik, kaynak metindeki anahtar ifadeleri arar.",
                    difficulty=0.6,
                    source_chunk_id=chunk.id,
                )
            )
        return GeneratedExercises(exercises=exercises)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai"

    def __init__(self) -> None:
        if not settings.llm_api_key:
            raise LLMConfigError("MEDSPACED_LLM_API_KEY tanımlı değil")
        self.model = settings.llm_model
        self.base_url = settings.llm_base_url.rstrip("/")

    def complete_json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        payload = {
            "model": self.model,
            "temperature": settings.llm_temperature,
            "messages": [
                {"role": "system", "content": system + "\n\n" + _json_schema_prompt(schema)},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=settings.llm_timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM isteği başarısız: {exc}") from exc
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM yanıt yapısı beklenmedik") from exc
        return _parse_json(content)


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        if not settings.llm_api_key:
            raise LLMConfigError("MEDSPACED_LLM_API_KEY tanımlı değil")
        self.model = settings.llm_model
        self.base_url = settings.llm_base_url.rstrip("/")

    def complete_json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": settings.llm_temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [
                {
                    "name": schema_name,
                    "description": "Şemaya uygun JSON çıktısı üret.",
                    "input_schema": schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": schema_name},
        }
        headers = {
            "x-api-key": settings.llm_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            response = httpx.post(
                f"{self.base_url}/messages",
                json=payload,
                headers=headers,
                timeout=settings.llm_timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"Anthropic isteği başarısız: {exc}") from exc
        data = response.json()
        for block in data.get("content", []):
            if block.get("type") == "tool_use":
                return block.get("input", {})
        raise LLMError("Anthropic yanıtında tool_use bloğu bulunamadı")


def _parse_json(content: str) -> dict:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"LLM geçerli JSON döndürmedi: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMError("LLM yanıtı JSON nesnesi değil")
    return parsed


@lru_cache
def get_provider() -> LLMProvider:
    provider = settings.llm_provider.strip().lower()
    if provider == "fake":
        return FakeLLMProvider()
    if provider in {"openai", "openai-compatible", "ollama", "vllm"}:
        return OpenAICompatibleProvider()
    if provider == "anthropic":
        return AnthropicProvider()
    raise LLMConfigError(f"Bilinmeyen LLM sağlayıcısı: {provider}")


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    pieces = re.split(r"(?<=[.!?])\s+", normalized)
    return [piece.strip() for piece in pieces if len(piece.strip()) > 20]
