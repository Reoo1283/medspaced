from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, model_validator


class ConceptCandidate(BaseModel):
    term: str = Field(min_length=2, max_length=255)
    category: str = Field(default="genel", max_length=100)
    key_facts: list[str] = Field(default_factory=list, max_length=10)
    source_chunk_id: str


class ConceptExtractionResult(BaseModel):
    concepts: list[ConceptCandidate] = Field(default_factory=list, max_length=10)


class MCQOption(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    is_correct: bool = False


class GeneratedMCQ(BaseModel):
    type: Literal["mcq"] = "mcq"
    stem: str = Field(min_length=5, max_length=2000)
    options: list[MCQOption] = Field(min_length=2, max_length=6)
    explanation: str = Field(default="", max_length=3000)
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    source_chunk_id: str

    @model_validator(mode="after")
    def validate_single_correct(self) -> "GeneratedMCQ":
        correct = [option for option in self.options if option.is_correct]
        if len(correct) != 1:
            raise ValueError("MCQ tam olarak bir doğru seçenek içermelidir")
        texts = [option.text.strip().casefold() for option in self.options]
        if len(set(texts)) != len(texts):
            raise ValueError("MCQ seçenekleri benzersiz olmalıdır")
        return self


class GeneratedCloze(BaseModel):
    type: Literal["cloze"] = "cloze"
    text: str = Field(min_length=5, max_length=4000)
    answer: str = Field(min_length=1, max_length=255)
    alternatives: list[str] = Field(default_factory=list, max_length=10)
    explanation: str = Field(default="", max_length=3000)
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    source_chunk_id: str

    @model_validator(mode="after")
    def validate_blank(self) -> "GeneratedCloze":
        if "{{blank}}" not in self.text:
            raise ValueError("Cloze metni {{blank}} yer tutucusu içermelidir")
        return self


class MatchingPair(BaseModel):
    left: str = Field(min_length=1, max_length=500)
    right: str = Field(min_length=1, max_length=1000)


class GeneratedMatching(BaseModel):
    type: Literal["matching"] = "matching"
    pairs: list[MatchingPair] = Field(min_length=2, max_length=8)
    explanation: str = Field(default="", max_length=3000)
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    source_chunk_id: str

    @model_validator(mode="after")
    def validate_pairs(self) -> "GeneratedMatching":
        lefts = [pair.left.strip().casefold() for pair in self.pairs]
        if len(set(lefts)) != len(lefts):
            raise ValueError("Eşleştirme sol tarafları benzersiz olmalıdır")
        return self


class RubricCriterion(BaseModel):
    label: str = Field(min_length=2, max_length=255)
    description: str = Field(default="", max_length=2000)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    weight: float = Field(default=1.0, ge=0.1, le=5.0)
    min_hits: int = Field(default=1, ge=1, le=10)


class GeneratedVignette(BaseModel):
    type: Literal["vignette"] = "vignette"
    vignette: str = Field(min_length=20, max_length=6000)
    prompt: str = Field(min_length=5, max_length=1500)
    rubric: list[RubricCriterion] = Field(min_length=1, max_length=10)
    model_answer: str = Field(default="", max_length=6000)
    explanation: str = Field(default="", max_length=3000)
    difficulty: float = Field(default=0.5, ge=0.0, le=1.0)
    source_chunk_id: str

    @model_validator(mode="after")
    def validate_rubric(self) -> "GeneratedVignette":
        labels = [item.label.strip().casefold() for item in self.rubric]
        if len(set(labels)) != len(labels):
            raise ValueError("Rubrik kriterleri benzersiz olmalıdır")
        if not any(item.keywords for item in self.rubric):
            raise ValueError("En az bir rubrik kriteri anahtar kelime içermelidir")
        return self


ExerciseDraft = Annotated[
    Union[GeneratedMCQ, GeneratedCloze, GeneratedMatching, GeneratedVignette],
    Field(discriminator="type"),
]


class GeneratedExercises(BaseModel):
    exercises: list[ExerciseDraft] = Field(default_factory=list, max_length=12)
