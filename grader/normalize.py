"""Text normalization shared by validation and (later) the matcher (Report §4.5.2).

Only representational differences are removed: Unicode NFC, line endings and
incidental whitespace. Letters, vowel signs, negation words and punctuation are
preserved, and the original text is never overwritten.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List

_WHITESPACE = re.compile(r"\s+")


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def normalize(text: str) -> str:
    """Comparison view: NFC, unified line endings, collapsed whitespace."""
    text = nfc(text).replace("\r\n", "\n").replace("\r", "\n")
    return _WHITESPACE.sub(" ", text).strip()


def split_lines(text: str) -> List[str]:
    """One entry per non-empty line, as typed (outer whitespace trimmed)."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def code_points(text: str) -> int:
    return len(nfc(text))


# --- Tokens -------------------------------------------------------------------

# Bengali block letters, signs and digits (plus ZWNJ/ZWJ used inside conjuncts),
# or Latin letters and digits. Anything else that is not whitespace is a
# single punctuation token. The danda (U+0964) is outside the Bengali block,
# so it always separates.
_TOKEN = re.compile(r"[ঀ-৿‌‍]+|[A-Za-z0-9]+|[^\s]")
CLAUSE_END = {"।", "॥", "?", "!", ".", ";"}


@dataclass(frozen=True)
class Token:
    start: int  # offset in the original text
    end: int
    text: str  # NFC form used for comparison

    @property
    def is_punct(self) -> bool:
        return not _WORD_RE.fullmatch(self.text)


def tokenize(text: str) -> List[Token]:
    """Tokens with offsets into the original string, so matches can be highlighted there."""
    return [Token(m.start(), m.end(), nfc(m.group())) for m in _TOKEN.finditer(text or "")]


def comparison_tokens(text: str) -> List[str]:
    """Token texts with trailing clause punctuation removed, for exact clause comparison."""
    tokens = [t.text for t in tokenize(text)]
    while tokens and tokens[-1] in CLAUSE_END:
        tokens.pop()
    return tokens


# --- Negation, quotation and correction markers (Report §4.5.2) ---------------

# These indicate contexts that need checking; they do not prove negation.
_MARKER_WORDS = ["না", "নয়", "নেই", "নাই", "নি", "কখনোই", "ভুল", "বরং", "কিন্তু"]
NEGATION_MARKERS = sorted({nfc(w) for w in _MARKER_WORDS})
QUOTE_MARKS = {'"', "'", "“", "”", "‘", "’", "«", "»"}
MARKER_LIST_VERSION = "markers-v1"


def find_markers(text: str) -> List[str]:
    """Markers present in the text as whole tokens, in order of first appearance."""
    found: List[str] = []
    for token in tokenize(text):
        if (token.text in NEGATION_MARKERS or token.text in QUOTE_MARKS) and token.text not in found:
            found.append(token.text)
    return found
