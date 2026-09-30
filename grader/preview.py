"""Rubric preview: which rubric rules a sample answer would trigger (exact matching only).

This is a teacher aid for checking a rubric before real answers arrive. It
follows the evidence rules of Report Table 4.5 for exact matches:

* a clause that exactly equals an approved clause pattern -> confirmed
* an expression found outside an approved clause -> candidate (needs review)
* an expression in a clause with a negation, quotation or correction marker
  -> uncertain (needs review), unless that clause is itself an approved pattern
* nothing found -> not detected (not proof the idea is absent)

It performs no spelling tolerance, no semantic comparison and produces no mark.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .models import Configuration
from .normalize import CLAUSE_END, Token, comparison_tokens, find_markers, tokenize

CONFIRMED = "confirmed"
CANDIDATE = "candidate"
UNCERTAIN = "uncertain"
NOT_DETECTED = "not_detected"

Span = Tuple[int, int]


@dataclass
class Clause:
    start: int
    end: int
    tokens: List[Token]

    @property
    def words(self) -> List[str]:
        words = [t.text for t in self.tokens]
        while words and words[-1] in CLAUSE_END:
            words.pop()
        return words


@dataclass
class RuleResult:
    rule_id: str
    rule_type: str  # "Concept", "Required item", "Wrong idea"
    label: str
    state: str
    reason: str
    spans: List[Span] = field(default_factory=list)
    effect: Optional[str] = None


def segment_clauses(text: str) -> List[Clause]:
    """Split at sentence punctuation and line breaks, keeping original offsets."""
    clauses: List[Clause] = []
    current: List[Token] = []
    prev_end = 0
    for token in tokenize(text):
        if current and "\n" in text[prev_end:token.start]:
            clauses.append(Clause(current[0].start, current[-1].end, current))
            current = []
        current.append(token)
        prev_end = token.end
        if token.text in CLAUSE_END:
            clauses.append(Clause(current[0].start, current[-1].end, current))
            current = []
    if current:
        clauses.append(Clause(current[0].start, current[-1].end, current))
    return [c for c in clauses if c.words]


def _find(needle: List[str], tokens: List[Token]) -> List[Span]:
    """All token-boundary occurrences of the needle, as original-text spans."""
    n = len(needle)
    if not n:
        return []
    texts = [t.text for t in tokens]
    return [(tokens[i].start, tokens[i + n - 1].end)
            for i in range(len(texts) - n + 1) if texts[i:i + n] == needle]


def _evaluate(expressions: List[str], clause_patterns: List[str], clauses: List[Clause]):
    """State, reason and spans for one rule under the exact-match evidence policy."""
    patterns = [comparison_tokens(p) for p in clause_patterns if comparison_tokens(p)]
    needles = [comparison_tokens(e) for e in expressions if comparison_tokens(e)]

    confirmed: List[Span] = []
    candidates: List[Span] = []
    marked: List[Tuple[Span, List[str]]] = []
    for clause in clauses:
        if clause.words in patterns:
            confirmed.append((clause.start, clause.end))
            continue
        hits = [span for needle in needles for span in _find(needle, clause.tokens)]
        if not hits:
            continue
        markers = find_markers(" ".join(t.text for t in clause.tokens))
        if markers:
            marked.extend((span, markers) for span in hits)
        else:
            candidates.extend(hits)

    if confirmed:
        return CONFIRMED, "An answer clause exactly matches an approved clause pattern.", confirmed
    if marked:
        shown = ", ".join(sorted({f"'{m}'" for _, ms in marked for m in ms}))
        return (UNCERTAIN, f"Expression found in a clause containing the marker {shown}; "
                           "no automatic credit or deduction.", [s for s, _ in marked])
    if candidates:
        return (CANDIDATE, "Expression found, but its clause is not an approved pattern; "
                           "teacher review needed.", candidates)
    return NOT_DETECTED, "No accepted evidence found. This does not prove the idea is absent.", []


def preview(cfg: Configuration, answer: str) -> List[RuleResult]:
    clauses = segment_clauses(answer)
    results: List[RuleResult] = []
    concept_states = {}

    for c in cfg.concepts:
        state, reason, spans = _evaluate(c.expressions, c.clauses, clauses)
        concept_states[c.id] = state
        results.append(RuleResult(c.id, "Concept", c.label, state, reason, spans))

    for r in cfg.required_items:
        if r.kind == "concept":
            state = concept_states.get(r.concept_id, NOT_DETECTED)
            reason = f"Follows concept {r.concept_id}."
            spans: List[Span] = []
            label = f"Requires concept {r.concept_id}"
        else:
            state, reason, spans = _evaluate(r.phrases, r.clauses, clauses)
            label = "Requires phrase: " + " / ".join(r.phrases)
        effect = None
        if state != CONFIRMED:
            effect = f"Provisional cap {r.absence_cap:g} and review"
        results.append(RuleResult(r.id, "Required item", label, state, reason, spans, effect))

    for w in cfg.wrong_ideas:
        state, reason, spans = _evaluate(w.expressions, w.clauses, clauses)
        effect = None
        if state == CONFIRMED:
            effect = {"cap": f"Cap at {w.amount:g} and review" if w.amount is not None else "Cap and review",
                      "penalty": f"Penalty {w.amount:g} and review" if w.amount is not None else "Penalty and review",
                      "review": "Review only"}.get(w.action)
        elif state in (CANDIDATE, UNCERTAIN):
            effect = "Review; no automatic deduction"
        results.append(RuleResult(w.id, "Wrong idea", w.label, state, reason, spans, effect))

    return results


def review_needed(results: List[RuleResult]) -> List[str]:
    """Review reasons that the exact-match evidence alone would raise (subset of §4.2.4)."""
    reasons = []
    for r in results:
        if r.state in (CANDIDATE, UNCERTAIN):
            reasons.append(f"{r.rule_type} {r.rule_id}: {r.state} evidence")
        elif r.rule_type == "Required item" and r.state == NOT_DETECTED:
            reasons.append(f"Required item {r.rule_id} not confirmed")
        elif r.rule_type == "Wrong idea" and r.state == CONFIRMED:
            reasons.append(f"Wrong idea {r.rule_id} confirmed")
    return reasons
