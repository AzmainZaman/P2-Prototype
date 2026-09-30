"""Configuration records for a question and its rubric (Report §4.2.5, Table 4.9).

A saved Configuration is immutable: editing a question produces a new
config_id with the next version number. Original teacher-entered text is kept
as typed; normalization is applied only when comparing text (see normalize.py).
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field, fields
from typing import List, Optional

ACTIONS = ("cap", "penalty", "review")
KINDS = ("concept", "phrase")

# Fields filled in by the store when a version is saved; excluded from the content hash.
SAVE_METADATA = ("config_id", "version", "created_at", "content_hash", "parent_config_id")


@dataclass
class Concept:
    """A credit-bearing idea with a weight (FR-02)."""

    id: str
    label: str = ""
    weight: float = 1.0
    expressions: List[str] = field(default_factory=list)
    clauses: List[str] = field(default_factory=list)
    allow_overlap: bool = False


@dataclass
class RequiredItem:
    """A condition whose absence caps the mark (FR-03).

    kind="concept" links to a concept in the same configuration;
    kind="phrase" uses its own phrases and clause patterns.
    """

    id: str
    kind: str = "concept"
    concept_id: Optional[str] = None
    phrases: List[str] = field(default_factory=list)
    clauses: List[str] = field(default_factory=list)
    absence_cap: float = 0.0


@dataclass
class WrongIdea:
    """A configured misconception with exactly one action (FR-04)."""

    id: str
    label: str = ""
    expressions: List[str] = field(default_factory=list)
    clauses: List[str] = field(default_factory=list)
    action: str = "review"
    amount: Optional[float] = None


@dataclass
class Configuration:
    question_id: str
    domain: str = "General science"
    prompt: str = ""
    model_answer: str = ""
    max_mark: float = 10.0
    increment: float = 0.5
    concepts: List[Concept] = field(default_factory=list)
    required_items: List[RequiredItem] = field(default_factory=list)
    wrong_ideas: List[WrongIdea] = field(default_factory=list)
    # Save metadata, assigned by the store.
    config_id: Optional[str] = None
    version: Optional[int] = None
    created_at: Optional[str] = None
    content_hash: Optional[str] = None
    parent_config_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def content_dict(self) -> dict:
        data = self.to_dict()
        for key in SAVE_METADATA:
            data.pop(key, None)
        return data

    def as_draft(self) -> "Configuration":
        """A copy with save metadata cleared, used as the start of a new version."""
        draft = copy.deepcopy(self)
        for key in SAVE_METADATA:
            setattr(draft, key, None)
        return draft

    @classmethod
    def from_dict(cls, data: dict) -> "Configuration":
        data = dict(data)
        concepts = [_build(Concept, c) for c in data.pop("concepts", [])]
        required = [_build(RequiredItem, r) for r in data.pop("required_items", [])]
        wrong = [_build(WrongIdea, w) for w in data.pop("wrong_ideas", [])]
        cfg = _build(cls, data)
        cfg.concepts, cfg.required_items, cfg.wrong_ideas = concepts, required, wrong
        return cfg


def _build(cls, data: dict):
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in known})
