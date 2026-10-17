# Same-team receivers in observed winning Sunday Main Classic lineups

**2026 sample: 0/15 first-place entries (0%) had at least two WRs from the same team. But 3,019/12,527 top-1% entries (24.10%) did, versus 182,346/1,242,949 classified field entries (14.67%).** First place is a tiny, volatile subset; these results do not support a blanket teammate prohibition.

Primary coverage: **13 downloaded Classic contest fields across five Sunday Main slates (2026 weeks1–5)**. Rank1 includes ties: one contest has three tied winning entries. There are13 contest-distinct first-place rosters; the15 entry count preserves duplicated winners. All winning entries resolve to nine distinct canonical players. Showdown, Tiers and Single Stat are excluded.

## Definitions and denominators

“Two receivers” primarily means **at least two natural WRs with the same historical salary-pool team**, including a WR in FLEX. A WR+TE is reported separately. “Exactly two maximum” means the largest same-team WR count is exactly2; “three-plus” means at least3. “With own QB” means a qualifying receiver team equals the rostered QB’s team; “without own QB” means no qualifying receiver team has its QB rostered. The two QB categories partition the primary two-WR metric. The actual starter context below is a separate retrospective evidence state.

First place: supplied rank==1, including all ties. Top1%: supplied rank≤ceil(imported field size ×.01), including boundary ties; ceiling rounding may admit more than exactly1%. It is not “paid.” Paid finishes are **unavailable**: the13 hash-verified raw CSVs have no winnings/payout column, normalized entries have no payout amounts, and no complete payout schedule is supplied. User-only entry-history winnings cannot label the entire field.

Entries retain duplicates. Distinct-roster statistics below collapse sorted canonical player IDs **within each contest**, then sum contest–roster observations; a roster appearing in multiple contests remains multiple observations. Across contests, repeated slates/players/rosters are dependent. No significance claim treats individual entries or contests as independent trials.

## Primary 2026 results

| Construction | First-place entries | Top1% entries | Field entries |
| --- | --- | --- | --- |
| ≥2 WR same team | 0/15 (0.00%) | 3,019/12,527 (24.10%) | 182,346/1,242,949 (14.67%) |
| Exactly two maximum WR on one team | 0/15 (0.00%) | 3,009/12,527 (24.02%) | 180,499/1,242,949 (14.52%) |
| ≥3 WR same team | 0/15 (0.00%) | 10/12,527 (0.08%) | 1,847/1,242,949 (0.15%) |
| WR + TE same team | 7/15 (46.67%) | 4,119/12,527 (32.88%) | 366,720/1,242,949 (29.50%) |
| ≥2 WR/TE same team | 7/15 (46.67%) | 6,282/12,527 (50.15%) | 504,248/1,242,949 (40.57%) |
| ≥2 WR with their own team QB rostered | 0/15 (0.00%) | 2,617/12,527 (20.89%) | 139,876/1,242,949 (11.25%) |
| ≥2 WR with that team QB absent | 0/15 (0.00%) | 402/12,527 (3.21%) | 42,470/1,242,949 (3.42%) |

Both strict two-WR and broader pass-catcher definitions matter: **7/15 first-place entries (46.67%) had same-team WR+TE**, despite none having two WRs. “Receivers” in football conversation must not silently mix these categories.

### Distinct roster observations within contests

| Construction | First-place distinct | Top1% distinct | Field distinct |
| --- | --- | --- | --- |
| ≥2 WR same team | 0/13 (0.00%) | 2,535/11,513 (22.02%) | 163,825/1,150,781 (14.24%) |
| Exactly two maximum WR on one team | 0/13 (0.00%) | 2,525/11,513 (21.93%) | 162,113/1,150,781 (14.09%) |
| ≥3 WR same team | 0/13 (0.00%) | 10/11,513 (0.09%) | 1,712/1,150,781 (0.15%) |
| WR + TE same team | 7/13 (53.85%) | 3,658/11,513 (31.77%) | 321,459/1,150,781 (27.93%) |
| ≥2 WR/TE same team | 7/13 (53.85%) | 5,504/11,513 (47.81%) | 445,641/1,150,781 (38.73%) |
| ≥2 WR with their own team QB rostered | 0/13 (0.00%) | 2,159/11,513 (18.75%) | 124,035/1,150,781 (10.78%) |
| ≥2 WR with that team QB absent | 0/13 (0.00%) | 376/11,513 (3.27%) | 39,790/1,150,781 (3.46%) |

This is a construction association, not causal lift. Contests differ substantially in field size and repeated entrants. The pooled field is dominated by the large week1 contest. Giving each sampled week equal weight yields17.62% top1% versus15.69% field, a much smaller difference than the entry-weighted24.10% versus14.67%. Week2 reverses the pooled direction; the week table matters. No entry fee, field skill or tournament-type adjustment is justified by absent metadata.

## Week/slate coverage and rates

| Season/week | Contests | First place ≥2WR | Top1% ≥2WR | Field ≥2WR | Imported / classified entries |
| --- | --- | --- | --- | --- | --- |
| 2026 W1 Sunday Main | 2 | 0/2 (0.00%) | 2,463/8,479 (29.05%) | 129,027/839,843 (15.36%) | 841,537 / 839,843 |
| 2026 W2 Sunday Main | 3 | 0/3 (0.00%) | 72/483 (14.91%) | 11,937/47,784 (24.98%) | 47,917 / 47,784 |
| 2026 W3 Sunday Main | 3 | 0/3 (0.00%) | 50/418 (11.96%) | 5,007/41,553 (12.05%) | 41,616 / 41,553 |
| 2026 W4 Sunday Main | 4 | 0/6 (0.00%) | 419/3,066 (13.67%) | 35,225/305,868 (11.52%) | 306,459 / 305,868 |
| 2026 W5 Sunday Main | 1 | 0/1 (0.00%) | 15/81 (18.52%) | 1,150/7,901 (14.56%) | 7,906 / 7,901 |

## Does the quarterback matter?

Yes, the football mechanism matters: a passing TD can score for both QB and receiver, while receivers compete for finite targets. Passing volume, efficiency, receiving distribution, protection/opponent and game environment determine whether two players can contribute; a QB’s reputation is not an empirical joint probability. These standings alone cannot estimate that week’s pregame likelihood or prove a Cam Ward double-WR lineup cannot succeed.

For context, the source schedule’s actual listed starting QB is linked through nflreadpy native ID → canonical alias → exact season/week/team salary-pool QB membership. All applicable source games mapped without ambiguity. This is **postgame actual-starter context**, not proof of what was expected at lineup lock. A full immutable pregame expected-QB/availability/efficiency snapshot is not available for these contest fields, so no retrospective “elite QB” tier, passing-efficiency group or pregame likelihood is invented. Historical effective team membership comes from that contest’s salary pool; Wan’Dale Robinson is TEN in2026 rather than a current-master or old-team assumption.

### Mahomes and Ward: sparse observed cases

Denominators differ because Kansas City appears in only two sampled2026 slates; Tennessee appears in all five. “Applicable field” means all classified entries in contests whose native pool includes that QB’s team/game. “Own QB” denominators count only entries that actually roster the canonical actual starting QB. These are descriptive construction fractions, not probabilities of reaching P90.

| Actual starter/team | Slates / contests | First-place two team WRs | Top1% two team WRs | Field two team WRs |
| --- | --- | --- | --- | --- |
| Cam Ward / TEN | 5 / 13 | 0/15 (0.00%) | 5/12,527 (0.04%) | 1,709/1,242,949 (0.14%) |
| Patrick Mahomes / KC | 2 / 7 | 0/9 (0.00%) | 2/3,484 (0.06%) | 1,051/347,421 (0.30%) |

| Actual starter | Top1%: twoWR among own-QB entries | Field: twoWR among own-QB entries | Top1%: twoWR among entries with ≥1 teamWR | Field: twoWR among ≥1 teamWR |
| --- | --- | --- | --- | --- |
| Cam Ward | 2/27 (7.41%) | 1,217/10,868 (11.20%) | 5/488 (1.02%) | 1,709/74,491 (2.29%) |
| Patrick Mahomes | 2/53 (3.77%) | 858/20,707 (4.14%) | 2/164 (1.22%) | 1,051/26,785 (3.92%) |

Only **two Mahomes/KC and five Ward/TEN two-WR top1% cases** exist here, with different slates/opponents/player pools. Those counts cannot support a reliable Mahomes-versus-Ward rule or a causal field-adjusted comparison. Zero first-place cases for both is especially uninformative. Broader QB/team rows with sample sizes are retained in results.json, but no small sample is promoted to a recommendation.

## 2025 supplementary archive, kept separate

Six older Sunday Main fields (weeks6–11) have **3/6 first-place entries (50%)** with two same-team WRs; top1% is3,202/13,723 (23.33%), field199,958/1,367,154 (14.63%). These archived normalized/captured inputs have existing content hashes, but their six original downloaded files are no longer at the checked known locations. They are supplemental cached evidence, not mixed into the13 raw-verified2026 fields. The contrast between0/15 and3/6 illustrates first-place sample volatility, not a season effect.

## Source and identity audit

The13 current original ZIP files were located in ~/NFL/Processed or the original known path. Every ZIP’s **uncompressed CSV SHA256 matches its import source hash**; archive bytes have their own separate hash. The source registry hashes CSV payload bytes, so comparing a ZIP-container hash to that source hash would be the wrong check. Originals were read only and not modified. Full source headers, paths, hashes, ZIP members and statuses are preserved in source_audit.json.

Grouped normalized actual standings were exported read-only, reusing earlier immutable captures where available. Counts preserve full imported file entry populations: 1,245,435 imported, 1,242,949 classified, 2,486 excluded. Blank/invalid slots, unresolved/ambiguous canonical identity, duplicate player identities and over-cap rosters are excluded with per-contest reasons; they are not silently assumed to lack the pattern. Every first-place entry is classified; one of12,528 raw top1% entries is excluded, leaving12,527 classified. Unknown construction is not counted as “no.” Complete imported-file coverage does not independently certify the official total contest field size for every archived source.

Three week2 contests were originally mislabeled SUNDAY_NIGHT; their nine Classic slots and multi-game Sunday Main salary membership were already documented in the earlier historical study. Original labels remain intact, and the research scope correction is explicit. The strict explicit-SUNDAY_MAIN subset is separately retained in summary.json, so this scope decision is reviewable.

Resolution uses only that season/week/Main native salary pool and natural slot-compatible positions, requires a unique native/canonical/team/opponent identity and rejects ambiguity. It does not join a global display name to today’s master-team attribute. FLEX uses the resolved natural position. Same Classic canonical roster identity ignores equivalent WR/RB/FLEX ordering; CPT formats never enter.

## Football interpretation and next step

Two teammates may benefit from the same successful passing game, compete for targets, or offer salary savings that improve the rest of the roster. A lineup can win without both reaching their own P90. The relevant decision is whether a full legal alternative has a stronger evidence-supported success path at the same budget/settings—not whether a single construction occurred in a handful of first-place results. The top1%/field association supports studying QB/target-distribution context; it does not validate a forced stack or generic penalty.

All scripts are read-only with respect to application data. No live model, projection, source status, setting or optimizer default changed. No contest entry, upload or submission occurred. Six meaningful checks cover natural WR/FLEX membership, WRTE separation, exact2/three-plus, ownQB partition, canonical duplicate/Showdown rejection and effective historical team ambiguity.

[Results and per-QB denominators](results.json) · [Summary cohorts](summary.json) · [Raw-source audit](source_audit.json) · [Inventory](inventory.json) · [Reproducible capture](capture.py) · [Analysis](analyze.py). Existing normalized/cached evidence was previously inspected; this is retrospective descriptive research, not fresh held-out validation.
