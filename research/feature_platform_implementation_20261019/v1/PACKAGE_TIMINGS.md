# Package timing evidence

`PACKAGE_TIMINGS.jsonl` records actual UTC stages as the owning agent reaches them. Use the local `record_package_timing.py --package NAME --agent AGENT --stage STAGE --evidence PATH --notes TEXT` helper for one append-only event write. Record package_start before new package implementation; review_ready after immutable pins; High records high_start and approval itself; each corrective cycle records rework_start/end. Source_start/end is separate from complete implementation time.

Earlier coding/review starts were not consistently recorded. Do not infer them from file modification times, tool latency, chat ordering or source-build elapsed time. Missing stages and end-to-end durations remain unknown. Process/source runtimes in existing actual receipts remain valid for that narrower operation, not package coding/review throughput. Heartbeat cadence is not an assignment or source-job scheduler: A/B/High continue via direct ready-work and resource-slot messages.

Record wait_start/wait_end with the same reason in notes for resource/approval/reviewer waits; state whether useful code work continued during the interval. Do not conflate source process runtime with approval-tool latency. Review-ready→High-start measures a review queue interval only when both actual events exist. Separate source dispatch timing from actual process/source timestamps in receipts. A owns log/schema; B and High append their own first-party stages.

Use the canonical `EVIDENCE.json.package` identifier for new events. `PACKAGE_TIMING_ALIASES.json` joins earlier spelling variants without rewriting append-only historical events; the helper normalizes known aliases. No timestamp is changed by normalization.

`PACKAGE_TIMING_EVIDENCE_INDEX.json` is the authoritative join by exact evidence reference for earlier differently named worker/High events. Preserve original event lines. Future helper writes prefer the evidence-reference canonical key; package_start should use that same EVIDENCE.package version identifier before implementation.
