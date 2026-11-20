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
# Redaction input is bounded to this many characters (or four times the output
# limit, if larger) before any pattern runs, so a runaway message cannot make the
# redactor scan megabytes. Every pattern is linear, so the bound is generous: the
# stored text is capped far lower. When the bound cuts the text, the trailing
# partial token is dropped too (see ``_bound``), because a secret cut in half
# no longer matches the credential patterns and whitespace collapse can pull
# text from near the bound into the stored message.
MAX_INPUT_CHARS = 65536
_TOKEN_BOUNDARY = frozenset(" \t\r\n\f\v,;")
_TRUNCATED = "...[truncated]"

# Every pattern below is linear in the input. Each character of a quoted value
# is matched by exactly one alternative (a backslash pair, or a character that
# is neither a backslash nor the delimiter); keys are one possessive token
# checked for a sensitive word by lookahead, so ``secret-secret-...`` is
# scanned once; and no repeated group can match the same text two ways.
_KEY_CHARS = r"[A-Za-z0-9_-]"
_SENSITIVE_WORD = r"(?:secret|api[_-]?key|password|passwd|token|authorization)"
_KEY_TOKEN = rf"(?={_KEY_CHARS}*?{_SENSITIVE_WORD}){_KEY_CHARS}++"


def _quoted(name: str, *, unclosed_to_line_end: bool = False) -> str:
    """A quoted literal with escapes, as a regex fragment.

    The body has one parse. If no closing quote follows (a value ending in a
    literal backslash, such as ``'C:\\dir\\'``) the fallback runs to the last
    matching quote on the line, which is what the former backtracking did.

    With ``unclosed_to_line_end`` (credential values only), a value without a
    real closing quote is masked to the end of the line instead. That covers a
    value cut by the input bound and a truncated mapping repr such as
    ``{'password': 'SECRET``; without it the bare-value rule would mask only
    the first word. The last-quote fallback is not used here, because an
    escaped quote inside the value (``'a \\' b``) would end the match early and
    leave the later words visible. Quoted values never span lines, so the rest
    of the text is kept. Ordinary quoted literals keep the closing-quote
    requirement, so a lone apostrophe in prose does not mask the rest of its
    line.
    """
    fallback = r"[^\n]*+" if unclosed_to_line_end else rf"[^\n]*(?P={name})"
    return rf"(?P<{name}>['\"])" rf"(?:(?:(?!(?P={name}))[^\\\n]|\\.)*(?P={name})|{fallback})"


# Mapping/JSON reprs put a closing quote between the key and separator. Values
# may use the opposite quote, contain escaped delimiters, or carry a Python
# bytes/string prefix.
_QUOTED_CREDENTIAL_ASSIGNMENT = re.compile(
    rf"""
      (?P<key_quote>['"])
      {_KEY_TOKEN}
      (?P=key_quote)
      \s*[:=]\s*
      [bBrRuUfF]{{0,2}}
      {_quoted("value_quote", unclosed_to_line_end=True)}
    """,
    re.IGNORECASE | re.VERBOSE,
)
_BARE_CREDENTIAL_ASSIGNMENT = re.compile(
    rf"""
      (?<!{_KEY_CHARS})
      {_KEY_TOKEN}
      \s*[:=]\s*
      (?:
        [bBrRuUfF]{{0,2}}
        {_quoted("bare_value_quote", unclosed_to_line_end=True)}
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
# scheme word. The quoted body always succeeds (closing quote, line end or end
# of text), and a lone backslash before a newline is its own alternative.
_AUTHORIZATION_HEADER = re.compile(
    r"""
      \bauthorization\b['"]?\s*[:=]\s*
      (?:
        (?P<authz_quote>['"])
        (?:(?!(?P=authz_quote))[^\\\n]|\\[^\n]|\\(?![^\n]))*
        (?:(?P=authz_quote)|(?=[\r\n])|\Z)
        |
        [^\r\n]*
      )
    """,
    re.IGNORECASE | re.VERBOSE,
)
# ``scheme://user:pass@host`` for any scheme: mask the whole userinfo, up to the
# last ``@`` before whitespace, ``/``, ``?`` or ``#``, so a password that itself
# contains ``@`` is fully covered. The scheme length is bounded so each start
# position scans a constant window (no quadratic backtracking over long
# ``a+a+a+`` runs).
_URL_USERINFO = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]{0,31}://)[^\s/?#]*@")
_QUOTED = re.compile(_quoted("lit_quote"))


def _mask_credentials(message: str) -> str:
    # Match quoted-key assignments first: the bare-key expression cannot cross
    # the closing quote between ``'api_key'`` and ``:``.
    text = _URL_USERINFO.sub(r"\g<scheme>[redacted]@", str(message))
    text = _AUTHORIZATION_HEADER.sub("[redacted]", text)
    text = _QUOTED_CREDENTIAL_ASSIGNMENT.sub("[redacted]", text)
    text = _BARE_CREDENTIAL_ASSIGNMENT.sub("[redacted]", text)
    return _AUTH_SCHEME.sub("[redacted]", text)


def _bound(message: str, limit: int) -> tuple[str, bool]:
    """Cut the input to what can matter, and say whether anything was cut.

    A cut can land inside a credential. The cut-off tail, back to the last
    whitespace, comma or semicolon, is dropped as well, so no fragment of a
    secret that the patterns can no longer recognise survives the cut.
    """
    text = str(message)
    cap = max(MAX_INPUT_CHARS, 4 * limit)
    if len(text) <= cap:
        return text, False
    end = cap
    while end > 0 and text[end - 1] not in _TOKEN_BOUNDARY:
        end -= 1
    return text[:end], True


def _collapse_and_cap(message: str, *, limit: int, cut: bool = False) -> str:
    text = " ".join(message.split())
    if len(text) > limit or (cut and not text.endswith(_TRUNCATED)):
        text = text[: max(0, limit - len(_TRUNCATED))] + _TRUNCATED
    return text


def redact_error_text(message: str, *, limit: int = MAX_ERROR_CHARS) -> str:
    """Strict policy: mask credentials and all quoted document literals."""
    text, cut = _bound(message, limit)
    text = _QUOTED.sub("'[redacted]'", _mask_credentials(text))
    return _collapse_and_cap(text, limit=limit, cut=cut)


def redact_job_error_text(message: str, *, limit: int = MAX_ERROR_CHARS) -> str:
    """Queue policy: mask credentials while retaining operational identifiers.

    This intentionally preserves quoted values. Generic job errors use quoted
    job kinds, tickers, accessions and FRED series IDs for diagnosis; payloads
    and document-derived values must instead be removed at their source.
    """
    text, cut = _bound(message, limit)
    return _collapse_and_cap(_mask_credentials(text), limit=limit, cut=cut)


__all__ = ["MAX_ERROR_CHARS", "redact_error_text", "redact_job_error_text"]
