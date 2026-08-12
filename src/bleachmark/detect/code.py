"""Constrained repeated-generation probe for source code (FR-45, FR-46, FR-46a).

The probe minimizes the places a watermark can hide, then looks at what is left.

1. Constrain the prompt: fix the function and variable names and the structure.
2. Canonicalize each generation: parse to an AST, alpha-rename every identifier to
   v0, v1, and so on, and unparse. This removes the naming channel, the whitespace
   and formatting channel, the comment channel, and the literal-format channel.
3. What survives canonicalization is structural token choice: a different construct,
   a different statement order, a different operator. A green-list watermark must
   use this residual channel, so a watermark shows up as residual variability that
   the control model does not have.

The probe aggregates a suite of well-known functions so the corpus reaches the
400-to-800-word attribution band (FR-49); one canonical function is too short.
The probe does not force the full output, because a forced token carries no
watermark (research 3).
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from .code_c import canonicalize_c

_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_CODE_FENCE = re.compile(r"```[a-zA-Z]*\n?|```")


class _AlphaRenamer(ast.NodeTransformer):
    """Rename local identifiers deterministically, so naming is not a channel."""

    def __init__(self) -> None:
        self.mapping: dict[str, str] = {}

    def _new(self, name: str) -> str:
        if name not in self.mapping:
            self.mapping[name] = f"v{len(self.mapping)}"
        return self.mapping[name]

    def visit_FunctionDef(self, node: ast.FunctionDef):
        node.name = self._new(node.name)
        for a in list(node.args.args) + list(node.args.kwonlyargs):
            a.arg = self._new(a.arg)
        if node.args.vararg:
            node.args.vararg.arg = self._new(node.args.vararg.arg)
        if node.args.kwarg:
            node.args.kwarg.arg = self._new(node.args.kwarg.arg)
        self.generic_visit(node)
        return node

    def visit_Name(self, node: ast.Name):
        # rename only names we have already bound (locals, params, the func name)
        if node.id in self.mapping:
            node.id = self.mapping[node.id]
        elif isinstance(node.ctx, ast.Store):
            node.id = self._new(node.id)
        return node


def _strip_fences(code: str) -> str:
    return _CODE_FENCE.sub("", code).strip()


def canonicalize(code: str) -> str:
    """Return a canonical form with naming, formatting, and comments removed.

    Falls back to a whitespace-and-comment normalization when the code does not
    parse, so a non-Python or malformed sample still yields a comparable form.
    """
    code = _strip_fences(code)
    try:
        tree = ast.parse(code)
        tree = _AlphaRenamer().visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
    except SyntaxError:
        # fallback: drop comments and collapse whitespace
        no_comments = re.sub(r"#.*", "", code)
        return re.sub(r"\s+", " ", no_comments).strip()


def canonicalize_for(lang: str, code: str) -> str:
    """Dispatch canonicalization by language: python (AST) or c (lexical)."""
    if lang == "c":
        return canonicalize_c(_strip_fences(code))
    return canonicalize(code)


_COMMUTATIVE = (ast.Add, ast.Mult, ast.BitAnd, ast.BitOr, ast.BitXor)
_CMP_FLIP = {ast.Lt: ast.Gt, ast.Gt: ast.Lt, ast.LtE: ast.GtE, ast.GtE: ast.LtE}


class _StructuralNormalizer(ast.NodeTransformer):
    """Collapse the semantics-preserving structural choices a watermark rides on.

    It sorts the operands of a commutative operator, sorts the operands of a boolean
    operator, and turns a comparison to one canonical direction. It keeps the
    identifier names, so the result is still runnable code. It does not touch a
    non-commutative operator, a chained comparison, or the statement order, because
    those changes are not always meaning-preserving.
    """

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if isinstance(node.op, _COMMUTATIVE):
            if ast.unparse(node.left) > ast.unparse(node.right):
                node.left, node.right = node.right, node.left
        return node

    def visit_BoolOp(self, node):
        self.generic_visit(node)
        node.values.sort(key=ast.unparse)
        return node

    def visit_Compare(self, node):
        self.generic_visit(node)
        if len(node.ops) != 1:
            return node
        op = node.ops[0]
        left, right = node.left, node.comparators[0]
        if type(op) in _CMP_FLIP:
            # turn a > b into b < a, and a >= b into b <= a: one direction only
            if isinstance(op, (ast.Gt, ast.GtE)):
                node.left, node.comparators[0] = right, left
                node.ops[0] = _CMP_FLIP[type(op)]()
        elif isinstance(op, (ast.Eq, ast.NotEq)):
            # == and != are commutative, so sort the operands
            if ast.unparse(left) > ast.unparse(right):
                node.left, node.comparators[0] = right, left
        return node


def structural_normalize(code: str) -> str:
    """Return runnable code with the commutative and comparison-direction slots closed.

    This is the deterministic corpus bleach. Two samples that differ only in operand
    order or comparison direction collapse to one form, so the residual structural
    channel closes without a model call. Samples that differ in a real way (a different
    construct or algorithm) stay different. The names are kept, so the result runs.
    Falls back to the input when the code does not parse.
    """
    code = _strip_fences(code)
    try:
        tree = ast.parse(code)
        tree = _StructuralNormalizer().visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree)
    except SyntaxError:
        return code


def _residual_variability(samples: list[str], lang: str = "python") -> float:
    """Mean pairwise token difference across the canonicalized samples."""
    canon = [Counter(_TOKEN.findall(canonicalize_for(lang, s))) for s in samples]
    if len(canon) < 2:
        return 0.0
    total = 0.0
    pairs = 0
    for i in range(len(canon)):
        for j in range(i + 1, len(canon)):
            keys = set(canon[i]) | set(canon[j])
            diff = sum(abs(canon[i].get(k, 0) - canon[j].get(k, 0)) for k in keys)
            size = sum(canon[i].values()) + sum(canon[j].values()) or 1
            total += diff / size
            pairs += 1
    return total / max(1, pairs)


@dataclass
class CodeProbeResult:
    candidate_residual: float
    control_residual: float
    excess: float
    corpus_words: int
    long_enough: bool
    likely_watermarked: bool
    note: str
    per_task: list[dict] = field(default_factory=list)


DEFAULT_SUITE = [
    "the nth Fibonacci number, iterative",
    "reverse a string",
    "check whether an integer is prime",
    "compute the factorial of n, iterative",
    "return the maximum of a list",
    "count vowels in a string",
    "compute the greatest common divisor of a and b",
    "check whether a string is a palindrome",
    "sum the digits of an integer",
    "return the second largest value in a list",
]

DEFAULT_SUITE_C = [
    "the nth Fibonacci number, iterative",
    "reverse a string in place",
    "check whether an integer is prime",
    "compute the factorial of n, iterative",
    "return the maximum value in an int array",
    "count vowels in a string",
    "compute the greatest common divisor of a and b",
    "check whether a string is a palindrome",
    "sum the decimal digits of an integer",
    "return the second largest value in an int array",
]

_PROMPT_PY = (
    "Write a Python function for: {task}.\n"
    "Use exactly this signature: def f(x). Rename every local to a, b, c. "
    "Iterative only, no recursion, no comments, no docstring, no prose. "
    "Return only the code."
)

_PROMPT_C = (
    "Write a C function for: {task}.\n"
    "Use exactly this signature: int f(int x). Name every local a, b, c. "
    "Iterative only, no recursion, no comments, no prose. "
    "Return only the code, no includes."
)


def suite_probe(
    candidate_fn: Callable[[str], str],
    control_fn: Callable[[str], str],
    tasks: list[str] | None = None,
    runs: int = 6,
    excess_threshold: float = 0.02,
    min_words: int = 400,
    lang: str = "python",
) -> CodeProbeResult:
    """Run the constrained, canonicalized probe over a suite of functions.

    For each task the model writes the function `runs` times under a naming and
    structure constraint. The probe canonicalizes each output and measures the
    residual variability of the candidate against the control. It aggregates the
    corpus word count to confirm the 400-to-800-word band. `lang` selects the
    Python AST canonicalizer or the C lexical canonicalizer.
    """
    if tasks is None:
        tasks = DEFAULT_SUITE_C if lang == "c" else DEFAULT_SUITE
    template = _PROMPT_C if lang == "c" else _PROMPT_PY
    cand_res: list[float] = []
    ctrl_res: list[float] = []
    per_task: list[dict] = []
    corpus_words = 0
    for task in tasks:
        prompt = template.format(task=task)
        cand = [candidate_fn(prompt) for _ in range(runs)]
        ctrl = [control_fn(prompt) for _ in range(runs)]
        corpus_words += sum(len(s.split()) for s in cand)
        cr = _residual_variability(cand, lang)
        xr = _residual_variability(ctrl, lang)
        cand_res.append(cr)
        ctrl_res.append(xr)
        per_task.append({"task": task, "candidate_residual": cr, "control_residual": xr})
    cand_mean = sum(cand_res) / len(cand_res)
    ctrl_mean = sum(ctrl_res) / len(ctrl_res)
    excess = cand_mean - ctrl_mean
    note = (
        "Residual variability is measured after canonicalization, so it is not "
        "formatting or naming noise. It is structural token choice, where a "
        "green-list watermark must act. It is investigative, not a guarantee "
        "(research 3, 5)."
    )
    return CodeProbeResult(
        candidate_residual=cand_mean,
        control_residual=ctrl_mean,
        excess=excess,
        corpus_words=corpus_words,
        long_enough=corpus_words >= min_words,
        likely_watermarked=excess >= excess_threshold,
        note=note,
        per_task=per_task,
    )


def constrained_probe(
    candidate_fn: Callable[[str], str],
    control_fn: Callable[[str], str],
    task: str,
    constraint: str = "Use exactly these names: def solve(a, b). Return one statement.",
    runs: int = 10,
    excess_threshold: float = 0.05,
    lang: str = "python",
) -> CodeProbeResult:
    """A single-task probe, kept for a quick check. Prefer suite_probe for power."""
    return suite_probe(candidate_fn, control_fn, tasks=[task], runs=runs,
                       excess_threshold=excess_threshold, min_words=0, lang=lang)
