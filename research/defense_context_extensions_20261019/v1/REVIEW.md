# B03.2 measured defense extensions

The isolated builder adds five source-supported catalog variants. It has not been published into current Prepare or a fitted feature matrix. Existing source/model modules remain unchanged.

- G14-M06: provider CPOE in percentage points over eligible nonspike official pass attempts with known vendor values. Values outside [-100,100] reject; unavailable values remain unknown. The vendor model's training and original availability are unknown.
- G14-M08: YAC yards per known completed nonspike pass. Incompletions do not supply zero YAC.
- G14-M10: passing touchdowns after an observed native-drive red-zone entry per entered drive with known outcome. An observed passing TD proves one; an observed rushing TD proves zero passing TDs. No observed TD in a partial drive remains unknown, even if all currently observed pass-TD flags are zero. Conflicting terminal evidence is unknown. A later passing TD from outside20 counts after prior proven entry; a long TD drive never observed entering is excluded. Completion basis and native terminal play IDs are retained per drive.
- G15-M08: conversion on nonkneel official rushes with known preplay yards-to-go in [0,2], including scrambles. Known first-down or rushing-TD evidence establishes conversion.
- G15-M10: QB rushing net yards/counts with scoped native game/team/player position evidence, source availability and canonical-identity checks. Without position proof, full QB rushing is unknown; separately labeled scramble-only evidence remains available.

Each metric retains known outcomes, unknown outcomes and unknown eligibility separately. Windows pool exposures over the last up to8 observed prior games, without claiming complete-game coverage. Provider measurements are descriptive, not a fantasy-point bonus or forecast. Pressure, blitz, man-zone and contact charting remain explicit source gaps.

API: `build_defense_context_extensions(event_receipt, *, before_period, cutoff, position_evidence=(), last_n_games=8)`. The caller must verify the immutable parent/raw source through the existing intake contract; a checksum alone does not authenticate source provenance. Canonical source ordering and original position evidence provenance are retained independently from the semantic hash.

Validation:13 focused tests passed in1.80s; exact file/log hashes are in `receipt.json`. Actual derivation and a named compact-context consumer remain pending A's operational compute slot and integration handoff. No source fetch, fit or runtime restart was performed for this slice.
