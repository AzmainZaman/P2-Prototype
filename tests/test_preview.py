import pytest

from grader.normalize import comparison_tokens, find_markers, tokenize
from grader.preview import (CANDIDATE, CONFIRMED, NOT_DETECTED, UNCERTAIN, preview, review_needed,
                            segment_clauses)
from grader.validation import validate
from tests.test_validation import seed_config

# Student answers from Report Table 4.7.
CASE_A = "পানির একটি অণুতে দুটি হাইড্রোজেন পরমাণু থাকে। পানির একটি অণুতে একটি অক্সিজেন পরমাণু থাকে।"
CASE_B = "পানির একটি অণুতে দুটি হাইড্রোজেন পরমাণু থাকে।"
CASE_C = "প্রতিটি জল অণু গঠিত হয় হাইড্রোজেনের দুই পরমাণু ও অক্সিজেনের এক পরমাণু দিয়ে।"
CASE_D = "পানির একটি অণুতে তিনটি হাইড্রোজেন পরমাণু থাকে।"
CASE_E = "পানির একটি অণুতে তিনটি হাইড্রোজেন পরমাণু থাকে না।"


def states(answer):
    return {r.rule_id: r.state for r in preview(seed_config(), answer)}


# --- Markers ------------------------------------------------------------------

def test_markers_found_as_whole_tokens_only():
    assert find_markers("এটি সঠিক নয়।") == ["নয়"]
    assert find_markers("নানা রকম অণু") == []  # 'না' inside a longer word is not a marker
    assert find_markers("নিয়ম") == []


def test_marker_forms_are_equivalent():
    composed = "নয়".replace("য়", "য়")
    decomposed = "নয়".replace("য়", "য়")
    assert find_markers(composed) == find_markers(decomposed) == ["নয়"]
    assert find_markers("কিছু নেই") == ["নেই"]
    assert find_markers("কিছু নাই") == ["নাই"]


def test_quotation_marks_are_markers():
    assert find_markers("শিক্ষক বললেন “ভুল”") == ["“", "ভুল", "”"]


def test_validation_warns_on_marker_in_clause():
    cfg = seed_config()
    cfg.concepts[0].clauses = ["পানির একটি অণুতে দুটি হাইড্রোজেন পরমাণু থাকে না।"]
    msgs = [i.message for i in validate(cfg) if i.level == "warning" and i.section == "concepts"]
    assert any("marker 'না'" in m for m in msgs)


def test_seed_has_no_marker_warnings():
    assert not any("marker" in i.message for i in validate(seed_config()))


# --- Tokens and clauses -------------------------------------------------------

def test_tokens_keep_original_offsets():
    text = "পানির  অণু।"
    tokens = tokenize(text)
    assert [text[t.start:t.end] for t in tokens] == ["পানির", "অণু", "।"]


def test_clause_comparison_ignores_spacing_and_final_danda():
    assert comparison_tokens("পানির একটি অণুতে থাকে ।") == comparison_tokens("পানির  একটি অণুতে থাকে")


def test_segmentation_splits_on_danda_and_newline():
    clauses = segment_clauses("প্রথম বাক্য। দ্বিতীয় বাক্য\nতৃতীয় বাক্য")
    assert [c.words for c in clauses] == [["প্রথম", "বাক্য"], ["দ্বিতীয়", "বাক্য"], ["তৃতীয়", "বাক্য"]]


# --- Table 4.7 cases ----------------------------------------------------------

def test_case_a_complete():
    assert states(CASE_A) == {"C1": CONFIRMED, "C2": CONFIRMED, "R1": CONFIRMED, "W1": NOT_DETECTED}
    assert review_needed(preview(seed_config(), CASE_A)) == []


def test_case_b_partial():
    assert states(CASE_B) == {"C1": CONFIRMED, "C2": NOT_DETECTED, "R1": CONFIRMED, "W1": NOT_DETECTED}
    assert review_needed(preview(seed_config(), CASE_B)) == []


def test_case_c_unseen_paraphrase_is_not_asserted_absent():
    s = states(CASE_C)
    assert s["C1"] == s["C2"] == NOT_DETECTED
    results = preview(seed_config(), CASE_C)
    assert "does not prove" in next(r for r in results if r.rule_id == "C1").reason
    assert "Required item R1 not confirmed" in review_needed(results)


def test_case_d_configured_misconception_applies_cap():
    results = {r.rule_id: r for r in preview(seed_config(), CASE_D)}
    assert results["W1"].state == CONFIRMED
    assert results["W1"].effect == "Cap at 2 and review"
    assert results["R1"].effect == "Provisional cap 6 and review"


def test_case_e_negated_misconception_is_not_deducted():
    results = {r.rule_id: r for r in preview(seed_config(), CASE_E)}
    assert results["W1"].state == UNCERTAIN
    assert results["W1"].effect == "Review; no automatic deduction"
    assert results["C1"].state == NOT_DETECTED


def test_expression_outside_approved_clause_is_candidate():
    s = states("আমার মতে দুটি হাইড্রোজেন পরমাণু আছে।")
    assert s["C1"] == CANDIDATE
    assert s["R1"] == CANDIDATE


def test_spans_point_into_original_text():
    answer = "আমার মতে   দুটি  হাইড্রোজেন পরমাণু আছে।"
    c1 = next(r for r in preview(seed_config(), answer) if r.rule_id == "C1")
    (start, end), = c1.spans
    assert answer[start:end] == "দুটি  হাইড্রোজেন পরমাণু"


def test_repeated_clause_counts_once():
    s = states(CASE_B + " " + CASE_B)
    assert s["C1"] == CONFIRMED


@pytest.mark.parametrize("answer", ["", "   ", "।।"])
def test_empty_answers_detect_nothing(answer):
    assert set(states(answer).values()) == {NOT_DETECTED}
