"""Error text reaching durable columns must not carry secrets or filing content."""

from __future__ import annotations

import time

import pytest

from fel_workers.redact import MAX_ERROR_CHARS, redact_error_text, redact_job_error_text


@pytest.mark.parametrize(
    ("message", "secret"),
    [
        # The regression this module exists for: a keyed credential whose value
        # is preceded by a scheme word. A bare `\S+` value consumes only
        # "Bearer" and leaves the token in the clear.
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ("authorization: Bearer sk-live-SECRET", "sk-live-SECRET"),
        ("Authorization=Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        ("Bearer sk-live-SECRET", "sk-live-SECRET"),
        ("api_key=SECRET123", "SECRET123"),
        ("API-Key: SECRET123", "SECRET123"),
        ("password: hunter2", "hunter2"),
        ("token=abc123", "abc123"),
    ],
)
def test_credentials_never_survive(message: str, secret: str) -> None:
    assert secret not in redact_error_text(message)


@pytest.mark.parametrize(
    ("message", "content"),
    [
        # Normalizer/validator errors interpolate the offending value with
        # {value!r}, so the quoted run is a slice of a filing. No keyword rule
        # catches that -- only a positional one.
        ("cannot normalize raw_value 'ACME reported ARR of $4.2M'", "ACME reported"),
        ('bad value "confidential filing text"', "confidential filing"),
    ],
)
def test_quoted_document_content_never_survives(message: str, content: str) -> None:
    assert content not in redact_error_text(message)


def test_ordinary_diagnostics_stay_readable() -> None:
    """Redaction must not destroy the operational value of the message."""
    msg = "stage classify failed: provider timeout after 30s"
    assert redact_error_text(msg) == msg


def test_length_is_capped() -> None:
    assert len(redact_error_text("x" * 5000)) <= MAX_ERROR_CHARS


def test_whitespace_is_collapsed() -> None:
    assert redact_error_text("a\n\n  b\tc") == "a b c"


@pytest.mark.parametrize(
    ("message", "secret"),
    [
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ("{'api_key': 'sk-live-SECRET', 'ticker': 'CRM'}", "sk-live-SECRET"),
        ('{"token": "SECRET123", "accession": "0001-25-000001"}', "SECRET123"),
        ("password=hunter2", "hunter2"),
        ("FEL_OPENAI_API_KEY=sk-live-abcdef", "sk-live-abcdef"),
        ("access_token=top-secret", "top-secret"),
        ("client_secret=top-secret", "top-secret"),
        ("{'api_key': b'sk-bytes-secret'}", "sk-bytes-secret"),
        ('api_key="secret with spaces"', "secret with spaces"),
        ("api_key='abc def'", "abc def"),
        ("{'api_key': \"abc'def\"}", "abc'def"),
        ('{"api_key": "abc\\"def"}', 'abc\\"def'),
    ],
)
def test_job_error_credentials_never_survive(message: str, secret: str) -> None:
    assert secret not in redact_job_error_text(message)


def test_job_error_keeps_quoted_operational_identifiers() -> None:
    message = "unknown job kind 'sec_filing_fetch' for ticker 'CRM' accession '0001-25-000001'"

    assert redact_job_error_text(message) == message


def test_job_error_is_collapsed_and_capped() -> None:
    cleaned = redact_job_error_text("ticker 'CRM'\n\n" + "x" * 5000)

    assert "\n" not in cleaned
    assert "ticker 'CRM'" in cleaned
    assert len(cleaned) <= MAX_ERROR_CHARS


_URL_USERINFO_CASES = [
    ("connect failed postgres://svc:p4ss-FAKE@db.internal:5432/fel", "p4ss-FAKE"),
    ("postgresql+psycopg://svc:p4ss-FAKE@db/fel?sslmode=require", "p4ss-FAKE"),
    ("redis://:p4ss-FAKE@cache:6379/0", "p4ss-FAKE"),
    ("amqps://guest:p4ss-FAKE@mq.example.invalid/vhost", "p4ss-FAKE"),
    ("GET https://user:p4ss-FAKE@host.example.invalid/x failed", "p4ss-FAKE"),
]

_AUTH_HEADER_CASES = [
    ("Authorization: Token abc123-FAKE", "abc123-FAKE"),
    ("authorization=ApiKey abc123-FAKE", "abc123-FAKE"),
    ("Authorization: Negotiate abc123-FAKE", "abc123-FAKE"),
    ("{'Authorization': 'Token abc123-FAKE'}", "abc123-FAKE"),
    ("Authorization: Bearer abc123-FAKE", "abc123-FAKE"),
]


@pytest.mark.parametrize(("message", "secret"), _URL_USERINFO_CASES)
def test_url_userinfo_credentials_are_masked(message: str, secret: str) -> None:
    assert secret not in redact_error_text(message)
    assert secret not in redact_job_error_text(message)


@pytest.mark.parametrize(("message", "secret"), _AUTH_HEADER_CASES)
def test_authorization_header_credential_is_masked_for_any_scheme(
    message: str, secret: str
) -> None:
    assert secret not in redact_error_text(message)
    assert secret not in redact_job_error_text(message)


def test_url_without_userinfo_keeps_host_and_path() -> None:
    message = "fetch https://www.sec.gov/Archives/edgar/data/1/x.htm failed"

    assert redact_job_error_text(message) == message


# Inputs the pre-#445 sanitizer already masked: widening the Authorization rule
# must never leave more of the header value visible than before.
_AUTH_VALUE_REGRESSION_CASES = [
    ('{\'Authorization\': \'Digest username="alice", nonce="FAKENONCE", response="FAKERESP"\'}'),
    (
        '{"Authorization": "Digest username=\\"alice\\", nonce=\\"FAKENONCE\\", '
        'response=\\"FAKERESP\\""}'
    ),
    ("{'Authorization': 'Token abc FAKESECRET'}"),
    ("{'Authorization': 'Negotiate FAKEA FAKESECRET'}"),
    ('{"Authorization": "Token abc FAKESECRET"}'),
    ("Authorization: Digest username=alice, nonce=FAKENONCE, response=FAKERESP"),
    ("headers={'authorization': 'Token abc FAKESECRET'} while retrying"),
]


@pytest.mark.parametrize("message", _AUTH_VALUE_REGRESSION_CASES)
def test_authorization_value_is_masked_through_its_end(message: str) -> None:
    for sanitize in (redact_error_text, redact_job_error_text):
        out = sanitize(message)
        for secret in ("FAKENONCE", "FAKERESP", "FAKESECRET", "FAKEA"):
            assert secret not in out, (sanitize.__name__, out)


def test_text_after_a_quoted_authorization_value_is_kept() -> None:
    out = redact_job_error_text("{'Authorization': 'Token abc FAKESECRET', 'retry': 3} failed")

    assert "FAKESECRET" not in out
    assert "retry" in out
    assert out.endswith("failed")


@pytest.mark.parametrize(
    "message",
    [
        "a+" * 100_000 + "://",
        "a" * 200_000 + "://",
        "x://" * 50_000,
        "http://" + "a" * 200_000,
        "Authorization: " + "a" * 200_000,
        "Authorization:" + " " * 200_000 + "x",
    ],
    ids=["plus-run", "long-scheme", "repeated-scheme", "long-userinfo", "long-auth", "auth-spaces"],
)
def test_redaction_runs_in_linear_time_on_adversarial_input(message: str) -> None:
    started = time.perf_counter()
    redact_error_text(message)
    redact_job_error_text(message)

    assert time.perf_counter() - started < 1.0


def test_long_scheme_userinfo_is_still_masked() -> None:
    out = redact_job_error_text("a" * 40 + "://user:FAKEPW@host/x")

    assert "FAKEPW" not in out
