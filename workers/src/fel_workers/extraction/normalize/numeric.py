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
    r"(?P<open>\()?\s*"
    r"(?P<sign>[-+])?\s*"
    r"(?P<body>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"(?P<close_bare>\s*\))?"
    rf"(?:\s*(?P<suffix>{_SUFFIX_ALTERNATION})s?\b(?!/(?P=suffix)))?"
    r"(?P<close_suffixed>\s*\))?",
    re.IGNORECASE,
)

# Currency markers that may sit between a sign (or opening paren) and the digits.
# They carry no magnitude or sign of their own, so they are removed before the
# match; leaving them in made '-EUR100' / '(US$100)' match only '100' and drop
# the sign into the discarded prefix (issue #410). Prefixed dollars come first so
# 'US$' is consumed whole. ISO codes need word boundaries so they never eat a
# fragment of a longer word.
_CURRENCY_MARKER_RE = re.compile(
    r"(?:US|CA|C|AU|A|HK|NZ|S)\$|[$\u20ac\u00a3\u00a5\u20b9\u20a9]"
    r"|\b(?:USD|EUR|GBP|JPY|CAD|AUD|CHF|CNY|RMB|INR)\b",
    re.IGNORECASE,
)

# U+2212 MINUS SIGN is always a minus. En/em dash and figure dash are also
# written as a minus in filings, but they double as sentence punctuation
# ('Revenue \u2014 $100 million'), so they count as a minus only when glued to
# what follows; a dash set off by whitespace stays punctuation.
_ALWAYS_MINUS_RE = re.compile("\u2212")
_GLUED_DASH_RE = re.compile(r"[\u2012\u2013\u2014](?=\S)")

# What is left in front of the match must not be able to carry a sign. A
# sign/open-paren followed by at most one short unrecognised token ('-kr 100',
# '(Fr. 100)') is a sign we could not attach to the number, so it fails closed.
_ORPHAN_SIGN_PREFIX_RE = re.compile(r"[-+(]\s*\S{0,3}\s*$")

# A grouping/decimal separator touching the matched body means the match only
# covered part of a malformed number ('1,23' -> '1').
_ADJACENT_GROUPING = frozenset({",", "."})


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
    if _ORPHAN_SIGN_PREFIX_RE.search(cleaned[: match.start()]):
        raise ValueError(
            f"raw_value has a sign or parenthesis that could not be attached "
            f"to its number: {raw_value!r} (read only {cleaned[match.start() : match.end()]!r})"
        )
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
    cleaned = _ALWAYS_MINUS_RE.sub("-", raw_value)
    cleaned = _GLUED_DASH_RE.sub("-", cleaned)
    cleaned = _CURRENCY_MARKER_RE.sub("", cleaned).replace("%", "").strip()
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
    explicit_sign = match.group("sign")
    parenthesized = match.group("open") is not None and (
        match.group("close_bare") is not None or match.group("close_suffixed") is not None
    )
    if explicit_sign == "-" or parenthesized:
        value = -abs(value)
    elif explicit_sign == "+":
        value = abs(value)
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
