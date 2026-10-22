"""One serial approved-cache projection+new label/input gate; no fit/DB/source API."""
from pathlib import Path
from datetime import datetime,UTC
import json,hashlib,time,gc
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input
from backend.app.product_services.model_weekly_workload_components import project_weekly_components
from backend.app.product_services.scheduled_workload_efficiency_model_inputs import build_workload_efficiency_contexts,append_workload_efficiency,TEAM_ADDED,PLAYER_ADDED,METRICS
from backend.app.product_services.model_source_budget_ledger import build_source_budget_ledger
from backend.app.product_services.team_opportunity_models import prepare_model_inputs
from backend.app.product_services.feature_block_model_inputs import prepare_player_inputs
from backend.app.product_services.model_input_admission import cohort_manifest
from backend.app.product_services.evaluation_record import digest
ROOT=Path('research/workload_efficiency_model_batch_20261020/v1')
if(ROOT/'MANIFEST.json').exists():raise ValueError('Frozen existing output, no automatic overwrite')
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def load(r,cap):
 if r['bytes']>cap:raise ValueError('Bounded managed cache exceeded')
 p=Path(r['path']);b=p.read_bytes()
 if p.name!=r['sha256']+'.json'or len(b)!=r['bytes']or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('Managed immutable cache bytes differ')
 return json.loads(b)
def save(value,kind,cap=400*1024*1024):
 b=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(b)<=cap
 sha=hashlib.sha256(b).hexdigest();p=Path('artifacts',kind,sha+'.json');p.parent.mkdir(exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb')as h:h.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha,bytes=len(b))
started=datetime.now(UTC);timer=time.monotonic();base_path=Path('research/scheduled_coverage_model_inputs_20261020/v1/MANIFEST.json');base=json.loads(base_path.read_text())
source_receipt=json.loads(Path('research/weekly_effectiveness_catalog_features_20261020/v1/actual_derivation_receipt.json').read_text());weekly_ref=source_receipt['full_ref'];raw_ref=source_receipt['source_extract_ref'];active_ref=json.loads(Path('research/active_workload_distributions_20261020/v1/actual_receipt.json').read_text())['full_ref'];schedule_ref=base['source_refs']['native_schedule']
schedule=load(schedule_ref,9*1024*1024);assert digest(dict(version=schedule['version'],game_rows=[{k:v for k,v in r.items()if k!='source_row'}for r in schedule['game_rows']]))==schedule['semantic_sha256'];schedule_rows=[r for r in schedule['game_rows']if 2023<=r['season']<=2026];del schedule
source_refs=dict(weekly=weekly_ref,raw_revision_extract=raw_ref,active_participation=active_ref,native_schedule=schedule_ref)
component_record=ROOT/'COMPONENT_REF.json'
producer=ref(Path('backend/app/product_services/model_weekly_workload_components.py'))
if component_record.exists():
 record=json.loads(component_record.read_text());assert record['producer_ref']==producer and record['source_refs']==source_refs;component=load(record['component_ref'],192*1024*1024);component_ref=record['component_ref'];print('Reusing immutable projected component; no repeated weekly/raw decode',flush=True)
else:
 weekly=load_reviewed_weekly_input(weekly_ref,cutoff=started);raw=load(raw_ref,64*1024*1024);active=load(active_ref,16*1024*1024);positive=active['positive_participants_missing_weekly_rows']
 assert active['provenance']['weekly_input_ref']==weekly_ref and all(p['season']==2026 for p in positive),'Preserve exact2026bounded missing-positive source scope'
 component=project_weekly_components(weekly,raw,schedule_rows,positive_missing=positive);component['provenance']=dict(source_refs=source_refs,actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),producer_ref=producer,original_pregame_availability=False,source_positive_missing_evidence_scope='Actual supplied2026facts only; historical participant censusUNKNOWN')
 component_ref=save(component,'model_weekly_workload_components',192*1024*1024);component_record.write_text(json.dumps(dict(component_ref=component_ref,producer_ref=producer,source_refs=source_refs),indent=2)+'\n');print(json.dumps(dict(stage='COMPONENT_END',actors=len(component['actor_rows']),teams=len(component['team_game_rows']),unscoped=len(component['unscoped_contributions']),ref=component_ref)),flush=True);del weekly,raw,active;gc.collect()
assert digest({k:v for k,v in component.items()if k not in{'semantic_sha256','provenance'}})==component['semantic_sha256']
contexts=build_workload_efficiency_contexts(component,schedule_rows);context_ref=save(dict(version=contexts['version'],team_contexts=contexts['team_contexts'],source_component_ref=component_ref),'weekly_workload_model_contexts');parents=dict(**source_refs,source_component=component_ref,context_ref=context_ref)
outputs={};scored_subjects=[];label_deltas={}
for grain in('team','player'):
 b=base['grains'][grain];matrix=load(b['matrix_ref'],300*1024*1024);extended=append_workload_efficiency(matrix,contexts,component,grain=grain,parent_refs=parents)
 assert len(matrix['rows'])==len(extended['rows'])
 assert all(all(new['features'][k]==old['features'][k]for k in matrix['feature_columns'])for old,new in zip(matrix['rows'],extended['rows'])),'Old raw numeric inputs cannot be silently revised'
 prepared=(prepare_model_inputs if grain=='team'else prepare_player_inputs)(extended,train_before=202401,validation_before=202501);cohorts=cohort_manifest(prepared,grain=grain)
 if grain=='player':
  for split,part in prepared['splits'].items():
   assert len(part['keys'])==b['cohorts'][split]['rows'],'Player warmup/row cohort must remain unchanged'
   for key,ys in zip(part['keys'],part['labels']):
    channels=[c for c,v in ys.items()if v is not None]
    if channels:scored_subjects.append(dict(**key,channels=channels))
 cols=list(TEAM_ADDED)if grain=='team'else[*(f'team_{k}'for k in TEAM_ADDED),*PLAYER_ADDED];ordered=prepared['preprocessing']['columns'];n=len(ordered);coverage={split:{k:sum(x[n+ordered.index(k)]==0 for x in part['x'])for k in cols}for split,part in prepared['splits'].items()}
 assert all(coverage['train'][k]>0 for k in cols),'Each declared new input must have actual training observations'
 deltas=[dict(game_id=r['game_id'],team=r['team'],period=r['period'],**({'player_master_id':r['player_master_id']}if grain=='player'else{}),differences=r['label_revision_difference'])for r in extended['rows']if r['label_revision_difference']];label_deltas[grain]=deltas
 outputs[grain]=dict(matrix_ref=save(extended,'workload_efficiency_model_matrices'),matrix_sha256=extended['matrix_sha256'],prepared_ref=save(prepared,'workload_efficiency_model_prepared'),prepared_sha256=prepared['prepared_sha256'],consumer_version=prepared['version'],ordered_columns=ordered,added_columns=cols,added_coverage=coverage,cohorts=cohorts,preprocessing=prepared['preprocessing'],baseline_matrix_ref=b['matrix_ref'],baseline_prepared_ref=b['prepared_ref'],baseline_cohorts=b['cohorts'],label_contract=extended['label_contract'],label_changed_rows=len(deltas),source_refs=parents)
 print(json.dumps(dict(stage=grain+'_END',columns=len(ordered),rows=len(extended['rows']),splits={k:v['rows']for k,v in cohorts.items()},label_changed_rows=len(deltas),efficiency_train={k:v for k,v in coverage['train'].items()if k in cols and ('fraction'in k or'per_'in k)})),flush=True);del matrix,extended,prepared;gc.collect()
ledger=build_source_budget_ledger(component['actor_rows'],scored_subjects=scored_subjects,positive_missing=component['positive_missing'],unscoped_threats=component['unscoped_contributions']);ledger_ref=save(ledger,'model_source_budget_ledger');delta_ref=save(label_deltas,'workload_model_label_deltas')
manifest=dict(version='workload_efficiency_model_batch_manifest_v1',actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,baseline_manifest_ref=ref(base_path),contract_ref=ref(ROOT/'HIGH_CONTRACTS.json'),source_refs=parents,component_ref=component_ref,accounting_ledger_ref=ledger_ref,label_delta_ref=delta_ref,grains=outputs,selection='Fixed approved raw statistical metrics selected by source/window coverage, NOT inspected2025 accuracy',producer_refs=[ref(Path('backend/app/product_services')/(n+'.py'))for n in('model_weekly_workload_components','scheduled_workload_efficiency_model_inputs','model_source_budget_ledger','team_opportunity_models','feature_block_model_inputs')],target_census='SOURCE_OBSERVED_NOT_FULL_NFL; historical participant censusUNKNOWN',player_cohort='Original canonical warmup/scoring rows retained; known native excluded/coldstart/unresolved amounts remain residual, not donated/predicted',original_pregame_backtest_eligible=False,outcomes_previously_inspected=True,fits=0,database_reads=0,source_requests=0,raw_PBP_reads=0,activation=False)
(ROOT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n');print(json.dumps(dict(stage='MANIFEST_END',elapsed=manifest['elapsed_seconds'],component_ref=component_ref,ledger_ref=ledger_ref)),flush=True)
