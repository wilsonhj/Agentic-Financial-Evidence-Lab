"""Decimal numeric normalization helpers (no float math)."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Magnitude suffix -> decimal exponent. Filing conventions, not SI: 'M' and the
# accounting doubled 'MM' both mean millions, 'B'/'bn' billions, 'tn' trillions.
# Lookup is case-folded, so 'M' and 'm' are the same key — there is no
# SI-style m=milli here, and a lowercase 'b' is still billions.
#
# Deliberately absent: a bare 't' (tons/tonnes are a real filing unit), and
# 'bps' / 'basis points' / 'months' / 'mo' — those are rejected by the word
# boundary below rather than by omission alone, because their first letter is
# 'b' or 'm'.
_SCALE_SUFFIX = {
    "k": 3,
    "thousand": 3,
    "m": 6,
    "mm": 6,
    "mn": 6,
    "million": 6,
    "b": 9,
    "bn": 9,
    "billion": 9,
    "tn": 12,
    "trillion": 12,
}

# Longest-first alternation: 'million' must win over 'mm'/'mn'/'m', and 'mm'
# over 'm', or the regex would stop after one character and drop the exponent
# ('$4.2bn' -> scale 0).
_SUFFIX_ALTERNATION = "trillion|billion|million|thousand|mm|mn|bn|tn|[kmb]"

# The grouped alternative requires at least one ',\d{3}' so it can never win on
# a bare digit run and truncate it ('4200000' -> '420'). The suffix is anchored
# with a word boundary so unit words keep their own meaning ('150 bps' is not
# 150 billion, '18 months' is not 18 million). The trailing backreference
# lookahead rejects ratio notation, where the suffix letter is a period label
# and not a magnitude: 'm/m' is month-over-month, not millions. It is keyed on
# the *same* token repeating after the slash, so a genuine per-unit rate
# ('$5bn/yr') keeps its exponent. A parenthesized amount is accounting notation
# for a negative; the closing paren may sit before or after the suffix.
_NUM_RE = re.compile(
    r"(?P<lead>[-+\u2212])?\s*"
    r"(?P<open>\()?\s*"
    r"(?P<sign>[-+\u2212])?\s*"
    r"(?P<body>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"(?P<close_bare>\s*\))?"
    rf"(?:\s*(?P<suffix>{_SUFFIX_ALTERNATION})s?\b(?!/(?P=suffix)))?"
    r"(?P<close_suffixed>\s*\))?",
    re.IGNORECASE,
)

# Currency and percent markers that may sit around the digits. They carry no
# magnitude or sign of their own, so they are removed before the match; leaving
# them in made '-EUR100' / '(US$100)' match only '100' and drop the sign into
# the discarded prefix (issue #410). Prefixed dollars come first so 'US$' is
# consumed whole. Letters around a code are checked with letter-only
# lookarounds, not '\b': '\b' does not fire between a letter and a digit, so
# '-GBP100' / '(EUR100)' would otherwise keep their code, while a longer word
# ('Euro', 'cadence') still never loses a fragment. Codes in compound labels
# ('USD-denominated', 'gbp–denominated', 'non-USD', 'non–USD') keep the letters
# that make the hyphen or dash part of a word. A code glued to the digits still
# counts as part of the amount.
_NOT_AFTER_LETTER = r"(?<![^\W\d_])"
_ISO_CURRENCY_CODE = r"(?:USD|EUR|GBP|JPY|CAD|AUD|CHF|CNY|RMB|INR)"
_HYPHEN_OR_DASH = r"[-\u2012-\u2014]"
_CURRENCY_MARKER_RE = re.compile(
    rf"(?:{_NOT_AFTER_LETTER}(?:US|CA|C|AU|A|HK|NZ|S)\$|[$\u20ac\u00a3\u00a5\u20b9\u20a9%]"
    rf"|{_NOT_AFTER_LETTER}(?:(?<![^\W\d_]{_HYPHEN_OR_DASH}){_ISO_CURRENCY_CODE}"
    rf"(?!{_HYPHEN_OR_DASH}?[^\W\d_])"
    rf"|{_ISO_CURRENCY_CODE}(?=\.?\d)))+",
    re.IGNORECASE,
)

# U+2212 MINUS SIGN is always a minus, even glued to a label: it is not used to
# hyphenate words. ASCII '-' and '+' are signs only when they are not part of a
# word (not preceded by a word character): 'pre-tax' has no sign.
_MINUS_SIGN = "\u2212"
_MINUS_CHARS = frozenset("-" + _MINUS_SIGN)
_SIGN_CHARS = frozenset("-+" + _MINUS_SIGN)

# Figure/en/em dashes are written as a minus in filings but also double as
# sentence punctuation ('Revenue\u2014$100 million'). One is a minus only where
# nothing could be a label in front of it: at the start of the text (after
# optional whitespace and currency marker) or directly after '(', and glued to
# what follows. A dash that follows other text stays punctuation (the value stays
# positive, as before #410), except the one shape that reads both ways, see
# _normalize_dashes.
_PUNCT_DASHES = "\u2012\u2013\u2014"
_DASH_FOLLOWED_BY_NUMBER_RE = re.compile(r"\d|\.\d")

_WORD_CHAR_RE = re.compile(r"\w")

# A grouping/decimal separator touching the matched body means the match only
# covered part of a malformed number ('1,23' -> '1').
_ADJACENT_GROUPING = frozenset({",", "."})


def _remove_currency_markers(match: re.Match[str]) -> str:
    # Keep numeric fragments apart. Full consumption will reject a second
    # number in "100€200" or "100%200" instead of accepting the concatenated value.
    before = match.string[max(0, match.start() - 1) : match.start()]
    after = match.string[match.end() : match.end() + 1]
    if (before.isdecimal() or before in _ADJACENT_GROUPING) and (
        after.isdecimal() or after in _ADJACENT_GROUPING
    ):
        return " "
    return ""


def _is_word_char(char: str) -> bool:
    return _WORD_CHAR_RE.match(char) is not None


def _normalize_dashes(raw_value: str, text: str) -> str:
    """Turn the dashes that are unambiguously a minus into '-'; raise on the ambiguous one.

    A dash that is set off by whitespace before it and glued to a figure after it
    ('Assets \u2013$1,000', 'Revenue \u2013100') has the typographic shape of a minus
    but also of a careless punctuation dash. The sign cannot be read either way
    without guessing, and guessing wrong silently flips a loss, so it raises.
    """
    out: list[str] = []
    for index, char in enumerate(text):
        if char not in _PUNCT_DASHES:
            out.append(char)
            continue
        before = text[:index]
        glued = index + 1 < len(text) and not text[index + 1].isspace()
        if glued and (not before.strip() or before.endswith("(")):
            out.append("-")
            continue
        if glued and before[-1:].isspace() and _DASH_FOLLOWED_BY_NUMBER_RE.match(text, index + 1):
            raise ValueError(
                f"raw_value has a dash that could be a minus sign or punctuation: " f"{raw_value!r}"
            )
        out.append(char)
    return "".join(out)


def _dangling_sign_index(prefix: str) -> int | None:
    """Index of the last standalone sign or still-open '(' in ``prefix``, if any."""
    for index in range(len(prefix) - 1, -1, -1):
        char = prefix[index]
        if char != "(" and char not in _SIGN_CHARS:
            continue
        if char != _MINUS_SIGN and index > 0 and _is_word_char(prefix[index - 1]):
            continue  # part of a word: 'pre-tax', 'f(x)'
        if char == "(" and ")" in prefix[index + 1 :]:
            continue  # a closed parenthetical, '(a) 100', is not an open sign
        return index
    return None


def _require_sign_attached(raw_value: str, cleaned: str, match: re.Match[str]) -> None:
    """Fail closed when a sign or '(' cannot be tied to the number it precedes.

    A standalone sign/'(' in front of the number may only be separated from it by
    whitespace (currency markers are already removed). Anything else between them
    ('-Euro 100', '-kr 100', '(Fr. 100)') is a token we do not recognise that may
    carry the sign, so we raise instead of dropping the sign. There is no length
    limit on that token. A sign or '(' glued to a word and directly to the digits
    ('pre-100', 'Revenue(100)') could be a hyphen, a range or a minus; it raises.
    """
    group_starts = [
        match.start(name) for name in ("lead", "open", "sign") if match.group(name) is not None
    ]
    if group_starts:
        first = min(group_starts)
        if first > 0 and cleaned[first] != _MINUS_SIGN and _is_word_char(cleaned[first - 1]):
            raise ValueError(
                f"raw_value has a sign or parenthesis glued to a word and its number: "
                f"{raw_value!r}"
            )
    prefix = cleaned[: match.start()]
    dangling = _dangling_sign_index(prefix)
    if dangling is not None and prefix[dangling + 1 :].strip():
        raise ValueError(
            f"raw_value has a sign or parenthesis that could not be attached "
            f"to its number: {raw_value!r} (read only {cleaned[match.start() : match.end()]!r})"
        )


def _require_full_consumption(raw_value: str, cleaned: str, match: re.Match[str]) -> None:
    """Fail closed unless the match covered the whole numeric portion of the text.

    ``re.search`` happily returns the first token it can parse and discards the
    rest, which silently reports a wrong order of magnitude: '12,34,567' becomes
    12, '$ 1 234 567' becomes 1, '1e6' becomes 1. Those are the same class of
    defect as '4200000' -> '420'. A number we cannot read in full is never
    guessed at — the caller gets a ValueError and the candidate is dropped
    rather than persisted with a wrong magnitude.
    """
    leftover = cleaned[: match.start()] + cleaned[match.end() :]
    _require_sign_attached(raw_value, cleaned, match)
    if any(char.isdigit() for char in leftover):
        raise ValueError(
            f"raw_value has an unconsumed numeric remainder: {raw_value!r} "
            f"(read only {cleaned[match.start() : match.end()]!r})"
        )
    body_start, body_end = match.span("body")
    before = cleaned[body_start - 1] if body_start > 0 else ""
    after = cleaned[body_end] if body_end < len(cleaned) else ""
    if before in _ADJACENT_GROUPING or after in _ADJACENT_GROUPING:
        raise ValueError(
            f"raw_value has a malformed grouped number: {raw_value!r} "
            f"(read only {match.group('body')!r})"
        )


def parse_numeric(raw_value: str) -> tuple[Decimal, int, str]:
    """Parse raw numeric text into (value, scale, sign). Keeps Decimal only.

    ``value`` is the mantissa exactly as written and ``scale`` its decimal
    exponent, which is the mantissa + exponent convention the frozen
    ``extraction-payload/v1`` contract stores (its own reference fixture is
    ``{"raw_value": "$100 million", "value": "100", "scale": 6}``).
    ``normalize_payload`` carries the pair through; it never collapses it.

    Raises ``ValueError`` when the text cannot be read in full — see
    ``_require_full_consumption``.
    """
    if not raw_value or not isinstance(raw_value, str):
        raise ValueError("raw_value required")
    cleaned = _CURRENCY_MARKER_RE.sub(_remove_currency_markers, raw_value).strip()
    cleaned = _normalize_dashes(raw_value, cleaned)
    match = _NUM_RE.search(cleaned)
    if match is None:
        raise ValueError(f"no numeric token in raw_value: {raw_value!r}")
    _require_full_consumption(raw_value, cleaned, match)
    body = match.group("body").replace(",", "")
    try:
        value = Decimal(body)
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal: {body!r}") from exc
    scale = 0
    suffix = match.group("suffix")
    if suffix:
        scale = _SCALE_SUFFIX[suffix.lower()]
    negated = any(
        match.group(name) in _MINUS_CHARS for name in ("lead", "sign") if match.group(name)
    )
    parenthesized = match.group("open") is not None and (
        match.group("close_bare") is not None or match.group("close_suffixed") is not None
    )
    if negated or parenthesized:
        value = -abs(value)
    if value > 0:
        sign = "positive"
    elif value < 0:
        sign = "negative"
    else:
        sign = "zero"
    return value, scale, sign


def format_decimal(value: Decimal) -> str:
    """Normalize Decimal to a contract decimal-string (no exponent, no float)."""
    normalized = value.normalize() if value != 0 else Decimal("0")
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


__all__ = ["format_decimal", "parse_numeric"]
