"""Human-readable summary of what changed between two configuration versions."""
from __future__ import annotations

from typing import List

from .models import Configuration

_QUESTION_FIELDS = (
    ("domain", "Domain"),
    ("prompt", "Question prompt"),
    ("model_answer", "Model answer"),
    ("max_mark", "Maximum mark"),
    ("increment", "Mark increment"),
)
_SECTIONS = (
    ("concepts", "Concept"),
    ("required_items", "Required item"),
    ("wrong_ideas", "Wrong idea"),
)


def summarize_changes(old: Configuration, new: Configuration) -> List[str]:
    changes = []
    for attr, label in _QUESTION_FIELDS:
        if getattr(old, attr) != getattr(new, attr):
            changes.append(f"{label} changed")

    for attr, label in _SECTIONS:
        before = {item.id: item for item in getattr(old, attr)}
        after = {item.id: item for item in getattr(new, attr)}
        for item_id in after.keys() - before.keys():
            changes.append(f"{label} {item_id} added")
        for item_id in before.keys() - after.keys():
            changes.append(f"{label} {item_id} removed")
        for item_id in sorted(before.keys() & after.keys()):
            if before[item_id] != after[item_id]:
                changes.append(f"{label} {item_id} edited")
    return changes
