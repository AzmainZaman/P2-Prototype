import json
import math
from pathlib import Path

import pytest

from grader.models import Concept, Configuration, RequiredItem, WrongIdea
from grader.validation import concept_shares, has_errors, validate

SEED = Path(__file__).resolve().parent.parent / "data" / "seed" / "Q01_water.json"


def seed_config() -> Configuration:
    return Configuration.from_dict(json.loads(SEED.read_text(encoding="utf-8")))


def errors(cfg, **kwargs):
    return [i for i in validate(cfg, **kwargs) if i.level == "error"]


def warnings(cfg, **kwargs):
    return [i for i in validate(cfg, **kwargs) if i.level == "warning"]


def fields_with_errors(cfg, **kwargs):
    return {(i.section, i.index, i.field) for i in errors(cfg, **kwargs)}


def test_seed_example_is_valid():
    assert not has_errors(validate(seed_config()))


def test_concept_shares_are_normalized():
    assert concept_shares(seed_config()) == [0.6, 0.4]


# --- Question and mark scale --------------------------------------------------

@pytest.mark.parametrize("qid", ["", "   ", "Q 01", "প্রশ্ন"])
def test_question_id_must_be_present_and_simple(qid):
    cfg = seed_config()
    cfg.question_id = qid
    assert ("question", None, "question_id") in fields_with_errors(cfg)


def test_new_question_id_must_not_already_exist():
    cfg = seed_config()
    assert ("question", None, "question_id") in fields_with_errors(cfg, existing_question_ids=["Q01"])
    # Saving a new version of an existing question is allowed.
    assert not errors(cfg, existing_question_ids=["Q01"], is_new_question=False)


@pytest.mark.parametrize("field", ["prompt", "model_answer"])
def test_prompt_and_model_answer_required(field):
    cfg = seed_config()
    setattr(cfg, field, "  \n ")
    assert ("question", None, field) in fields_with_errors(cfg)


def test_text_limit_is_enforced_without_truncation():
    cfg = seed_config()
    cfg.model_answer = "ক" * 2001
    assert ("question", None, "model_answer") in fields_with_errors(cfg)
    assert len(cfg.model_answer) == 2001


@pytest.mark.parametrize("max_mark", [0, -5, math.nan, math.inf])
def test_max_mark_must_be_positive_and_finite(max_mark):
    cfg = seed_config()
    cfg.max_mark = max_mark
    assert ("question", None, "max_mark") in fields_with_errors(cfg)


def test_max_mark_must_be_multiple_of_increment():
    cfg = seed_config()
    cfg.max_mark = 10.25
    assert ("question", None, "max_mark") in fields_with_errors(cfg)
    cfg.increment = 1.0
    cfg.max_mark = 10.5
    assert ("question", None, "max_mark") in fields_with_errors(cfg)


# --- Concepts -----------------------------------------------------------------

def test_at_least_one_concept():
    cfg = seed_config()
    cfg.concepts, cfg.required_items = [], []
    assert ("concepts", None, None) in fields_with_errors(cfg)


def test_negative_or_non_finite_weight_rejected():
    cfg = seed_config()
    cfg.concepts[0].weight = -1
    cfg.concepts[1].weight = math.nan
    found = fields_with_errors(cfg)
    assert ("concepts", 0, "weight") in found
    assert ("concepts", 1, "weight") in found


def test_zero_total_weight_rejected():
    cfg = seed_config()
    for c in cfg.concepts:
        c.weight = 0
    assert ("concepts", None, "weight") in fields_with_errors(cfg)
    assert concept_shares(cfg) == [None, None]


def test_concept_needs_label_and_expression():
    cfg = seed_config()
    cfg.concepts[0].label = ""
    cfg.concepts[0].expressions = ["  "]
    found = fields_with_errors(cfg)
    assert ("concepts", 0, "label") in found
    assert ("concepts", 0, "expressions") in found


def test_concept_without_clauses_is_a_warning_only():
    cfg = seed_config()
    cfg.concepts[0].clauses = []
    assert not errors(cfg)
    assert any(w.section == "concepts" and w.field == "clauses" for w in warnings(cfg))


def test_clause_that_contains_no_expression_warns():
    cfg = seed_config()
    cfg.concepts[1].clauses = ["পানিতে অক্সিজেন থাকে।"]
    assert any(w.index == 1 and w.field == "clauses" for w in warnings(cfg))


def test_duplicate_ids_across_sections_rejected():
    cfg = seed_config()
    cfg.wrong_ideas[0].id = "C1"
    found = fields_with_errors(cfg)
    assert ("concepts", 0, "id") in found
    assert ("wrong_ideas", 0, "id") in found


def test_shared_expression_warns_unless_overlap_allowed():
    cfg = seed_config()
    cfg.concepts[1].expressions.append("দুটি হাইড্রোজেন পরমাণু")
    assert any("shared by concepts" in w.message for w in warnings(cfg))
    for c in cfg.concepts:
        c.allow_overlap = True
    assert not any("shared by concepts" in w.message for w in warnings(cfg))


# --- Required items -----------------------------------------------------------

def test_required_item_must_link_existing_concept():
    cfg = seed_config()
    cfg.required_items[0].concept_id = "C9"
    assert ("required_items", 0, "concept_id") in fields_with_errors(cfg)
    cfg.required_items[0].concept_id = None
    assert ("required_items", 0, "concept_id") in fields_with_errors(cfg)


def test_required_item_uses_exactly_one_mode():
    cfg = seed_config()
    cfg.required_items[0].phrases = ["হাইড্রোজেন"]
    assert ("required_items", 0, "phrases") in fields_with_errors(cfg)

    phrase_item = RequiredItem(id="R2", kind="phrase", concept_id="C1", phrases=[], absence_cap=4)
    cfg = seed_config()
    cfg.required_items.append(phrase_item)
    found = fields_with_errors(cfg)
    assert ("required_items", 1, "concept_id") in found
    assert ("required_items", 1, "phrases") in found


@pytest.mark.parametrize("cap", [-1, 6.25, 11, math.nan])
def test_absence_cap_bounds(cap):
    cfg = seed_config()
    cfg.required_items[0].absence_cap = cap
    assert ("required_items", 0, "absence_cap") in fields_with_errors(cfg)


# --- Wrong ideas --------------------------------------------------------------

def test_review_only_rule_has_no_amount():
    cfg = seed_config()
    cfg.wrong_ideas[0].action = "review"
    cfg.wrong_ideas[0].amount = 2
    assert ("wrong_ideas", 0, "amount") in fields_with_errors(cfg)
    cfg.wrong_ideas[0].amount = None
    assert not errors(cfg)


@pytest.mark.parametrize("action", ["cap", "penalty"])
def test_cap_or_penalty_needs_valid_amount(action):
    cfg = seed_config()
    cfg.wrong_ideas[0].action = action
    cfg.wrong_ideas[0].amount = None
    assert ("wrong_ideas", 0, "amount") in fields_with_errors(cfg)
    cfg.wrong_ideas[0].amount = 1.25
    assert ("wrong_ideas", 0, "amount") in fields_with_errors(cfg)
    cfg.wrong_ideas[0].amount = 12
    assert ("wrong_ideas", 0, "amount") in fields_with_errors(cfg)


def test_unknown_action_rejected():
    cfg = seed_config()
    cfg.wrong_ideas[0].action = "delete"
    assert ("wrong_ideas", 0, "action") in fields_with_errors(cfg)


def test_clause_collision_between_concept_and_wrong_idea():
    cfg = seed_config()
    cfg.wrong_ideas[0].clauses.append(cfg.concepts[0].clauses[0])
    assert ("wrong_ideas", 0, "clauses") in fields_with_errors(cfg)


def test_clause_collision_detected_across_unicode_forms():
    # য় can be typed as one code point (U+09DF) or as য + nukta (U+09AF U+09BC).
    composed = "পানির অণু নয়।".replace("য়", "য়")
    decomposed = "পানির অণু নয়।".replace("য়", "য়")
    assert composed != decomposed
    cfg = Configuration(
        question_id="Q02", prompt="প্রশ্ন", model_answer="উত্তর",
        concepts=[Concept(id="C1", label="x", weight=1, expressions=["অণু"], clauses=[composed])],
        wrong_ideas=[WrongIdea(id="W1", label="y", expressions=["অণু"], clauses=[decomposed],
                               action="review")],
    )
    assert ("wrong_ideas", 0, "clauses") in fields_with_errors(cfg)


def test_extra_spaces_do_not_hide_collision():
    cfg = seed_config()
    cfg.wrong_ideas[0].clauses.append("  " + cfg.concepts[1].clauses[0].replace(" ", "   ") + " ")
    assert ("wrong_ideas", 0, "clauses") in fields_with_errors(cfg)
