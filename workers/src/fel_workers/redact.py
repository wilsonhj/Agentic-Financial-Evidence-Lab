"""Sink-specific redaction for error text that reaches durable storage.

Two sinks record exception text: ``jobs.error`` (``queue.fail``) and
``extraction_run_steps.error`` (a failed stage record). They need different
policies. Extraction-step errors can contain quoted document values, so their
sanitizer masks every quoted literal. The generic queue also serves ingestion
jobs whose quoted job kinds, tickers, accessions and series IDs are important
to operators, so its sanitizer masks credential shapes without destroying
those identifiers. Queue callers must not interpolate arbitrary payloads.

This lives outside ``fel_workers.extraction`` on purpose: ``queue`` is generic
job infrastructure and must not import from a single job kind's package.

Two rules, both needed:

Both sanitizers collapse whitespace and cap stored text. Credential shapes
(``key=value``, mappings such as ``{'api_key': 'value'}``,
``Authorization: <scheme> <credential>``, ``Bearer <token>`` and URL
userinfo ``scheme://user:pass@host``) are masked in both. Only :func:`redact_error_text`, the
strict extraction-step policy, masks every quoted run positionally.
"""

from __future__ import annotations

import re

MAX_ERROR_CHARS = 256
_TRUNCATED = "...[truncated]"

_SENSITIVE_KEY = (
    r"[A-Za-z0-9_-]*(?:secret|api[_-]?key|password|passwd|token|authorization)" r"[A-Za-z0-9_-]*"
)

# Mapping/JSON reprs put a closing quote between the key and separator. Values
# may use the opposite quote, contain escaped delimiters, or carry a Python
# bytes/string prefix. Match the delimiter paired with itself instead of using
# ``[^'\"]*``, which leaked the suffix of values containing the other quote.
_QUOTED_CREDENTIAL_ASSIGNMENT = re.compile(
    rf"""
      (?P<key_quote>['"])
      {_SENSITIVE_KEY}
      (?P=key_quote)
      \s*[:=]\s*
      [bBrRuUfF]{{0,2}}
      (?P<value_quote>['"])
      (?:\\.|(?!(?P=value_quote)).)*
      (?P=value_quote)
    """,
    re.IGNORECASE | re.VERBOSE,
)
_BARE_CREDENTIAL_ASSIGNMENT = re.compile(
    rf"""
      \b{_SENSITIVE_KEY}\b
      \s*[:=]\s*
      (?:
        [bBrRuUfF]{{0,2}}
        (?P<bare_value_quote>['"])
        (?:\\.|(?!(?P=bare_value_quote)).)*
        (?P=bare_value_quote)
        |
        (?:(?:bearer|basic)\s+)?[^\s,;}}\]]+
      )
    """,
    re.IGNORECASE | re.VERBOSE,
)
_AUTH_SCHEME = re.compile(r"\b(?:bearer|basic)\s+\S+", re.IGNORECASE)
# ``Authorization: <scheme> <credential...>``: the whole header value is masked,
# not just its first token. A quoted value (mapping/JSON repr) runs to its
# paired closing quote, so multi-token credentials such as Digest parameters or
# ``Token abc SECRET`` are covered; an unquoted value runs to the end of the
# line. This runs before the generic key rules, which would consume only the
# scheme word.
_AUTHORIZATION_HEADER = re.compile(
    r"""
      \bauthorization\b['"]?\s*[:=]\s*
      (?:
        (?P<authz_quote>['"])
        (?:\\.|(?!(?P=authz_quote)).)*
        (?:(?P=authz_quote)|(?=[\r\n])|\Z)
        |
        [^\r\n]*
      )
    """,
    re.IGNORECASE | re.VERBOSE,
)
# ``scheme://user:pass@host`` for any scheme: mask the whole userinfo. The
# scheme length is bounded so each start position scans a constant window
# (no quadratic backtracking over long ``a+a+a+`` runs).
_URL_USERINFO = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]{0,31}://)[^\s/?#@]*@")
_QUOTED = re.compile(r"""(['"])(?:\\.|(?!\1).)*\1""")


def _mask_credentials(message: str) -> str:
    # Match quoted-key assignments first: the bare-key expression cannot cross
    # the closing quote between ``'api_key'`` and ``:``.
    text = _URL_USERINFO.sub(r"\g<scheme>[redacted]@", str(message))
    text = _AUTHORIZATION_HEADER.sub("[redacted]", text)
    text = _QUOTED_CREDENTIAL_ASSIGNMENT.sub("[redacted]", text)
    text = _BARE_CREDENTIAL_ASSIGNMENT.sub("[redacted]", text)
    return _AUTH_SCHEME.sub("[redacted]", text)


def _collapse_and_cap(message: str, *, limit: int) -> str:
    text = " ".join(message.split())
    if len(text) > limit:
        text = text[: max(0, limit - len(_TRUNCATED))] + _TRUNCATED
    return text


def redact_error_text(message: str, *, limit: int = MAX_ERROR_CHARS) -> str:
    """Strict policy: mask credentials and all quoted document literals."""
    text = _QUOTED.sub("'[redacted]'", _mask_credentials(message))
    return _collapse_and_cap(text, limit=limit)


def redact_job_error_text(message: str, *, limit: int = MAX_ERROR_CHARS) -> str:
    """Queue policy: mask credentials while retaining operational identifiers.

    This intentionally preserves quoted values. Generic job errors use quoted
    job kinds, tickers, accessions and FRED series IDs for diagnosis; payloads
    and document-derived values must instead be removed at their source.
    """
    return _collapse_and_cap(_mask_credentials(message), limit=limit)


__all__ = ["MAX_ERROR_CHARS", "redact_error_text", "redact_job_error_text"]
