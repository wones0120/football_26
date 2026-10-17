# Versioned DST production correction

**The corrected ensemble is selected for 2026 Week 6 Prepare.** The user explicitly accepted activation with rollback and acknowledged that ranking advantage is unproven. Both API and durable worker attest the same approved checksum. Existing saved projections remain immutable; selecting runtime policy does not retroactively change them. Activation evidence is in `artifacts/dst_deployments/20261016/v1/`.

## What can be deployed

`dst_deployment.py` loads a checksum-pinned selection and fitted component. The component uses canonical team/player/game identity, verified event-scored DST outcomes, and the same strictly prior home/history adapter used in training. Missing history remains missing; it is not a fake zero. Opponent-QB experimental features remain excluded.

Two fixed artifacts are staged in `research/dst_production_rollout_20261016/v1/` with pending selections:

- `corrected_dedicated_mae_v1`: the existing corrected dedicated MAE policy. Its frozen point/noninferiority gates passed, but full-history selection is median five for every Sunday DST. It does not provide a differentiated defense rank.
- `corrected_temporal_ensemble_v1`: fixed 50% median + 25% regularized Ridge + 25% regularized tree. It uses corrected football inputs and shrinks uncertain estimates. Recent rolling MAE is 4.0598 versus incumbent 4.1590; ranking-superiority gates failed. This is a concrete candidate for an explicitly accepted forecast-noninferiority rollout, **not a passed rank-superiority model**.

These are separately versioned policies. Historical evaluations are retrospective, and original historical capture clocks remain incomplete. No later acceptance record can make those outcomes blind.

## Application contract

Normal canonical Prepare selects the component only when both `DST_DEPLOYMENT_MANIFEST_PATH` and `DST_DEPLOYMENT_MANIFEST_SHA256` are configured. A selection must contain an explicit approved acceptance decision, its standard and evidence hashes, and acknowledged limitations. Pending selections are deliberately unusable. Invalid hashes, unknown contracts, ambiguous identities, invalid calibration or expired periods stop Prepare before fitting/persistence rather than silently using another forecast.

The component owns DST means and DST residual calibration. It replaces the shared-tree DST mean after opportunity/market reconciliation, avoiding duplicate adjustment; offense still uses the unchanged shared model. Component residual quantiles use 88 prefix-only W3–W5 predictions, with the retrospective and selection-reuse limitation disclosed. Existing nonnegative forecast/quantile conventions are retained.

A saved combined artifact embeds the fitted component, corrected-source context and canonical keyed DST forecasts. Reload checks both shared raw forecasts and DST forecasts; DST explanations use its actual corrected inputs rather than unrelated offense-tree attributions. Model/source metadata names the policy, acceptance, source and calibration hashes. Gold feature JSON retains `dst_serving_component_inputs` alongside the unchanged shared-model inputs. The combined feature hash and model registry identity distinguish the policy. Older legacy artifacts remain loadable.

The staged component is valid **only for 2026 week 6**. A later week requires a new version and verified historical refresh; the old source is not silently reused forever.

## Activation and rollback

1. Resolve the deployment acceptance standard explicitly. Do not mark the failed rank gates passed. Create a separately identified approved selection from the pending template, recording the actual decision and limitations; keep the pending evidence intact. Do not use files named `ISOLATED_TEST` as runtime selections.
2. Pin that approved manifest's path/hash in the two configuration keys. Coordinate an idle API **and worker** restart. A normal Prepare then records the chosen component; do not bypass unrelated player availability guards to make a fresh slate appear ready.
3. Before advancing the active projection pointer, preserve its exact current value and fitted artifact checksum. Verify selected DST contract, all 20 DST inputs/means/quantiles, offense parity against matched inputs, and saved-artifact rescoring. Inspect rankings and the matched legal roster.
4. Roll back future Prepare by clearing the two deployment configuration keys and restarting both services when idle. Existing artifacts remain reproducible because each embeds its component. To roll back an already selected slate, use the existing explicit active-projection selection operation to restore the exact pre-rollout projection UUID captured in `live_before.json`; never overwrite or delete the corrected run. There is no pointer change to undo from this task.

The separately captured baseline is Main `28f764f0-6fe9-4463-b55e-c6c93804848c` with 288 means. Verify the current pointer immediately before activation; another authorized task may legitimately change it. The old shadow comparison uses `b2ae485d-f436-470b-a52c-fa53095bbd4d`, a different historical artifact.

## Verification and limits

Run `PYTHONPATH=. .venv/bin/python research/dst_production_rollout_20261016/v1/stage.py` to reconstruct the fixed components with zero fits. `verify_prepare.py` exercises real Prepare scoring and serialization on the preserved valid 288-player snapshot; persistence is intercepted. Both policies preserve all 268 non-DST numerical forecasts exactly, and reload 20 DST forecasts/explanations within 1e-12. This does not prove fresh current-slate readiness or actual database persistence of an accepted corrected run.

The fresh normal Classic Prepare previously failed on unresolved availability for four offensive players before creating a projection. That independent guard does not prevent isolated DST verification and is not bypassed here.

## Accepted activation: 2026-10-16

The approved decision `human-accepted-dst-ensemble-20261016-v1` preserves the user instruction verbatim in `artifacts/dst_deployments/20261016/v1/selection.approved.json`. Selection SHA256 is `c2a5aee81621a1403f6e6b04cc2fab717ae179bc30044c732f5fb5a340b07a89`; policy is `ensemble`. The acceptance is provisional forecast deployment with rollback, not a changed research result. `runtime_verified.json` captures independent API and worker process-level attestation.

Rollback command, from the repository root with coordinated idle jobs:

```sh
PYTHONPATH=. .venv/bin/python artifacts/dst_deployments/20261016/v1/rollback.py --restore-main-projection --restart
```

It restores only this rollout's configuration keys and, if Main's pointer belongs to this accepted selection, restores the exact saved baseline. It refuses to replace an unrelated concurrent pointer, preserves all model/projection artifacts, and writes a separately dated receipt. To restore configuration alone, omit `--restore-main-projection`. The previous exact model artifact is copied and hash-verified locally.

For a fresh-run comparison, `research/dst_production_rollout_20261016/v1/counterfactual.py` reconstructs legacy DST means/quantiles from the accepted run's same shared fitted model and unchanged legacy feature batch. It returns DST rows only; hold all non-DST pool cells/settings fixed and never persist this diagnostic as a historical projection. This separates defense-policy effects from new source captures.

The first refresh exposed an old unmanaged duplicate worker that survived launchd-only restart. Its legacy projection was preserved and rejected as corrected evidence. The restart script now stops extra verified repo workers gracefully before managed restart; two regression cases protect managed/unrelated workers. `runtime_verified_unique_worker.json` proves one accepted consumer remains. Always verify the actual newly persisted component/calibration/Gold inputs; startup configuration alone cannot prove which process claimed a job.

## Verified refreshed outputs

The actual accepted Sunday projection is `c8869a96-440c-4c36-aead-3614d6ef4d97` / model run `3dd3819a-b880-4696-a734-eb689c96bde9`. All 20 DST means/quantiles/corrected Gold inputs and 265 non-DST pre-overlay means verify. The saved five-lineup run is `bebc581f-cda1-4db9-b0a1-352eeba6efea`; it remains preliminary/NOT_READY with unknown availability excluded. Runtime selection and this explicit refreshed run use the ensemble; the old global Main pointer remains preserved rather than silently promoting preliminary output.

Matched local generation changes 4/5 canonical rosters; the fifth retains all nine players with a changed CAR forecast. All non-DST pool cells, source snapshot, ownership, eligibility, controls, checked packet and seed are fixed. Ensemble replay exactly reproduces the saved portfolio. Full before/after evidence and the tested rollback command are in `artifacts/dst_deployments/20261016/v1/FINAL_REPORT.md`. The rollback dry-run passes and the old 288 Main rows remain unchanged.
