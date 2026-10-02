export type AvailabilityOverride = {
  player_name?: string;
  player_id?: string;
  availability: "default" | "assume_active" | "assume_out";
};

type PlayerDecision = {
  playerName: string;
  availability: AvailabilityOverride["availability"];
  excludeFromLineups: boolean;
};

export function optimizerAvailabilityOverrides(
  decisions: PlayerDecision[],
  excludedNames: string,
  excludedIds: string,
): AvailabilityOverride[] {
  const byReference = new Map<string, AvailabilityOverride>();
  const add = (row: AvailabilityOverride) => {
    const key = row.player_id ? `id:${row.player_id}` : `name:${row.player_name?.toLowerCase()}`;
    const previous = byReference.get(key);
    if (previous && previous.availability !== row.availability) {
      throw new Error(`Conflicting availability and exclusion for ${row.player_name ?? row.player_id}.`);
    }
    byReference.set(key, row);
  };
  for (const decision of decisions) {
    const player_name = decision.playerName.trim();
    if (!player_name) continue;
    if (decision.excludeFromLineups && decision.availability === "assume_active") {
      throw new Error(`Cannot assume ${player_name} active and exclude them as assumed out.`);
    }
    if (decision.excludeFromLineups || decision.availability !== "default") {
      add({ player_name, availability: decision.excludeFromLineups ? "assume_out" : decision.availability });
    }
  }
  for (const player_name of excludedNames.split(",").map((value) => value.trim()).filter(Boolean)) {
    add({ player_name, availability: "assume_out" });
  }
  for (const player_id of excludedIds.split(",").map((value) => value.trim()).filter(Boolean)) {
    add({ player_id, availability: "assume_out" });
  }
  return [...byReference.values()];
}
