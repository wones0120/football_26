# Optimizer Lineup Correlation Scoring

## Contract

Phase 4 introduced `optimizer_lineup_correlation` v1 for Classic and Showdown
Head-to-Head and Large-GPP strategies. Phase 5 advanced the active library to
v2 with format-specific higher-order terms. The Phase 5A correction advances
the active library to v3 and removes isolated positive stack credit. The
Classic H2H variance update advances the active library to v4 with soft
penalties for QB plus multiple pass catchers and three or more same-team
offensive players. The baseline ILP and advanced Classic GPP engine use the
same rule evaluations. The
library changes objective score only: it does not change raw projections,
roster legality, user locks, exposure controls, or the explicit stack policy
selected for a run.

Every rule is a soft boost or soft penalty. A negatively correlated lineup can
still be selected when its projection advantage is large or the user locks its
players. Existing strategy-owned hard requirements, such as an explicitly
selected GPP stack template or the QB-Captain receiver rule, remain separate and
are still validated after solving.

## Pair preferences

The configured maximum contributions before canonical profile multipliers are:

| Relationship | Maximum adjustment |
| --- | ---: |
| QB + same-team WR/TE | +0.80 |
| QB + source-backed receiving RB | +0.35 |
| QB + opposing receiving option in a competitive shootout | +0.45 GPP only |
| Classic RB + own DST | +0.55 |
| QB + opposing DST | -1.50 |
| DST + opposing WR/TE | -0.40 |
| DST + opposing rushing-dependent RB | -0.60 |
| Opposing WR/TE mini-correlation in a competitive shootout | +0.30 GPP only |
| Two Showdown DSTs | -1.20, reduced in very low totals |
| Two Showdown kickers in a low-total competitive game | +0.25 |

Positive QB-stack magnitude is multiplied by a cutoff-safe environment score:

`0.35 * total quality + 0.35 * team-total quality + 0.20 * competitiveness + 0.10 * opponent push`

That base is reduced by blowout risk. The required inputs are game total,
team-relative spread, and implied team total from the selected projection's
immutable feature lineage. QB + receiving-RB also multiplies this environment
by source-backed receiving-role strength. RB/DST requires safe favorite and
low-total evidence; it has no structural floor. Unsafe or missing market
context therefore contributes exactly zero to every positive stack term.

The canonical Head-to-Head profile applies its existing `0.50` boost and `0.65`
penalty multipliers. Large-GPP uses the configured contribution. The advanced
GPP engine then applies its declared correlation objective weight, just as it
does for mean, ceiling, and leverage.

## Classic H2H variance preferences

Version 4 adds two H2H-only higher-order penalties before the `0.65` penalty
profile multiplier:

- `-0.85` for a QB with at least two same-team WR/TE players;
- `-0.55` for three or more same-team QB/RB/WR/TE players.

These terms never exclude a player or lineup. The ordinary QB/receiver boost
still applies, and a sufficient individual projection advantage can outweigh
the diversification preference. DST does not count as offense, so the existing
context-backed RB/DST bonus remains available.

## Showdown Captain preferences

Captain selection is evaluated jointly with the rest of the lineup. Phase 4
adds these role-sensitive terms:

- offensive Captain in a high-total game: up to +0.35;
- QB Captain + same-team WR/TE: up to +0.55 in addition to the base pair value;
- WR/TE Captain + own QB: up to +0.85;
- receiving RB Captain + own QB: up to +0.30 after role and environment scaling;
- DST Captain + own RB: up to +0.60 with supporting favorite/low-total script;
- DST Captain + own kicker: up to +0.40 with supporting favorite/low-total script;
- DST Captain + opposing QB: -0.75 in addition to the base conflict;
- kicker Captain in a low-total game: up to +0.25.

The high- or low-total Captain value is added once per candidate, not once per
lineup partner.

## Audit and Operations

Every completed lineup stores `lineup_correlation_summary` on its rows. The
summary distinguishes the raw library adjustment from the effective objective
contribution after any advanced-GPP correlation multiplier. It contains:

- library and strategy-profile versions;
- total rule adjustment, objective multiplier, and effective adjustment;
- positive and negative reason codes;
- every triggered rule, its magnitude, contribution, player pair, and context
  evidence;
- a human-readable construction label;
- for Showdown, an implied game-script label and its evidence.

Operations displays `Correlation`, `Construction`, and `Script` in the lineup
header when available. `Correlation rules` expands to show each positive or
negative contribution and the players responsible for it. Older saved runs do
not fabricate a Phase 4 summary.

## Phase 5 construction terms

Version 2 added terms activated by a complete lineup pattern rather than a
single player pair. The terms and exact solver linearization are documented in
`docs/FORMAT_SPECIFIC_LINEUP_RULES.md`. Phase 4 v1 remains identifiable in
historical optimizer-run payloads, as does Phase 5 v2; existing saved runs are
never relabeled.

## Game-script labels and current limits

Showdown labels describe the construction implied by team count, Captain role,
game total, and team-relative spread. Current labels include favorite
dominates, underdog upset, high-scoring shootout, low-scoring defensive game,
favorite leads/RB closes, and underdog trails/QB volume. If a 5-1 lineup has no
safe spread evidence it is labeled only as a one-sided build; favorite status
is not invented.

These labels are explanations, not simulated scenario probabilities. Phase 5
adds selected higher-order construction rules, but it does not implement
learned pairwise covariance or game-script probability scoring. Those require
cutoff-safe backtests or simulation evidence before promotion. Material weight
changes require a new library version. Version 4 remains an
`initial_policy_unvalidated` policy prior.

`showdown_gpp_portfolio_v3` adds a strategy-owned saturation layer without relabeling
the shared v4 library or historical runs. A QB's first, second, and third same-team
WR/TE receive 0.60, 0.30, and 0.10 points; additional pass catchers receive no extra
stack reward. An opposing pass-catcher bring-back receives 0.45 once per selected QB
team. The lineup report replaces the repeated pair events with these threshold events.
