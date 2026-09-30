"""Configuration validation (Report §4.5.1, §4.2.4, FR-05).

Errors block saving; warnings are shown to the teacher but do not block.
Each issue carries its section and item index so the editor can show it next
to the relevant field as well as in the summary.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, List, Optional

from .models import ACTIONS, KINDS, Configuration
from .normalize import code_points, find_markers, normalize

MAX_TEXT_CODE_POINTS = 2000
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class Issue:
    level: str  # "error" or "warning"
    section: str  # "question", "concepts", "required_items", "wrong_ideas"
    index: Optional[int]  # item index within the section, None for section-wide
    field: Optional[str]
    where: str  # human-readable location, e.g. "Concept C1"
    message: str


def has_errors(issues: Iterable[Issue]) -> bool:
    return any(i.level == "error" for i in issues)


def fmt(x: float) -> str:
    return f"{x:g}"


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _is_multiple(x: float, step: float) -> bool:
    ratio = x / step
    return abs(ratio - round(ratio)) < 1e-9


def concept_shares(cfg: Configuration) -> List[Optional[float]]:
    """Each concept's normalized share w_i / sum(w), or None when undefined."""
    weights = [c.weight if _finite(c.weight) and c.weight >= 0 else None for c in cfg.concepts]
    total = sum(w for w in weights if w is not None)
    if total <= 0:
        return [None] * len(weights)
    return [None if w is None else w / total for w in weights]


def validate(
    cfg: Configuration,
    existing_question_ids: Iterable[str] = (),
    is_new_question: bool = True,
) -> List[Issue]:
    issues: List[Issue] = []

    def add(level, section, index, field_name, where, message):
        issues.append(Issue(level, section, index, field_name, where, message))

    # --- Question and mark scale -------------------------------------------
    qid = (cfg.question_id or "").strip()
    if not qid:
        add("error", "question", None, "question_id", "Question", "Question ID is required.")
    elif not ID_PATTERN.match(qid):
        add("error", "question", None, "question_id", "Question",
            "Question ID may contain only letters, digits, '-' and '_'.")
    elif is_new_question and qid in set(existing_question_ids):
        add("error", "question", None, "question_id", "Question",
            f"Question ID '{qid}' already exists. Open it from the library to create a new version.")

    for field_name, label in (("prompt", "Question prompt"), ("model_answer", "Model answer")):
        text = getattr(cfg, field_name)
        if not normalize(text):
            add("error", "question", None, field_name, "Question", f"{label} is required.")
        elif code_points(text) > MAX_TEXT_CODE_POINTS:
            add("error", "question", None, field_name, "Question",
                f"{label} is {code_points(text)} characters; the limit is {MAX_TEXT_CODE_POINTS}.")

    step = cfg.increment
    step_ok = _finite(step) and step > 0
    if not step_ok:
        add("error", "question", None, "increment", "Question", "Mark increment must be greater than zero.")

    max_mark = cfg.max_mark
    max_ok = _finite(max_mark) and max_mark > 0
    if not max_ok:
        add("error", "question", None, "max_mark", "Question", "Maximum mark must be greater than zero.")
    elif step_ok and not _is_multiple(max_mark, step):
        add("error", "question", None, "max_mark", "Question",
            f"Maximum mark must be a multiple of the mark increment ({fmt(step)}).")

    def check_amount(value, section, index, field_name, where, label):
        """Caps and penalties: finite, non-negative, multiple of the increment, at most M."""
        if not _finite(value) or value < 0:
            add("error", section, index, field_name, where, f"{label} must be a non-negative number.")
            return False
        if step_ok and not _is_multiple(value, step):
            add("error", section, index, field_name, where,
                f"{label} must be a multiple of the mark increment ({fmt(step)}).")
            return False
        if max_ok and value > max_mark:
            add("error", section, index, field_name, where,
                f"{label} ({fmt(value)}) cannot exceed the maximum mark ({fmt(max_mark)}).")
            return False
        return True

    # Rule identifiers must be unique across all rubric items.
    seen_ids = defaultdict(list)

    def check_id(item_id, section, index, where):
        item_id = (item_id or "").strip()
        if not item_id:
            add("error", section, index, "id", where, "ID is required.")
        elif not ID_PATTERN.match(item_id):
            add("error", section, index, "id", where, "ID may contain only letters, digits, '-' and '_'.")
        else:
            seen_ids[item_id].append((section, index, where))

    def check_clauses_contain(clauses, expressions, section, index, where, noun):
        norm_exprs = [normalize(e) for e in expressions if normalize(e)]
        if not norm_exprs:
            return
        for n, clause in enumerate(clauses, start=1):
            if not any(e in normalize(clause) for e in norm_exprs):
                add("warning", section, index, "clauses", where,
                    f"Clause pattern {n} does not contain any of the {noun}.")

    def check_markers(texts, section, index, field_name, where, noun):
        """Warn when rubric text contains a negation, quotation or correction marker (§4.5.2)."""
        for n, text in enumerate(texts, start=1):
            markers = find_markers(text)
            if not markers:
                continue
            shown = ", ".join(f"'{m}'" for m in markers)
            if noun == "clause":
                add("warning", section, index, field_name, where,
                    f"Clause pattern {n} contains the marker {shown}. An answer that matches this clause "
                    "exactly is confirmed as written, so check that the negation, correction or quotation "
                    "is intended.")
            else:
                add("warning", section, index, field_name, where,
                    f"{noun} '{normalize(text)}' contains the marker {shown}. Markers usually signal negation "
                    "or correction; check that this wording is intended.")

    # --- Concepts ------------------------------------------------------------
    if not cfg.concepts:
        add("error", "concepts", None, None, "Rubric", "Add at least one weighted concept.")

    weights_valid = True
    total_weight = 0.0
    for i, c in enumerate(cfg.concepts):
        where = f"Concept {c.id.strip() or i + 1}"
        check_id(c.id, "concepts", i, where)
        if not normalize(c.label):
            add("error", "concepts", i, "label", where, "Describe what this concept credits.")
        if not _finite(c.weight) or c.weight < 0:
            weights_valid = False
            add("error", "concepts", i, "weight", where, "Weight must be a non-negative number.")
        else:
            total_weight += c.weight
            if c.weight == 0:
                add("warning", "concepts", i, "weight", where, "Weight is zero, so this concept earns no credit.")

        exprs = [normalize(e) for e in c.expressions if normalize(e)]
        if not exprs:
            add("error", "concepts", i, "expressions", where, "Add at least one accepted expression.")
        elif len(set(exprs)) < len(exprs):
            add("warning", "concepts", i, "expressions", where, "Some accepted expressions are duplicates.")

        if not c.clauses:
            add("warning", "concepts", i, "clauses", where,
                "No approved clause patterns: matches can never be confirmed automatically "
                "and will always need teacher review.")
        else:
            check_clauses_contain(c.clauses, c.expressions, "concepts", i, where, "accepted expressions")
        check_markers(c.expressions, "concepts", i, "expressions", where, "Accepted expression")
        check_markers(c.clauses, "concepts", i, "clauses", where, "clause")

    if cfg.concepts and weights_valid and total_weight <= 0:
        add("error", "concepts", None, "weight", "Rubric", "At least one concept must have a positive weight.")

    # An expression shared by several concepts needs explicit overlap permission.
    expr_owners = defaultdict(list)
    for i, c in enumerate(cfg.concepts):
        for e in {normalize(x) for x in c.expressions if normalize(x)}:
            expr_owners[e].append(i)
    for expr, owners in expr_owners.items():
        if len(owners) > 1 and not all(cfg.concepts[i].allow_overlap for i in owners):
            names = ", ".join(cfg.concepts[i].id.strip() or str(i + 1) for i in owners)
            for i in owners:
                add("warning", "concepts", i, "expressions", f"Concept {cfg.concepts[i].id.strip() or i + 1}",
                    f"Expression '{expr}' is shared by concepts {names}. Tick 'Allow overlap' on each "
                    "of them to permit double credit.")

    # --- Required items ------------------------------------------------------
    concept_ids = {c.id.strip() for c in cfg.concepts if c.id.strip()}
    linked_seen = defaultdict(list)
    for i, r in enumerate(cfg.required_items):
        where = f"Required item {r.id.strip() or i + 1}"
        check_id(r.id, "required_items", i, where)
        if r.kind not in KINDS:
            add("error", "required_items", i, "kind", where, "Choose a linked concept or a standalone phrase.")
        elif r.kind == "concept":
            if not r.concept_id:
                add("error", "required_items", i, "concept_id", where, "Select the concept this item requires.")
            elif r.concept_id not in concept_ids:
                add("error", "required_items", i, "concept_id", where,
                    f"Linked concept '{r.concept_id}' does not exist in this configuration.")
            else:
                linked_seen[r.concept_id].append(i)
            if r.phrases:
                add("error", "required_items", i, "phrases", where,
                    "A linked required item cannot also define standalone phrases.")
        else:
            if r.concept_id:
                add("error", "required_items", i, "concept_id", where,
                    "A standalone phrase item cannot also link to a concept.")
            if not any(normalize(p) for p in r.phrases):
                add("error", "required_items", i, "phrases", where, "Add at least one required phrase.")
            if not r.clauses:
                add("warning", "required_items", i, "clauses", where,
                    "No approved clause patterns: this item can never be confirmed automatically.")
            else:
                check_clauses_contain(r.clauses, r.phrases, "required_items", i, where, "required phrases")
            check_markers(r.phrases, "required_items", i, "phrases", where, "Required phrase")
            check_markers(r.clauses, "required_items", i, "clauses", where, "clause")

        if check_amount(r.absence_cap, "required_items", i, "absence_cap", where, "Absence cap") \
                and max_ok and r.absence_cap == max_mark:
            add("warning", "required_items", i, "absence_cap", where,
                "Absence cap equals the maximum mark, so it never restricts the score.")

    for cid, items in linked_seen.items():
        if len(items) > 1:
            for i in items:
                add("warning", "required_items", i, "concept_id",
                    f"Required item {cfg.required_items[i].id.strip() or i + 1}",
                    f"Concept '{cid}' is required by more than one item; only the lowest cap will matter.")

    # --- Wrong ideas ---------------------------------------------------------
    credit_clauses = {}
    for c in cfg.concepts:
        for cl in c.clauses:
            if normalize(cl):
                credit_clauses.setdefault(normalize(cl), f"concept {c.id.strip()}")
    for r in cfg.required_items:
        if r.kind == "phrase":
            for cl in r.clauses:
                if normalize(cl):
                    credit_clauses.setdefault(normalize(cl), f"required item {r.id.strip()}")
    credit_exprs = {normalize(e): c.id.strip() for c in cfg.concepts for e in c.expressions if normalize(e)}

    for i, w in enumerate(cfg.wrong_ideas):
        where = f"Wrong idea {w.id.strip() or i + 1}"
        check_id(w.id, "wrong_ideas", i, where)
        if not normalize(w.label):
            add("error", "wrong_ideas", i, "label", where, "Describe the misconception.")
        if not any(normalize(e) for e in w.expressions):
            add("error", "wrong_ideas", i, "expressions", where, "Add at least one trigger expression.")

        if w.action not in ACTIONS:
            add("error", "wrong_ideas", i, "action", where, "Choose exactly one action: cap, penalty or review only.")
        elif w.action == "review":
            if w.amount not in (None, 0, 0.0):
                add("error", "wrong_ideas", i, "amount", where, "Review-only rules have no mark deduction value.")
        else:
            label = "Cap" if w.action == "cap" else "Penalty"
            if w.amount is None:
                add("error", "wrong_ideas", i, "amount", where, f"Enter the {label.lower()} amount.")
            elif check_amount(w.amount, "wrong_ideas", i, "amount", where, label) and max_ok:
                if w.action == "cap" and w.amount == max_mark:
                    add("warning", "wrong_ideas", i, "amount", where,
                        "Cap equals the maximum mark, so it never restricts the score.")
                if w.action == "penalty" and w.amount == 0:
                    add("warning", "wrong_ideas", i, "amount", where, "A penalty of zero has no effect.")
            if not w.clauses:
                add("warning", "wrong_ideas", i, "clauses", where,
                    f"No confirming clause patterns: this misconception can never be confirmed, "
                    f"so its {label.lower()} will never apply automatically.")

        if w.clauses:
            check_clauses_contain(w.clauses, w.expressions, "wrong_ideas", i, where, "trigger expressions")
        check_markers(w.expressions, "wrong_ideas", i, "expressions", where, "Trigger expression")
        check_markers(w.clauses, "wrong_ideas", i, "clauses", where, "clause")

        for cl in w.clauses:
            owner = credit_clauses.get(normalize(cl))
            if owner:
                add("error", "wrong_ideas", i, "clauses", where,
                    f"Clause '{normalize(cl)}' is also an approved clause for {owner}. "
                    "A statement cannot be both credited and treated as a misconception.")
        for e in w.expressions:
            owner = credit_exprs.get(normalize(e))
            if owner:
                add("warning", "wrong_ideas", i, "expressions", where,
                    f"Trigger '{normalize(e)}' is also an accepted expression for concept {owner}; "
                    "only the clause patterns will tell them apart.")

    for item_id, owners in seen_ids.items():
        if len(owners) > 1:
            for section, index, where in owners:
                add("error", section, index, "id", where, f"ID '{item_id}' is used more than once in this rubric.")

    return issues
