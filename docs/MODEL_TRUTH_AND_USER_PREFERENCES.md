# Model Truth and User Preferences

Football evidence and personal constraints belong to separate layers.

## Model and football layer

Projection means and distributions, opportunity, role and centrality, matchup,
game environment, ownership, and historical validation represent the system's
best estimate of reality. User preferences never alter these values.

## User preference and optimization layer

Fandom exclusions, bankroll and contest limits, personal roster restrictions,
and other explicit choices apply after model inputs have been calculated. They
may change optimizer eligibility, candidate construction, or final selection.

Every excluded player remains in the optimizer audit with:

- the unchanged projection and P90;
- available football-role context;
- explicit optimizer eligibility;
- the user-preference rule and reason that caused exclusion.

Reports must not interpret preference-driven absence as weak projection or weak
football evidence. Historical model evaluation also uses the unmodified model
view.

Example:

```text
Projection: 18.4 DK points
Football assessment: strong value
Optimizer eligibility: EXCLUDED
Reason: user preference — opponent DEN
```

The opponent is only an example. The boundary applies to every present and
future user preference.

## Availability scenarios are model inputs

An explicit **Availability** override is a scenario assumption rather than a lineup
preference. **Assume Out** removes the player from forward opportunity, redistributes
vacated team opportunity with the generic injury allocator, and produces a new immutable
projection run. **Assume Active** treats a tentative status as available, but it cannot
override an officially confirmed inactive unless a separate diagnostic flag is used.

Operations now labels its player checkbox **Exclude and assume out**. By the user's
chosen workflow, that control, explicit bulk player-name/ID exclusions, and the
questionable checkbox create an assumed-out scenario before optimization. **Run
Optimizer** refreshes features and saves new projections before using that exact run.
Vacated workload is allocated with the existing scenario allocator; the original
model assessment remains available as `projection_before_scenario`, and official
statuses and historical training labels remain unchanged. Conflicting active/out
assumptions block execution. Weekly runs from Operations use the same assumptions.

Direct optimizer API `exclude_players`, `exclude_player_ids` and `exclude_questionable`
remain eligibility preferences unless a separate availability projection scenario
is requested. Opponent-team exclusions, exposure, overlap and Captain-only restrictions
also stay in the optimization layer; they do not assert that players are unavailable.
