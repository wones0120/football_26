from pathlib import Path
import json,hashlib
from backend.app.product_services.scheduled_workload_efficiency_model_inputs import METRICS,EXPOSURES,TEAM_ADDED,PLAYER_ADDED
ROOT=Path('research/workload_efficiency_model_batch_20261020/v1');m=json.loads((ROOT/'MANIFEST.json').read_text())
metrics={name:dict(numerator=num,denominator=den,actor_scope='Every included prior game sourceQB-proven'if qb else'All source actors with observed numerator/denominator',unit=f'signed_{num}_per_{den}'if 'yards'in num else f'{num}_per_{den}')for name,num,den,qb in METRICS}
contracts={}
for grain,out in m['grains'].items():
 entries=[]
 for column in out['added_columns']:
  team_column=column[5:]if grain=='player'and column.startswith('team_')else column
  shared=team_column.startswith('weekly3_');axis='own'if team_column.startswith('weekly3_own_')else'opponent'if shared else'actor'
  key=team_column.removeprefix('weekly3_'+axis+'_')if shared else column.removeprefix('scheduled3_')
  detail=metrics.get(key,{})
  if shared:scope='ALL raw native source actor rows before position/UUID filtering; valid unresolved native amounts included; passing is all-passer extension, not original QB-only G04 actor cohort'
  else:scope=detail.get('actor_scope','Canonical actor/nativeGSIS/frozen UUID at same-team/season; no current/target role proof inferred')
  entries.append(dict(column=column,grain=grain,axis=axis,unit=detail.get('unit','source_event_count'if key.endswith('exposure')else'official_count_per_scheduled_game'if key.endswith('mean')else'fraction_of_full_compatible_native_source_channel_budget'if key.endswith('pooled_share')else'source_presence_or_literal_role_indicator'),source_fields=detail or key,cohort=scope,window='Exactly3 immediate prior SCHEDULED same-team-season games, dates/periods before target; no skip or prior-season borrow',role_policy='Latest prior scheduled actor row only; literal prior roles remain unknown if absent/conflicted. Role consistency requires ALL3known roles; no target position/current health.',unknown_policy='Missing row/source field/scope/cohort makes exact sum/rate/share unknown; known zero contributes0, pooled zero denominator undefined. Known-source/actor-row counts describe recorded row presence, not complete NFL participation.',shares='Pool actor and all-native source counts on IDENTICAL3nativegame IDs; never average per-game shares or donate unresolved mass',identity='Native IDs/frozen source aliases; known unresolved native amounts retained as rest, no display-name join',source_refs=m['source_refs'],availability='Revised postlock captures/alias proofs; original historical pregame availability unproven.2026onlywhereactualsourcecoverage exists',target_game_ledger_is_input=False))
 contracts[grain]=dict(ordered_column_count=len(out['ordered_columns']),inherited_columns_manifest_ref=m['baseline_manifest_ref'],added_columns=entries)
(ROOT/'COLUMN_CONTRACTS.json').write_text(json.dumps(dict(version='workload_efficiency_column_contracts_v1',grains=contracts,label_contract='New all-raw SOURCE_OBSERVED team label; old source-role-filtered label stored, no full NFL census claim. Player known labels require exact current frozen raw count match; old warmup rowcohort retained.',football='Pass and receiver target views share events, not additive opportunities. Labels/target accounting ledger never enter features or preprocessing.',selection=m['selection']),indent=2)+'\n')
