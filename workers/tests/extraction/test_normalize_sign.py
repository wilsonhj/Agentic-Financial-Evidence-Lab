"""Sign-parsing review regressions for ``parse_numeric`` (#410 / PR #443).

The first fix for #410 made a hyphen inside a word, a dash used as punctuation,
and several glued currency codes change meaning. The principle pinned here: a
sign is only ever read from text that supports it, and a genuinely ambiguous
sign raises ``ValueError`` instead of being guessed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from fel_workers.extraction.normalize import parse_numeric
from fel_workers.extraction.normalize.pipeline import normalize_payload

NBSP = " "
NNBSP = " "


@pytest.mark.parametrize(
    ("raw", "expected_value", "expected_scale"),
    [
        # A hyphen inside a word is not a sign (positive on base, raised on #443 head).
        ("pre-tax $100 million", Decimal("100"), 6),
        ("After-tax $100 million", Decimal("100"), 6),
        ("non-US $100", Decimal("100"), 0),
        ("ex-US $5", Decimal("5"), 0),
        ("pre-IPO $5 million", Decimal("5"), 6),
        ("co-op $100", Decimal("100"), 0),
        # A currency code can be the first word of a hyphenated label.
        ("USD-denominated $100 million", Decimal("100"), 6),
        ("EUR-denominated €100 million", Decimal("100"), 6),
        ("gbp–denominated £100 million", Decimal("100"), 6),
        # A dash used as punctuation after a label is not a minus (negative on #443 head).
        ("Revenue—$100 million", Decimal("100"), 6),
        ("Total–$100", Decimal("100"), 0),
        ("Revenue—100", Decimal("100"), 0),
        ("Revenue — $100 million", Decimal("100"), 6),
        ("Revenue— $100 million", Decimal("100"), 6),
        # A closed parenthetical before the number is not an open sign.
        ("(a) 100", Decimal("100"), 0),
        ("Note (b) 100", Decimal("100"), 0),
        ("Revenue (restated) $100 million", Decimal("100"), 6),
        # Glued ISO codes are recognised markers.
        ("USD100", Decimal("100"), 0),
        ("GBP100", Decimal("100"), 0),
        # Same as base: no sign in the text means positive.
        ("minus 100", Decimal("100"), 0),
        ("150 bps", Decimal("150"), 0),
        ("$5bn", Decimal("5"), 9),
        ("$ 100 million", Decimal("100"), 6),
    ],
)
def test_text_without_a_sign_stays_positive(
    raw: str, expected_value: Decimal, expected_scale: int
) -> None:
    value, scale, sign = parse_numeric(raw)
    assert (value, scale, sign) == (expected_value, expected_scale, "positive")


@pytest.mark.parametrize(
    ("raw", "expected_scale"),
    [
        ("-(100)", 0),
        ("−(100)", 0),
        ("-(100 million)", 6),
        ("-GBP100", 0),
        ("(EUR100)", 0),
        ("-USD100", 0),
        ("(US$100 million)", 6),
        # A currency marker can still be followed by a signed amount.
        ("USD-100", 0),
        ("GBP–100", 0),
        ("USD-denominated -$100 million", 6),
        # A dash is a minus at the start, or glued to "(" or to a currency marker there.
        ("–$100 million", 6),
        ("—100 million", 6),
        ("  –100", 0),
        ("$–100 million", 6),
        ("€–100 million", 6),
        ("(–100)", 0),
        ("Revenue (–100)", 0),
        # U+2212 is always a minus, even glued to a label.
        ("Revenue−100", 0),
        ("Revenue −$100 million", 6),
        # Spacing variants.
        (f"−{NBSP}100 million", 6),
        (f"({NBSP}100{NNBSP}million)", 6),
        # An ASCII hyphen set off by whitespace is a sign, as on base.
        ("Net loss -$100 million", 6),
    ],
)
def test_unambiguous_negative_forms(raw: str, expected_scale: int) -> None:
    value, scale, sign = parse_numeric(raw)
    assert (value, scale, sign) == (Decimal("-100"), expected_scale, "negative")


@pytest.mark.parametrize(
    "raw",
    [
        # Unknown token between a sign/"(" and the number: the sign cannot be
        # attached, so it fails closed whatever the token's length.
        "-Euro 100",
        "-Euro100",
        "-kr 100 million",
        "(kr 100 million)",
        "-Fr. 100",
        "(Fr. 100)",
        "(approx. 100)",
        "+Euro 100",
        # En/em dash spaced before and glued after a label: a minus or punctuation?
        "Assets –$1,000",
        "Net sales —$100 million",
        "Revenue –100",
        # A sign or "(" glued to a word and to the digits: hyphen, range or minus?
        "pre-100",
        "Revenue(100)",
        # Existing fail-closed behaviour is unchanged.
        "$10–$20 million",
        "10-20%",
        "year-over-year",
        "Q4-2024",
        "-€1,23",
        "",
    ],
)
def test_ambiguous_or_unreadable_sign_raises(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_numeric(raw)


@pytest.mark.parametrize(
    ("raw_value", "currency"),
    [("USD-denominated $100 million", "USD"), ("EUR-denominated €100 million", "EUR")],
)
def test_currency_code_label_in_raw_value_fallback(raw_value: str, currency: str) -> None:
    payload = {"kind": "kpi", "raw_value": raw_value, "unit": currency, "currency": currency}

    normalized, blockers = normalize_payload(payload)

    assert blockers == []
    assert normalized["raw_value"] == raw_value
    assert (normalized["value"], normalized["scale"], normalized["sign"]) == ("100", 6, "positive")
