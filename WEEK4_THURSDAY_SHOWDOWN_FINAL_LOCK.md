# PIT @ CLE — verified final-lock decision

**Updated 2026-10-01T20:12:32.865078-04:00. ENTRY READY: YES. ENTER THESE THREE.** Kickoff 8:15 PM EDT. Final source observations were at **7:45:49–50 PM EDT**, not the earlier bundle-creation time. The morning and afternoon freezes remain preserved.

[Download the final DraftKings CSV](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_uploads/20261002T001232Z/PIT_CLE_DK_SHOWDOWN_THREE_FINAL.csv). Exactly three native-ID lineups; no automatic upload or submission.

Immutable [final inputs](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_final_lock/20261001T225120Z/final_inputs.json), [normal projection freeze](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_final_lock/20261001T225120Z/refreshed_database_freeze.json), [full raw/common universe](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_final_lock/20261001T225120Z/final_common_universe.json), [A–E solves](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_final_lock/20261001T225120Z/decision.json), [independent entry clearance](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_final_lock/20261001T225120Z/entry_readiness.json).

Final official source reconciliation

[PIT official inactives](https://www.steelers.com/news/steelers-inactives-for-week-4-vs-browns), published 6:47 PM EDT: Rico Dowdle, Drew Allar, Will Howard (emergency 3QB), Eli Heidenreich, Kevin Jobity Jr., Gabriel Rubio. The article explicitly confirms Ramsey active and tonight’s Lew Nichols elevation, plus the Doneiko Slaughter signing.

[CLE official inactives](https://www.clevelandbrowns.com/news/browns-announce-inactives-for-week-4-vs-steelers), published 6:45 PM EDT: Taylen Green (3QB), Tylan Wallace, Justin Jefferson, Elgton Jenkins, Teven Jenkins. Complete roster/elevation/inactive reconciliation establishes game-active status; roster membership alone was not used.

All nine provisional players are verified active: Metcalf, Watson, Jeudy, Rodgers, Roman Wilson, Warren, Boston, Freiermuth and Judkins. Each retains a first depth-chart offensive role. Rodgers/Watson starting-QB verification uses official first depth plus complete final inactive reconciliation; no independent opening-snap announcement is claimed.

- **CLE OL:** Elgton Jenkins and Teven Jenkins inactive; official depth supports Luke Wypler C and Austin Barber RG. No new OL change versus morning; this is expected role evidence, not independent opening-snap confirmation..
- **Echols:** GAME ACTIVE; complete inactive reconciliation.
- **Homer:** GAME ACTIVE, offensive touches unverified; final-action role gate excludes.
- **Nichols:** GAME ACTIVE elevated; offensive touches unverified; final-action role gate excludes.
- **Ramsey:** GAME ACTIVE; final official article explicitly confirms.
- **Yahya Black:** GAME ACTIVE; complete inactive reconciliation.

No newly activated minimum-price offense has verified touches. Nichols’ elevation changes sourced availability and his normal model assessment, but does not establish an offensive workload; he remains excluded from actionable C/E portfolios alongside unsupported McLaughlin, Bernard, Heidenreich, Homer and Whiteheart. Full model/raw assessments are preserved.

[Official DK slots](https://www.draftkings.com/lineup/getavailableplayerscsv?draftGroupId=154084): 102 slots / 51 canonical players, zero unresolved identities. Allar/Howard/Green/Heidenreich now OUT; salary/ID pairs verified. [Current market](https://dknetwork.draftkings.com/moneyline-total-spread/): PIT −2.5, total 38.5, implied PIT20.5/CLE18.0. [NWS hourly weather](https://api.weather.gov/gridpoints/CLE/83,65/forecast/hourly), forecast updated 2026-10-01T19:46:50+00:00.

| EDT hour | Temp | Wind | Rain |
| --- | --- | --- | --- |
| 20:00 | 78F | 10 mph S | 5% |
| 21:00 | 77F | 10 mph S | 5% |
| 22:00 | 76F | 10 mph S | 10% |
| 23:00 | 76F | 9 mph SW | 19% |

Normal sourced context, 51 feature rows and 41 prediction rows were rebuilt. Heidenreich fell to zero, Nichols became available, and several PIT skill outputs changed through the unchanged normal pipeline. No manual forecasts, weights, correlations, CPT priors, ownership or policy parameters changed.

Full expanded discovery retained **777 distinct rosters**, **256 within .10**: global/captain ceiling and mean, forced FLEX, QB, structural/team splits, conditional discovery and exact PIT/CLE worlds. Every roster was exact baseline-rescored; ownership uniformly masked. Conditional worlds only discover candidates. Normalized research weights unchanged; saved production selector unused. Discovery 146.8s; exact rescore and joint solves 22.1s.

| Solve | Ranks | Selector sum | Mean sum | Marginal P90 sum | Captains | Theses | Overlap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | [1, 2, 3] | 2.753074592 | 195.911909069 | 405.776288743 | DK Metcalf | PIT passing concentration/balanced competitive | [4, 4, 5] |
| B | [1, 4, 7] | 2.736647247 | 190.111705731 | 403.792048508 | Aaron Rodgers/DK Metcalf/Deshaun Watson | balanced competitive | [6, 6, 6] |
| C | [3, 4, 32] | 2.715709526 | 195.993639756 | 412.152431683 | DK Metcalf/Deshaun Watson/Jerry Jeudy | CLE passing concentration/PIT passing concentration/balanced competitive | [4, 4, 4] |
| D | [3, 4, 32] | 2.715709526 | 195.993639756 | 412.152431683 | DK Metcalf/Deshaun Watson/Jerry Jeudy | CLE passing concentration/PIT passing concentration/balanced competitive | [4, 4, 4] |
| E | [3, 11, 22] | 2.710138369 | 191.670721376 | 406.982613296 | DK Metcalf/Denzel Boston/Jerry Jeudy | CLE passing concentration/PIT passing concentration/balanced competitive | [4, 4, 4] |

A unconstrained; B distinct CPT; C distinct CPT and three supported theses, overlap≤4 and supported-role gate; D pinned morning trio; E C plus Metcalf≤2/3. Choose C under the requested three-entry policy.

| Metcalf exposure | Selector | Mean | Marginal P90 | Captains | Theses | Overlap | 3/3 players |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3/3 | 2.715709526 | 195.993639756 | 412.152431683 | DK Metcalf/Deshaun Watson/Jerry Jeudy | CLE passing concentration/PIT passing concentration/balanced competitive | [4, 4, 4] | DK Metcalf, Deshaun Watson, Jerry Jeudy |
| 2/3 | 2.710138369 | 191.670721376 | 406.982613296 | DK Metcalf/Denzel Boston/Jerry Jeudy | CLE passing concentration/PIT passing concentration/balanced competitive | [4, 4, 4] | Aaron Rodgers, Deshaun Watson, Jerry Jeudy |

Exact 2/3 rosters:

1. CPT DK Metcalf; FLEX Jerry Jeudy; FLEX Deshaun Watson; FLEX Roman Wilson; FLEX Jaylen Warren; FLEX Aaron Rodgers.
2. CPT Jerry Jeudy; FLEX Quinshon Judkins; FLEX Denzel Boston; FLEX Deshaun Watson; FLEX DK Metcalf; FLEX Aaron Rodgers.
3. CPT Denzel Boston; FLEX Jerry Jeudy; FLEX Deshaun Watson; FLEX Pat Freiermuth; FLEX Jaylen Warren; FLEX Aaron Rodgers.

| CPT | Best selector | Gap | Counts .05/.10/.15/.20/.30 |
| --- | --- | --- | --- |
| DK Metcalf | 0.919074320 | 0.000000000 | 18/41/63/76/78 |
| Deshaun Watson | 0.914294942 | 0.004779378 | 10/24/30/31/31 |
| Jerry Jeudy | 0.900881506 | 0.018192814 | 12/22/27/31/31 |
| Denzel Boston | 0.903117063 | 0.015957257 | 7/24/39/45/47 |
| Jaylen Warren | 0.899042442 | 0.020031878 | 3/21/35/37/38 |
| Aaron Rodgers | 0.903277985 | 0.015796335 | 9/18/27/27/27 |

Validation: **105 tests passed**; 334 historical files, 148 production source files, 86 Classic configurations and 2 saved Thursday runs verified unchanged. Summed marginal P90 is not a portfolio percentile. No actual fantasy results used.

### ENTRY READY?

**YES.**

### Final captains

DK Metcalf, Deshaun Watson, Jerry Jeudy.

### FINAL THREE LINEUPS

#### Final lineup 1

| Slot | Player | Salary | Native DK ID |
| --- | --- | --- | --- |
| CPT | DK Metcalf | $13,500 | 44315946 |
| FLEX | Jerry Jeudy | $3,000 | 44315917 |
| FLEX | Deshaun Watson | $9,400 | 44315894 |
| FLEX | Roman Wilson | $4,000 | 44315914 |
| FLEX | Jaylen Warren | $9,600 | 44315893 |
| FLEX | Aaron Rodgers | $9,800 | 44315892 |

**Salary $49,300; selector 0.916888960; mean 65.523799271; summed marginal P90 134.894078373.** Thesis: PIT passing concentration, {'CLE': 2, 'PIT': 4}.

#### Final lineup 2

| Slot | Player | Salary | Native DK ID |
| --- | --- | --- | --- |
| CPT | Deshaun Watson | $14,100 | 44315945 |
| FLEX | Jerry Jeudy | $3,000 | 44315917 |
| FLEX | Denzel Boston | $8,000 | 44315897 |
| FLEX | Pat Freiermuth | $5,600 | 44315908 |
| FLEX | DK Metcalf | $9,000 | 44315895 |
| FLEX | Aaron Rodgers | $9,800 | 44315892 |

**Salary $49,500; selector 0.914294942; mean 63.903120903; summed marginal P90 134.722565184.** Thesis: balanced competitive, {'CLE': 3, 'PIT': 3}.

#### Final lineup 3

| Slot | Player | Salary | Native DK ID |
| --- | --- | --- | --- |
| CPT | Jerry Jeudy | $4,500 | 44315968 |
| FLEX | Quinshon Judkins | $8,800 | 44315896 |
| FLEX | Denzel Boston | $8,000 | 44315897 |
| FLEX | Deshaun Watson | $9,400 | 44315894 |
| FLEX | DK Metcalf | $9,000 | 44315895 |
| FLEX | Jaylen Warren | $9,600 | 44315893 |

**Salary $49,300; selector 0.884525624; mean 66.566719582; summed marginal P90 142.535788126.** Thesis: CLE passing concentration, {'CLE': 4, 'PIT': 2}.

### Thesis for each lineup

1. PIT passing concentration: {'CLE': 2, 'PIT': 4}.
2. balanced competitive: {'CLE': 3, 'PIT': 3}.
3. CLE passing concentration: {'CLE': 4, 'PIT': 2}.

### Pairwise overlap

1–2: 4/6, 1–3: 4/6, 2–3: 4/6.

### 3/3 players

DK Metcalf, Deshaun Watson, Jerry Jeudy.

### Metcalf exposure

**3/3.** Reducing 3/3 to 2/3 costs **0.005571158 selector (0.205145562%)**, **4.322918381 mean**, **5.169818387 summed marginal P90**. The model supports the higher-selector portfolio; diversification is not imposed mechanically.

### Fragile punts

**NO.**

### PIT decisive?

**YES**, supported PIT passing branch.

### CLE decisive?

**BORDERLINE** for a dedicated blowout; supported CLE passing concentration is represented.

### Rodgers CPT?

**NO** for the recommended three.

### What changed from the morning portfolio?

No selected roster or captain changed; fresh inputs and changed normal outputs were fully rerun, and the trio re-earned selection. Final inactives, Nichols elevation, transactions and forecast are now reconciled.

### Any unresolved player/injury blockers

None for the recommended three.

### Remaining blockers

None.

### Exact recommendation

**ENTER THESE THREE.** [Final DraftKings CSV](/Users/wones/git/football_26/artifacts/week4_thursday_showdown_uploads/20261002T001232Z/PIT_CLE_DK_SHOWDOWN_THREE_FINAL.csv). Manual upload only; no entries were uploaded or submitted.
