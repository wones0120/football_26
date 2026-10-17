export function tiersSettingsKey(pool:string):string{return `tiers:${pool}`;}
export function tierChoiceLabel(player:{player_master_id:string|null;reason_codes:string[]},selected:{player_master_id:string|null}[]):string{
  if(player.reason_codes.length)return player.reason_codes.join("; ");
  return selected.some(p=>p.player_master_id===player.player_master_id)?"Selected by unchanged baseline projection":"Alternative; same baseline, native tier remains binding";
}
