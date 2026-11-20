"""iXBRL unit parsing: ``xbrli:divide`` and multi-measure units (issue #411).

A per-share unit (``iso4217:USD`` over ``xbrli:shares``) used to collapse to
its last ``xbrli:measure`` (``shares``), so EPS and dividends-per-share facts
were stored with the wrong unit. These tests pin the composed representation:
``<numerator>/<denominator>`` with ``*`` joining several measures on one side.
"""

from __future__ import annotations

from datetime import date

import pytest

from fel_workers.ingestion.errors import ReasonCode
from fel_workers.ingestion.parser import ParseError, parse_filing
from fel_workers.ingestion.xbrl import map_unit, normalize_facts

ENTITY = "00000000-0000-4000-8000-0000000000e1"
VERSION = "00000000-0000-4000-8000-0000000000d1"


def _filing(units_xml: str, unit_ref: str = "u") -> bytes:
    return f"""<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
 xmlns:xbrli="http://www.xbrl.org/2003/instance">
<body>
<div style="display:none"><ix:header><ix:resources>
<xbrli:context id="c1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity>
<xbrli:period><xbrli:startDate>2027-01-01</xbrli:startDate><xbrli:endDate>2027-03-31</xbrli:endDate></xbrli:period></xbrli:context>
{units_xml}
</ix:resources></ix:header></div>
<h1>Units</h1>
<p>Diluted EPS was <ix:nonFraction name="us-gaap:EarningsPerShareDiluted"
 contextRef="c1" unitRef="{unit_ref}" decimals="2">1.25</ix:nonFraction>.</p>
</body></html>""".encode()


def _unit(units_xml: str) -> str:
    return parse_filing(_filing(units_xml)).units["u"]


def test_divide_unit_keeps_numerator_and_denominator() -> None:
    unit = _unit(
        '<xbrli:unit id="u"><xbrli:divide>'
        "<xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>"
        "<xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator>"
        "</xbrli:divide></xbrli:unit>"
    )
    assert unit == "iso4217:USD/xbrli:shares"
    assert map_unit(unit) == "USD/shares"


def test_divide_unit_reaches_normalized_fact() -> None:
    parsed = parse_filing(
        _filing(
            '<xbrli:unit id="u"><xbrli:divide>'
            "<xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>"
            "<xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure>"
            "</xbrli:unitDenominator></xbrli:divide></xbrli:unit>"
        )
    )
    (fact,) = normalize_facts(parsed, entity_id=ENTITY, document_version_id=VERSION)
    assert fact.unit == "USD/shares"
    assert fact.value == "1.25"
    assert fact.period_end == date(2027, 3, 31)


@pytest.mark.parametrize(
    ("measure", "stored", "mapped"),
    [
        ("iso4217:USD", "iso4217:USD", "USD"),
        ("xbrli:shares", "xbrli:shares", "shares"),
        ("xbrli:pure", "xbrli:pure", "pure"),
    ],
)
def test_single_measure_unit_is_unchanged(measure: str, stored: str, mapped: str) -> None:
    unit = _unit(f'<xbrli:unit id="u"><xbrli:measure>{measure}</xbrli:measure></xbrli:unit>')
    assert unit == stored
    assert map_unit(unit) == mapped


def test_multi_measure_multiply_unit_is_joined_deterministically() -> None:
    forward = _unit(
        '<xbrli:unit id="u"><xbrli:measure>iso4217:USD</xbrli:measure>'
        "<xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unit>"
    )
    reverse = _unit(
        '<xbrli:unit id="u"><xbrli:measure>xbrli:shares</xbrli:measure>'
        "<xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>"
    )
    assert forward == reverse == "iso4217:USD*xbrli:shares"
    assert map_unit(forward) == "USD*shares"


def test_multi_measure_numerator_and_denominator() -> None:
    unit = _unit(
        '<xbrli:unit id="u"><xbrli:divide><xbrli:unitNumerator>'
        "<xbrli:measure>iso4217:USD</xbrli:measure><xbrli:measure>ns:Barrel</xbrli:measure>"
        "</xbrli:unitNumerator><xbrli:unitDenominator>"
        "<xbrli:measure>xbrli:shares</xbrli:measure><xbrli:measure>ns:Year</xbrli:measure>"
        "</xbrli:unitDenominator></xbrli:divide></xbrli:unit>"
    )
    assert unit == "iso4217:USD*ns:Barrel/ns:Year*xbrli:shares"
    assert map_unit(unit) == "USD*ns:Barrel/ns:Year*shares"


def test_namespaced_custom_measures_pass_through() -> None:
    unit = _unit(
        '<xbrli:unit id="u"><xbrli:divide>'
        "<xbrli:unitNumerator><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unitNumerator>"
        "<xbrli:unitDenominator><xbrli:measure>acme:Widget</xbrli:measure></xbrli:unitDenominator>"
        "</xbrli:divide></xbrli:unit>"
    )
    assert unit == "iso4217:EUR/acme:Widget"
    assert map_unit(unit) == "EUR/acme:Widget"


def test_divide_does_not_leak_into_next_unit() -> None:
    parsed = parse_filing(
        _filing(
            '<xbrli:unit id="u"><xbrli:divide>'
            "<xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>"
            "<xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure>"
            "</xbrli:unitDenominator></xbrli:divide></xbrli:unit>"
            '<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
        )
    )
    assert parsed.units == {"u": "iso4217:USD/xbrli:shares", "usd": "iso4217:USD"}


@pytest.mark.parametrize(
    "body",
    [
        # Missing denominator.
        "<xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure>"
        "</xbrli:unitNumerator></xbrli:divide>",
        # Missing numerator.
        "<xbrli:divide><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure>"
        "</xbrli:unitDenominator></xbrli:divide>",
        # Empty denominator.
        "<xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure>"
        "</xbrli:unitNumerator><xbrli:unitDenominator></xbrli:unitDenominator></xbrli:divide>",
        # Empty divide.
        "<xbrli:divide></xbrli:divide>",
        # Measure directly inside a divide.
        "<xbrli:divide><xbrli:measure>iso4217:USD</xbrli:measure>"
        "<xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator>"
        "<xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure>"
        "</xbrli:unitDenominator></xbrli:divide>",
        # A divide mixed with a top-level measure.
        "<xbrli:measure>iso4217:USD</xbrli:measure><xbrli:divide><xbrli:unitNumerator>"
        "<xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator>"
        "<xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide>",
        # Two numerators.
        "<xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure>"
        "</xbrli:unitNumerator><xbrli:unitNumerator><xbrli:measure>iso4217:EUR</xbrli:measure>"
        "</xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure>"
        "</xbrli:unitDenominator></xbrli:divide>",
    ],
)
def test_malformed_divide_is_rejected_not_collapsed(body: str) -> None:
    with pytest.raises(ParseError) as excinfo:
        parse_filing(_filing(f'<xbrli:unit id="u">{body}</xbrli:unit>'))
    assert excinfo.value.reason_code == ReasonCode.UNKNOWN_UNIT
