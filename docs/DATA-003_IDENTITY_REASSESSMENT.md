# DATA-003 Identity Reassessment

Completed: 2026-07-30

## Outcome

The post-consolidation salary-identity audit passes. The current deterministic
matcher re-evaluated all 1,010 unresolved non-DST salary rows against 10,972
canonical player masters and found no newly resolvable row. Every stored reason
still matches the current decision, every unresolved row has an open quarantine
record, and every retained reason is in the explicit accepted set:
`ambiguous` or `no_match`.

No canonical mappings or source salary rows were changed by this audit.

## Evidence

Run the read-only audit with:

```bash
.venv/bin/python scripts/product/audit_salary_identities.py \
  --database football_26_dev --pretty
```

The 2026-07-30 development-database result was:

| Measure | Result |
| --- | ---: |
| Salary rows | 22,478 |
| Resolved salary rows | 21,468 |
| Reassessed unresolved salary rows | 1,010 |
| Accepted `no_match` quarantines | 979 |
| Accepted `ambiguous` quarantines | 31 |
| Newly deterministic matches | 0 |
| Stored/current reason mismatches | 0 |
| Untracked unresolved rows | 0 |
| Unaccepted quarantine reasons | 0 |
| Unresolved DST rows | 0 |

The stable audit digest was
`d602ec44bce5055f65b8770932d40c654cfca723afacadfb8900648963f5d561`.
Its ordered per-row decision evidence digest was
`9de4c190a26f5f850ce93e8aa2658a74f91a05a1061df948bab5b08ef4bf372b`.

For 2025 Week 11 Sunday Main, `player_identity_coverage` remains a pass at
549/556 (`98.74%`). Its seven excluded rows are reported separately as six
`no_match`, one `ambiguous`, seven accepted quarantines, zero unaccepted
quarantines, and zero untracked rows.

## Enforcement

Accepted quarantine is derived conservatively: the row must remain unresolved,
have persisted status `open`, reproduce its stored reason under the current
matcher, and use either `ambiguous` or `no_match`. A newly deterministic match,
missing quarantine, changed reason, unexpected reason, or unresolved DST makes
the audit fail. Slate readiness also fails every input gate for untracked or
unaccepted identity rows.

Target salary snapshots are populated only from rows with
`player_master_id IS NOT NULL`, and optimizer/replay salary queries enforce the
same predicate. Accepted quarantine rows therefore stay visible in readiness
evidence but cannot enter modeling, simulation, lineup, or replay inputs
silently.

## Validation

```text
.venv/bin/python -m pytest -q \
  backend/app/tests/product/test_slate_readiness.py \
  backend/app/tests/product/test_identity_audit.py \
  backend/app/tests/product/test_player_identity.py

20 passed

.venv/bin/python -m pytest -q

369 passed
```
