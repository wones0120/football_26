# DFS Rule Library

## Phase 1 contract

`backend/app/product_services/rule_library.py` provides a solver-independent,
versioned policy layer. It is intentionally separate from player projection and
from PuLP model construction so future football rules can be added without
turning the optimizer into one large set of hard constraints.

Every `RuleDefinition` has:

- a stable `rule_id`, description, and reason code;
- one type: `hard_exclusion`, `soft_boost`, `soft_penalty`, or `warning`;
- zero or more declarative conditions over dotted candidate-context fields;
- optional Classic, Showdown, Head-to-Head, Large-GPP, or exact-profile scope;
- a non-negative base weight and optional metadata.

Conditions support equality, membership, comparison, containment, existence,
and truthy/falsy checks. Conditions inside one rule are combined with AND; an
empty condition list makes a deliberately unconditional rule.
Missing context does not accidentally satisfy negative or comparison rules.

`RuleEngine.evaluate` returns the objective score, total rule adjustment, final
score, hard-exclusion flag, warnings, and every triggered rule with its exact
effective weight and score contribution. The result also carries the immutable
library and strategy-profile versions needed for run lineage.

## Strategy profiles

The registry contains exactly four canonical Phase 1 profiles:

| Profile | Primary posture |
| --- | --- |
| `showdown_head_to_head_v1` | Mean, median, floor, and stable construction |
| `showdown_large_gpp_v1` | Ceiling, correlation, leverage, and uniqueness |
| `classic_head_to_head_v1` | Mean-dominant scoring with floor ahead of correlation |
| `classic_large_gpp_v1` | Ceiling-led scoring with correlation and leverage |

All profiles declare weights for mean, median, floor, ceiling, correlation,
ownership, leverage, and uniqueness. Objective inputs are expected to use a
comparable scale. Mean/median/floor/ceiling are higher-is-better projections;
raw ownership is intentionally assigned a small negative GPP weight. H2H
profiles assign ownership, leverage, and uniqueness zero weight.

Profiles may enable or disable a rule, change its type, replace its weight, or
apply a multiplier without modifying the library definition. This is the
mechanism for keeping eligibility hard while allowing football strategy to be
soft and contest-specific.

The existing optimizer resolver attaches the canonical `rule_profile_id` and
full `rule_profile` contract to its strategy metadata, so every new optimizer
run persists the selected profile alongside its existing strategy lineage.
Phase 1 does not replace established production solver objectives or add the
domain rule catalog; later phases will adapt optimizer inputs and constraints
to consume rule evaluations incrementally.

## Phase 2 player-pool safety

`backend/app/product_services/player_pool_safety.py` is the first production
adapter that consumes the library. It applies one shared, versioned eligibility
catalog before every optimizer engine and records each candidate's complete
rule evaluation. Identity, confirmed availability, current roster, slate,
backup-QB, cutoff, and user-exclusion failures are hard gates. Missing/stale
current context and uncertain or conflicting roles are warnings.

Locks use canonical player IDs, cannot bypass hard eligibility, and are passed
to both Classic and Showdown solvers. Structured audit reasons distinguish
eligibility, projection, strategy, and user exclusions. See
`docs/PLAYER_POOL_SAFETY.md` for the runtime and API contract.

## Phase 3 contextual scoring

`backend/app/product_services/player_context_scoring.py` applies the shared
`optimizer_player_context` v2 library to every player who passes Phase 2. It
uses bounded continuous magnitudes for source-backed game total, implied team
total, team-relative spread, current opportunity, red-zone/goal-line work, and
role certainty. These rules are exclusively soft boosts, soft penalties, and
warnings; the layer cannot exclude a player or make the solver infeasible.

Raw projection mean and P90 remain immutable. The adapter writes separate
context-adjusted objective columns for baseline solvers and supplies the same
adjustment to portfolio GPP scoring. Each player and completed lineup retains
the exact rule contributions. Missing market or opportunity evidence produces
a warning and zero adjustment. Runtime counts distinguish context-ready rows
from rows whose objective actually changed; a Large-GPP run with no safe market
context is explicitly degraded. See `docs/PLAYER_CONTEXT_SCORING.md` for the
formula, lineage, and operational contract.

## Phase 4 lineup correlation

`backend/app/product_services/lineup_correlation_scoring.py` applies
`optimizer_lineup_correlation` v4 inside both the baseline ILP and advanced
Classic GPP objective. It evaluates player pairs and Showdown Captain-specific
relationships through the same four strategy profiles. All Phase 4 rules are
soft boosts or soft penalties; the layer never excludes a player or restricts
which otherwise legal lineups remain feasible. Binary helper constraints only
linearize each objective contribution.

Completed lineups retain the total correlation adjustment, every contributing
pair, positive and negative reason codes, a construction label, and a
descriptive Showdown game-script label. See
`docs/LINEUP_CORRELATION_SCORING.md` for weights, lineage behavior, and current
limits.

## Phase 5 format-specific construction

Phase 5 advanced `optimizer_lineup_correlation` from v1 to v2. Phase 5A
advances it to v3 so positive stack terms are multiplied by cutoff-safe game
environment and missing context contributes zero. The baseline Classic/Showdown
solvers and advanced Classic GPP engine consume higher-order terms whose activation depends on
Captain slot, teammate counts, team splits, or an explicitly absent partner.

Version 4 adds Classic H2H-only soft variance penalties for a quarterback with
multiple same-team pass catchers and for three or more same-team offensive
players. Same-team combinations remain feasible, and RB/DST retains its
context-backed positive correlation term.

Classic covers naked pocket-QB penalties with a rushing-role exception, QB
double stacks, competitive full-game stacks, and three-player skill clusters
without the team's quarterback. Showdown covers Captain partner structure,
favorite/underdog 5-1 builds, competitive 3-3 and 4-2 builds, favorite-RB
Captain scripts, and fragile sub-$1,000 punts without current opportunity
evidence. All remain soft boosts or penalties. See
`docs/FORMAT_SPECIFIC_LINEUP_RULES.md` for the activation and audit contract.

## Adding a rule

1. Add a versioned `RuleDefinition`; never silently change the meaning of a
   previously persisted rule ID.
2. Scope it as narrowly as the football claim requires.
3. Prefer `soft_boost` or `soft_penalty`; reserve `hard_exclusion` for eligibility
   and impossible contest constructions.
4. Add tests for the trigger, non-trigger, missing-context behavior, applicable
   profiles, and explanation payload.
5. Backtest material weight changes and create a new profile version before
   promoting them.
