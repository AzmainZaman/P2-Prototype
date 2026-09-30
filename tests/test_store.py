import json
import os
from pathlib import Path

import pytest

from grader.compare import summarize_changes
from grader.models import Configuration
from grader.store import NoChanges, Store, ValidationFailed, compute_hash

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "configs")
    s.ensure_seed(SEED_DIR)
    return s


def test_seed_is_saved_as_first_version(store):
    assert store.question_ids() == ["Q01"]
    v1 = store.latest("Q01")
    assert (v1.config_id, v1.version, v1.parent_config_id) == ("Q01-v1", 1, None)
    assert store.verify(v1)


def test_seed_runs_only_once(store):
    store.ensure_seed(SEED_DIR)
    assert len(store.versions("Q01")) == 1


def test_bangla_text_is_stored_readably(store):
    raw = (store.config_dir / "Q01-v1.json").read_text(encoding="utf-8")
    assert "হাইড্রোজেন" in raw


def test_saved_file_is_read_only(store):
    path = store.config_dir / "Q01-v1.json"
    assert not os.access(path, os.W_OK)


def test_edit_creates_new_version_and_keeps_original(store):
    v1 = store.latest("Q01")
    draft = v1.as_draft()
    draft.max_mark = 5.0
    draft.concepts[0].weight = 3.0
    draft.required_items[0].absence_cap = 3.0
    draft.wrong_ideas[0].amount = 1.0
    v2 = store.save_new_version(draft, parent_config_id=v1.config_id)

    assert (v2.config_id, v2.version, v2.parent_config_id) == ("Q01-v2", 2, "Q01-v1")
    reloaded_v1 = store.load("Q01-v1")
    assert reloaded_v1.max_mark == 10.0
    assert store.verify(reloaded_v1)
    assert v2.content_hash != v1.content_hash
    assert "Maximum mark changed" in summarize_changes(v1, v2)
    assert "Concept C1 edited" in summarize_changes(v1, v2)


def test_unchanged_draft_is_not_saved(store):
    v1 = store.latest("Q01")
    with pytest.raises(NoChanges):
        store.save_new_version(v1.as_draft(), parent_config_id=v1.config_id)


def test_invalid_draft_is_not_saved(store):
    draft = store.latest("Q01").as_draft()
    draft.max_mark = 0
    with pytest.raises(ValidationFailed):
        store.save_new_version(draft, parent_config_id="Q01-v1")
    assert len(store.versions("Q01")) == 1


def test_new_question_cannot_reuse_existing_id(store):
    draft = store.latest("Q01").as_draft()
    draft.prompt += " (copy)"
    with pytest.raises(ValidationFailed):
        store.save_new_version(draft)  # no parent -> treated as a brand-new question


def test_hash_ignores_save_metadata(store):
    v1 = store.latest("Q01")
    assert compute_hash(v1) == compute_hash(v1.as_draft())


def test_tampered_file_fails_verification(store):
    path = store.config_dir / "Q01-v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["max_mark"] = 20.0
    os.chmod(path, 0o644)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert not store.verify(store.load("Q01-v1"))


def test_next_question_id(store):
    assert store.next_question_id() == "Q02"


def test_round_trip(store):
    v1 = store.latest("Q01")
    assert Configuration.from_dict(v1.to_dict()) == v1
