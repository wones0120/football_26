# Classic Large-GPP effective strategy and replay

`classic_large_gpp_v1` uses `classic_large_gpp_effective_strategy_v1` in
`classic_strategy_contract.py`. It serializes ordered canonical Player inputs,
eligible IDs and ranking policy, generation options, resolved runtime config,
requested/effective game cap and source, metadata, implementation/CBC hashes,
execution mode, declared research deviations, and checksums. App runs and
production/parity replays execute the same contract. Saved optimizer-run JSON
already supports this payload; no database schema or environment change is needed.

The contract resolves existing ownership/leverage fallbacks, small-slate team
caps and standalone long-shot configuration using the same runtime helper as
execution. Neither the nominal generic rule profile nor a legacy stack-description
field overrides the executed configuration. Eligibility thresholds and initial
candidate/team caps share `classic_candidate_policy.py`; stack safety addbacks
can exceed initial caps. The full ordered final frame remains the replay input.

Production generation is sequential exposure-aware ILP. Accepted candidates are
the selected portfolio. The serialized template cycle, legality, tag/ownership
caps, objective and normalization, player limits, and overlap determine each
next candidate region. The trace retains region/objective coefficient hashes,
remaining exposures, prior rosters, template, blocked primary games and solver
status. An Optimal lineup solve does not prove a joint portfolio optimum.

`max_lineups_per_primary_game` is omitted/null for no cap or a positive integer.
A canonical sorted uppercase QB team/opponent pair is independent of QB direction
and of per-lineup player/game counts. Each accepted primary game consumes one
budget unit; when full, all QBs from both teams are blocked in the next solve.
Player caps are unchanged, and infeasible selection never relaxes the cap.
Small-field selection and its independent final audit use the same identity.

## Execution modes

- `PRODUCTION`: exact named strategy with requested user constraints.
- `PARITY`: same production path, frozen frame and configuration; no deviations.
- `RESEARCH_SHADOW`: explicit deviations required. Sequential cap sensitivities
  replay through the shared pipeline. Expanded discovery has a separate labelled
  research command, generation trace, full finite candidate pool and selector
  contract. Production replay rejects an expanded generation plan.

Every saved contract checks its content, effective configuration and current
implementation/solver fingerprints. Code/platform/solver drift requires a new
explicit parity check; it is never silently treated as exact replay.

## Frozen fixture

The first fixture is app run `d0e2ff8f-96cd-4fc0-ac7e-8297d4504701`, 2026 Week 4
Sunday Main, five entries and 80% max exposure. Its legacy snapshot freezes 154
final solver rows and its immutable eligibility ledger confirms the same IDs.
The old run did not retain complete historical upstream raw inputs or a broad
candidate pool. Replay starts at this documented final-frame boundary, uses no
current database reads, and compares saved per-step feasible models and captured
primary coefficients to the new shared execution.

```sh
.venv/bin/python scripts/audit_classic_large_gpp_parity.py
.venv/bin/python scripts/replay_classic_strategy_contract.py \
  --contract artifacts/classic_large_gpp_parity/d0e2ff8f/A_no_cap_contract.json \
  --output /tmp/classic-large-gpp-replay.json
.venv/bin/python scripts/research_classic_large_gpp_discovery.py
```

The first command verifies fixture checksums, IDs and all projections/P90, ledger,
resolved config, five accepted roster sets, region/coefficient fingerprints and
primary/report scores. A mismatch is classified and stops later research. It
then evaluates no cap and caps 4/3/2 at the same five entries/80% exposure.
The third command requires parity PASS, uses the same eligible frame/scoring and
five template slots, and labels its broader generation and finite joint selection
as `classic_large_gpp_v1 + expanded_discovery`.

Local evidence is under `artifacts/classic_large_gpp_parity/d0e2ff8f/`; the compressed
archive and SHA-256 manifest preserve the full fixture, original source capture,
contracts, traces and finite candidate pool. Extract it at repository root before
rerunning on the matching implementation/solver. The exact selected portfolios,
exposures, risk buckets and decision costs are in
[the comparison report](../../CLASSIC_LARGE_GPP_APP_CODEX_PARITY_AND_GAME_CAP.md).
