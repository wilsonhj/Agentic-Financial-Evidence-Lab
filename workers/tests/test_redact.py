"""Error text reaching durable columns must not carry secrets or filing content."""

from __future__ import annotations

import os
import subprocess
import sys
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


# --- ReDoS regressions (#412 / PR #445) -------------------------------------
#
# Each case runs in a child interpreter with a hard wall-clock timeout, so a
# catastrophic pattern fails the test instead of hanging CI. The child times
# the public functions and the private pattern stage (which is not subject to
# the public input cap), so an uncapped quadratic or exponential pattern is
# caught even if the cap hides it.

_CHILD = """
import sys, time
from fel_workers import redact
text = sys.stdin.read()
t = time.perf_counter()
redact.redact_error_text(text)
redact.redact_job_error_text(text)
redact._mask_credentials(text)
redact._mask_credentials(text[:20000])
print(time.perf_counter() - t)
"""

_BACKSLASH_RUN = "\\a" * 5000

_ADVERSARIAL = {
    "single-quote-backslashes": "password='" + _BACKSLASH_RUN,
    "double-quote-backslashes": 'password="' + _BACKSLASH_RUN,
    "api-key-backslashes": "api_key='" + _BACKSLASH_RUN,
    "quoted-key-backslashes": "{'client_secret': '" + _BACKSLASH_RUN,
    "quoted-key-dq-backslashes": '{"token": "' + _BACKSLASH_RUN,
    "authorization-quoted-backslashes": "authorization='" + _BACKSLASH_RUN,
    "bare-quote-backslashes": "'" + _BACKSLASH_RUN,
    "escaped-quote-run": "password='" + "\\'" * 20000,
    "secret-dash-run": "secret-" * 20000,
    "password-dash-run": "password-" * 20000,
    "authorization-run": "authorization" * 20000,
    "token-underscore-run": "my_token_" * 20000,
    "quoted-key-run": '"secret-' * 20000,
    "mixed-200k": ("password='\\a\"secret-token=authorization \\" * 6000)[:200_000],
    "mixed-quotes-200k": ("api_key=\"\\a'\\\"token: 'x\\" * 8000)[:200_000],
    "userinfo-ats": "http://" + "a@" * 50_000,
    "bearer-spaces": "bearer" + " " * 200_000,
}


@pytest.mark.parametrize("message", list(_ADVERSARIAL.values()), ids=list(_ADVERSARIAL))
def test_redaction_is_linear_on_adversarial_input(message: str) -> None:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _CHILD],
            input=message,
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
            check=True,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("redaction did not finish within 20 s (catastrophic backtracking)")
    assert float(proc.stdout.strip()) < 1.0


@pytest.mark.parametrize(
    ("message", "secrets"),
    [
        ("password='abc\\'def SECRET1'", ["abc", "def", "SECRET1"]),
        ('password="abc\\"def SECRET1"', ["abc", "def", "SECRET1"]),
        ("{'api_key': 'a\\'b SECRET1', 'ok': 1}", ["SECRET1", "a\\'b"]),
        ('{"token": "a\\"b SECRET1"}', ["SECRET1"]),
        ("password='C:\\\\dir\\\\SECRET1\\'", ["SECRET1"]),
        ("password='a\\'SECRET1\\'", ["SECRET1"]),
        ("secret='x' then token='SECRET1'", ["SECRET1"]),
    ],
)
def test_escaped_quotes_inside_credential_values_are_fully_masked(
    message: str, secrets: list[str]
) -> None:
    for fn in (redact_error_text, redact_job_error_text):
        out = fn(message)
        for secret in secrets:
            assert secret not in out, (message, out)


def test_text_after_a_terminated_quoted_credential_is_kept() -> None:
    out = redact_job_error_text("password='a\\'b' while parsing row 7")

    assert "while parsing row 7" in out
    assert "password='a" not in out


def test_strict_policy_masks_escaped_quoted_literals() -> None:
    out = redact_error_text("bad value 'a\\'SECRET1' in row")

    assert "SECRET1" not in out
    assert "in row" in out


def test_oversized_input_is_capped_before_redaction() -> None:
    out = redact_job_error_text("password=SECRET1 " + "x" * 1_000_000)

    assert "SECRET1" not in out
    assert len(out) <= MAX_ERROR_CHARS


_STRADDLE_SECRETS = (
    "{'api_key': 'FAKESTRADDLE0123456789'}",
    '{"token": "FAKESTRADDLE0123456789"}',
    "postgres://svc:FAKESTRADDLE0123456789@db.internal.invalid/app",
    "password=FAKESTRADDLE0123456789",
)


@pytest.mark.parametrize("secret", _STRADDLE_SECRETS)
@pytest.mark.parametrize("redact", [redact_error_text, redact_job_error_text])
def test_secret_straddling_the_input_bound_is_not_partly_kept(redact, secret: str) -> None:
    """A secret cut by the input bound must not leave a visible prefix (#412, PR #445).

    Whitespace padding collapses to one space, which pulls text from near the
    bound into the stored message, so every cut offset inside the secret is tried.
    """
    from fel_workers.redact import MAX_INPUT_CHARS

    for inside in range(1, len(secret)):
        pad = MAX_INPUT_CHARS - 2 - inside
        out = redact("x" + " " * pad + " " + secret)
        assert "FAKE" not in out, (inside, out)


_MULTIWORD_STRADDLE = (
    "password='FAKEONE FAKETWO FAKETHREE' end",
    '{"api_key": "FAKEONE FAKETWO FAKETHREE"}',
    "{'client_secret': 'FAKEONE FAKETWO'} tail",
)


@pytest.mark.parametrize("secret", _MULTIWORD_STRADDLE)
@pytest.mark.parametrize("redact", [redact_error_text, redact_job_error_text])
def test_quoted_multiword_secret_cut_by_the_bound_leaks_no_word(redact, secret: str) -> None:
    """Dropping the cut tail back to a space can leave an unclosed quoted value (#412)."""
    from fel_workers.redact import MAX_INPUT_CHARS

    for inside in range(1, len(secret)):
        out = redact("E: " + " " * (MAX_INPUT_CHARS - 3 - inside) + secret)
        assert "FAKE" not in out, (inside, out)


@pytest.mark.parametrize(
    "message",
    [
        "failed: {'password': 'FAKEUNCLOSED",
        'failed: {"token": "FAKEUNCLOSED more words',
        "failed: password='FAKEUNCLOSED more",
        "failed: api_key=\"FAKEUNCLOSED",
    ],
)
@pytest.mark.parametrize("redact", [redact_error_text, redact_job_error_text])
def test_unterminated_quoted_credential_is_masked_to_line_end(redact, message: str) -> None:
    out = redact(message + "\nnext line kept")

    assert "FAKE" not in out
    assert "failed:" in out
    assert "next line kept" in out
