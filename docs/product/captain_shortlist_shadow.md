# Captain shortlist shadow — 2026 Week 5 Sunday night

The saved run generated 174 candidate records, with 40 passing quality and
portfolio feasibility gates. Its five-lineup portfolio omitted the highest
common-baseline mean candidate (original rank 64), despite that candidate being
able to participate in a full legal portfolio. This is an objective mismatch
between portfolio scoring and the separate projection-first recommendation,
not evidence that generation failed to discover this roster.

The bounded challenger keeps the existing recommendation ordering and expands
shortlist coverage. It uses the same six players as the control, switching
Captain from Drake London to Michael Penix Jr. London moves to FLEX. Salary is
$49,700 versus $49,900; projected points are 80.33 versus 79.09. Summed marginal
P90s are 145.62 versus 145.41, not calibrated lineup percentiles. Forcing the
challenger into a full portfolio costs 5.38 units of the existing portfolio
selector objective; that score is not money or expected return.

Canonical IDs and native slot salaries reconstruct the challenger. Captain
scoring is weighted once, totals reproduce the captured audit, both rosters pass
export validation, and the frozen live recommendation remains unchanged.
Sunday Main's saved recommendation, contract hash and projection reference also
remain unchanged. No production policy or application code changed.

The control/challenger pair was registered before kickoff as
`1a05d53421bd39447cf978143b129e096e7a09f9e8f6498527ea5af72e2b8f18`.
Learning's existing comparison workflow will evaluate it when results are
imported. Paid-finish improvement and expected-return improvement are unknown;
one slate cannot justify promotion. Prioritize shortlisting research before
adding more generation volume, and retain Sunday Main as the live priority.

Reproduce the offline comparison:

```sh
PYTHONPATH=. .venv/bin/python scripts/audit_captain_shortlist_shadow.py \
  --baseline artifacts/sunday_night_captain_baseline/registered_snapshot.json \
  --capture-dir artifacts/sunday_night_captain_ranking_shadow
```

The script never connects to the database or registers experiments. Input hashes,
the read-only candidate/salary captures, shadow roster and separate registration
receipt are saved in that artifact directory. Reconstruction deliberately fails
if the challenger contains a player absent from the frozen control: additional
forecast evidence must be captured before extending this bounded experiment.

The user confirmed `DKSalaries_2026_5_SUNDAY_NIGHT`. Its local CSV checksum
matches the previously imported file exactly; no duplicate import was needed.
The app status checked at 2026-10-10 16:29 UTC reports 104 mapped salary rows,
a current prepared build, and no build issue. Final entry clearance remains
unverified; refresh availability before entering.
