"""Co-evolve the watermark context against the bleach (FR-56 to FR-60, research 3, 7).

The reorder rounds and the bound (round 13) leave an adversarial game. The WATERMARK DESIGNER
picks a context (unigram, window, prev) to keep the most signal against the current bleach. The
BLEACH picks an attack (reorder, substitution) to remove the most signal, and it must keep the
meaning (a fidelity gate). Each best-answers the other. The co-evolution finds where they settle.

The payoff is the watermark degradation, measured against the real green-list scheme. The bleach
maximizes it over the fidelity-safe attacks. The designer minimizes the bleach best answer over
the contexts. So the game value is a minimax, and the tool reports where the two populations meet.

The result names the equilibrium and the meta-finding: at equal fidelity a substitution removes
more than a reorder against every context, so the reorder family is dominated in the fidelity-safe
band. Its value is only against a context-keyed watermark that a designer would leave once the
reorder attack is known.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass

from ..detect.keyed.windowed import ContextScheme, generate_in_unit_order, reorder_degradation, _unit_sizes

_GRAN_FIDELITY = {1: 0.05, 4: 0.6, 12: 0.85, 40: 0.95}
FIDELITY_GATE = 0.7


@dataclass(frozen=True)
class Watermark:
    kind: str = "prev"        # "unigram" | "window" | "prev" | "selfhash"
    window: int = 3
    h: int = 4                # SelfHash context width


@dataclass(frozen=True)
class Attack:
    kind: str = "reorder"     # "reorder" | "substitution"
    unit_tokens: int = 12     # reorder granularity
    fraction: float = 0.15    # substitution fraction


def attack_fidelity(attack: Attack) -> float:
    if attack.kind == "substitution":
        return max(0.0, 1.0 - 2.0 * attack.fraction)     # a random swap hurts the meaning fast
    if attack.kind == "synonym":
        return max(0.0, 1.0 - 0.7 * attack.fraction)     # a synonym keeps most of the meaning
    if attack.kind == "shift":
        return max(0.0, 1.0 - 0.5 * attack.fraction)     # a few filler tokens keep the meaning
    return _GRAN_FIDELITY.get(attack.unit_tokens, 0.7)


def attack_feasible(attack: Attack) -> bool:
    return attack_fidelity(attack) >= FIDELITY_GATE


def _shift_degradation(scheme: ContextScheme, fraction: float, vocab: list[str],
                       total_tokens: int, n_eval: int, seed: int) -> float:
    z_ident, z_shift = [], []
    for i in range(n_eval):
        sizes = _unit_sizes(total_tokens, 1)
        seq = generate_in_unit_order(scheme, sizes, list(range(len(sizes))), seed + i, 2.0)
        rng = random.Random(seed + 700 + i)
        shifted = list(seq)
        for _ in range(int(fraction * len(seq))):
            shifted.insert(rng.randrange(len(shifted) + 1), rng.choice(vocab))
        z_ident.append(scheme.z_score(seq))
        z_shift.append(scheme.z_score(shifted))
    base = statistics.mean(z_ident)
    after = statistics.mean(z_shift)
    return max(0.0, 1.0 - after / base) if base > 1e-6 else 0.0


def _substitution_degradation(scheme: ContextScheme, fraction: float, vocab: list[str],
                              total_tokens: int, n_eval: int, seed: int) -> float:
    z_ident, z_sub = [], []
    for i in range(n_eval):
        sizes = _unit_sizes(total_tokens, 1)
        seq = generate_in_unit_order(scheme, sizes, list(range(len(sizes))), seed + i, 2.0)
        rng = random.Random(seed + 500 + i)
        sub = list(seq)
        for j in rng.sample(range(len(sub)), int(fraction * len(sub))):
            sub[j] = rng.choice(vocab)
        z_ident.append(scheme.z_score(seq))
        z_sub.append(scheme.z_score(sub))
    base = statistics.mean(z_ident)
    after = statistics.mean(z_sub)
    return max(0.0, 1.0 - after / base) if base > 1e-6 else 0.0


def degradation(watermark: Watermark, attack: Attack, vocab: list[str], key: str = "wm-key",
                total_tokens: int = 240, n_eval: int = 3, seed: int = 0, cache: dict | None = None) -> float:
    """The measured watermark degradation of an attack against a watermark context."""
    ck = (watermark.kind, watermark.window, watermark.h, attack.kind, attack.unit_tokens, round(attack.fraction, 3))
    if cache is not None and ck in cache:
        return cache[ck]
    scheme = ContextScheme(key=key, vocab=vocab, gamma=0.25, kind=watermark.kind,
                           window=watermark.window, h=watermark.h)
    if attack.kind in ("substitution", "synonym"):
        d = _substitution_degradation(scheme, attack.fraction, vocab, total_tokens, n_eval, seed)
    elif attack.kind == "shift":
        d = _shift_degradation(scheme, attack.fraction, vocab, total_tokens, n_eval, seed)
    else:
        d = reorder_degradation(scheme, attack.unit_tokens, total_tokens, 2.0, n_eval, seed)["degradation"]
    if cache is not None:
        cache[ck] = d
    return d


def game_payoff(watermark: Watermark, attack: Attack, vocab: list[str], cache: dict | None = None,
                **kw) -> float:
    """The usable degradation: zero when the attack is not fidelity-safe."""
    if not attack_feasible(attack):
        return 0.0
    return degradation(watermark, attack, vocab, cache=cache, **kw)


def fictitious_play(payoff: list[list[float]], iters: int = 4000) -> tuple:
    """Solve a zero-sum game by fictitious play (dependency-free).

    payoff[i][j] is the value to the COLUMN player, who maximizes; the ROW player minimizes.
    Each player best-answers the running empirical mix of the other. For a zero-sum game the
    empirical mixes converge to an equilibrium. Returns (row_mix, col_mix, value). A spread mix
    means a mixed equilibrium; a mix concentrated on one strategy means a pure equilibrium.
    """
    R, C = len(payoff), len(payoff[0])
    rc = [0.0] * R
    cc = [0.0] * C
    cc[0] = 1.0
    for _ in range(iters):
        cs = sum(cc)
        col_dist = [c / cs for c in cc]
        row_pay = [sum(payoff[i][j] * col_dist[j] for j in range(C)) for i in range(R)]
        rc[min(range(R), key=lambda i: row_pay[i])] += 1.0
        rs = sum(rc)
        row_dist = [r / rs for r in rc]
        col_pay = [sum(payoff[i][j] * row_dist[i] for i in range(R)) for j in range(C)]
        cc[max(range(C), key=lambda j: col_pay[j])] += 1.0
    rs, cs = sum(rc), sum(cc)
    row = [r / rs for r in rc]
    col = [c / cs for c in cc]
    value = sum(payoff[i][j] * row[i] * col[j] for i in range(R) for j in range(C))
    return row, col, value


def is_mixed(strategy: list[float], support_threshold: float = 0.1) -> bool:
    """A strategy is mixed when more than one option keeps real probability."""
    return sum(1 for p in strategy if p >= support_threshold) > 1


@dataclass
class GameResult:
    best_context: Watermark
    best_attack: Attack
    value: float                 # equilibrium degradation
    matrix: dict                 # (context_kind, attack_label) -> degradation
    stable: bool                 # a pure equilibrium was reached


def _attack_label(a: Attack) -> str:
    if a.kind == "substitution":
        return f"sub@{int(a.fraction*100)}%"
    if a.kind == "synonym":
        return f"synonym@{int(a.fraction*100)}%"
    if a.kind == "shift":
        return f"shift@{int(a.fraction*100)}%"
    return f"reorder@{a.unit_tokens}"


@dataclass
class EnrichedGameResult:
    contexts: list[str]
    attacks: list[str]
    matrix: list[list[float]]        # payoff[context][attack] degradation
    designer_mix: dict               # context -> probability
    bleach_mix: dict                 # attack -> probability
    value: float
    designer_mixed: bool
    bleach_mixed: bool


def enriched_game(vocab: list[str], contexts=None, attacks=None, total_tokens: int = 240,
                  n_eval: int = 3, seed: int = 0, iters: int = 4000) -> EnrichedGameResult:
    """Build the enriched payoff matrix and solve for the (possibly mixed) equilibrium."""
    contexts = contexts or [Watermark("unigram"), Watermark("window", 3), Watermark("window", 5),
                            Watermark("prev"), Watermark("selfhash", h=4)]
    attacks = attacks or [Attack("reorder", unit_tokens=12), Attack("substitution", fraction=0.15),
                          Attack("synonym", fraction=0.30), Attack("shift", fraction=0.30)]
    attacks = [a for a in attacks if attack_feasible(a)]
    cache: dict = {}
    matrix = [[round(game_payoff(c, a, vocab, cache, total_tokens=total_tokens, n_eval=n_eval, seed=seed), 3)
               for a in attacks] for c in contexts]
    designer, bleach, value = fictitious_play(matrix, iters=iters)
    return EnrichedGameResult(
        contexts=[c.kind if c.kind != "window" else f"window{c.window}" for c in contexts],
        attacks=[_attack_label(a) for a in attacks],
        matrix=matrix,
        designer_mix={(c.kind if c.kind != "window" else f"window{c.window}"): round(p, 3)
                      for c, p in zip(contexts, designer)},
        bleach_mix={_attack_label(a): round(p, 3) for a, p in zip(attacks, bleach)},
        value=round(value, 3),
        designer_mixed=is_mixed(designer),
        bleach_mixed=is_mixed(bleach),
    )


def co_evolve_game(
    vocab: list[str],
    contexts: list[Watermark] | None = None,
    attacks: list[Attack] | None = None,
    rounds: int = 8,
    total_tokens: int = 240,
    n_eval: int = 3,
    seed: int = 0,
) -> GameResult:
    """Alternating best-answer co-evolution over the context and attack strategy sets."""
    contexts = contexts or [Watermark("unigram"), Watermark("window", 3), Watermark("prev")]
    attacks = attacks or [Attack("reorder", unit_tokens=12), Attack("reorder", unit_tokens=1),
                          Attack("substitution", fraction=0.15), Attack("substitution", fraction=0.30)]
    cache: dict = {}

    matrix = {(c.kind, _attack_label(a)): round(game_payoff(c, a, vocab, cache, total_tokens=total_tokens,
                                                            n_eval=n_eval, seed=seed), 3)
              for c in contexts for a in attacks}

    context = contexts[0]
    attack = attacks[0]
    history = []
    for _ in range(rounds):
        # bleach best-answers the current context
        attack = max(attacks, key=lambda a: game_payoff(context, a, vocab, cache, total_tokens=total_tokens,
                                                        n_eval=n_eval, seed=seed))
        # designer best-answers the current attack
        context = min(contexts, key=lambda c: game_payoff(c, attack, vocab, cache, total_tokens=total_tokens,
                                                          n_eval=n_eval, seed=seed))
        step = (context.kind, _attack_label(attack))
        history.append(step)
        if len(history) >= 2 and history[-1] == history[-2]:
            break

    # the minimax value: the designer minimizes the bleach best-answer
    def worst_case(c: Watermark) -> float:
        return max(game_payoff(c, a, vocab, cache, total_tokens=total_tokens, n_eval=n_eval, seed=seed)
                   for a in attacks)

    best_context = min(contexts, key=worst_case)
    best_attack = max(attacks, key=lambda a: game_payoff(best_context, a, vocab, cache,
                                                        total_tokens=total_tokens, n_eval=n_eval, seed=seed))
    stable = len(history) >= 2 and history[-1] == history[-2]
    return GameResult(best_context=best_context, best_attack=best_attack,
                      value=round(worst_case(best_context), 3), matrix=matrix, stable=stable)
