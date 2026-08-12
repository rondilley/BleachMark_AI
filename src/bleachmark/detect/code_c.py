"""Lexical canonicalizer for C source (FR-46a, C-language arm).

C has no `ast` module in the standard library, and `pycparser` needs a full
preprocess pass and a heavy dependency (against NFR-03). So the C arm uses a
dependency-free lexical canonicalization that removes the same cosmetic channels
the Python AST path removes:

1. comments (`/* ... */` and `// ...`),
2. string and character literals (collapsed to `STR` and `CHR`),
3. identifier names (alpha-renamed to v0, v1, ... in first-seen order),
4. formatting and whitespace (re-emitted as single-space token joins).

C keywords and a small set of standard type and macro names stay as-is, because a
choice of `int` against `long` against `size_t` is a structural choice a watermark
could bias, not a cosmetic name. What survives is the token structure: the
construct choice, the operator choice, and the statement order. A green-list
watermark must act in this residual channel, so a watermark shows up as residual
variability that the control model does not have.

The canonicalization is lexical, not semantic. It is an honest approximation: it
cannot tell a type name from a variable name without a parser, so it keeps a fixed
keep-set and renames the rest. This is stated in the report note.
"""

from __future__ import annotations

import re

# C keywords (C11) plus common standard type, qualifier, and macro names. These
# stay verbatim, because they carry structure, not a cosmetic identifier name.
_C_KEEP = frozenset(
    {
        # keywords
        "auto", "break", "case", "char", "const", "continue", "default", "do",
        "double", "else", "enum", "extern", "float", "for", "goto", "if", "inline",
        "int", "long", "register", "restrict", "return", "short", "signed",
        "sizeof", "static", "struct", "switch", "typedef", "union", "unsigned",
        "void", "volatile", "while", "_Bool", "_Complex", "_Imaginary",
        # common standard types, qualifiers, and macros (structural, not cosmetic)
        "size_t", "ssize_t", "ptrdiff_t", "wchar_t", "bool", "true", "false",
        "int8_t", "int16_t", "int32_t", "int64_t", "uint8_t", "uint16_t",
        "uint32_t", "uint64_t", "intptr_t", "uintptr_t", "FILE", "NULL",
    }
)

# a block comment, a line comment, a string literal, or a char literal
_C_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
_C_STRING = re.compile(r'"(?:\\.|[^"\\])*"', re.DOTALL)
_C_CHAR = re.compile(r"'(?:\\.|[^'\\])*'")
# a preprocessor line (kept as a structural token stream, names still renamed)
_C_IDENT = re.compile(r"[A-Za-z_]\w*")
# an identifier, a number, or one punctuation or operator character
_C_TOKEN = re.compile(r"[A-Za-z_]\w*|\d+\.?\d*|[^\w\s]")


def _strip_comments_and_literals(code: str) -> str:
    code = _C_COMMENT.sub(" ", code)
    code = _C_STRING.sub(" STR ", code)
    code = _C_CHAR.sub(" CHR ", code)
    return code


def canonicalize_c(code: str) -> str:
    """Return a canonical C form with names, literals, and comments removed.

    The renamer maps each non-keep identifier to v0, v1, ... in first-seen order,
    so two functions that differ only in their variable names collapse to one form.
    """
    code = _strip_comments_and_literals(code)
    mapping: dict[str, str] = {}
    out: list[str] = []
    for tok in _C_TOKEN.findall(code):
        if _C_IDENT.fullmatch(tok) and tok not in _C_KEEP and tok not in ("STR", "CHR"):
            if tok not in mapping:
                mapping[tok] = f"v{len(mapping)}"
            out.append(mapping[tok])
        else:
            out.append(tok)
    return " ".join(out)
