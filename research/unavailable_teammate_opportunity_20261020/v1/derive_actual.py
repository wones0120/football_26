"""Approved absence/normalization/weekly/schedule parents, no raw or DB replay."""
from pathlib import Path
from datetime import datetime,UTC
import json,csv,hashlib,time
from backend.app.product_services.unavailable_teammate_opportunity import build_unavailable_opportunity,CHANNELS
from backend.app.product_services.absence_return_opportunity import load_reviewed_absence_input
from backend.app.product_services.weekly_passing_air_efficiency import load_reviewed_weekly_input
from backend.app.product_services.evaluation_record import digest
from backend.app.product_services.factual_designation import clock
ROOT=Path('research/unavailable_teammate_opportunity_20261020/v1');started=datetime.now(UTC);timer=time.monotonic()
def sha(b):return hashlib.sha256(b).hexdigest()
def load(ref,kind):
 p=Path(ref['path']).resolve();b=p.read_bytes();assert p.parent==Path('artifacts',kind).resolve() and p.name==ref['sha256']+'.json' and len(b)==ref['bytes']<=96*1024*1024 and sha(b)==ref['sha256'];return json.loads(b)
a=json.loads(Path('research/official_absence_path_20261020/v1/actual_receipt.json').read_text());absence_ref=a['artifact_ref'];absence=load_reviewed_absence_input(absence_ref,cutoff=started);weekly_ref=a['weekly_input_ref'];weekly=load_reviewed_weekly_input(weekly_ref,cutoff=started);assert absence['provenance']['weekly_input_ref']==weekly_ref
ar=json.loads(Path('research/weekly_feature_ancestry_20261020/v1/actual_receipt.json').read_text());ancestry_ref=ar['full_ref'];ancestry=load(ancestry_ref,'weekly_feature_ancestry')
assert ancestry['provenance']['weekly_input_ref']==weekly_ref and ancestry['provenance']['diagnostic_producer_code_sha256']==sha(Path('backend/app/product_services/weekly_feature_ancestry.py').read_bytes()) and clock(ancestry['provenance']['actual_publication_at'])<=started
vr=json.loads(Path('research/scheduled_venue_displacement_20261020/v1/actual_receipt.json').read_text());venue=load(vr['full_ref'],'scheduled_venue_displacement');schedule_ref=venue['provenance']['schedule_csv_ref'];assert schedule_ref['sha256']==absence['provenance']['schedule']['sha256'];b=Path(schedule_ref['path']).read_bytes();assert len(b)==schedule_ref['bytes'] and sha(b)==schedule_ref['sha256']
seasons={r['season']for r in absence['rows']};games=[]
for r in csv.DictReader(b.decode().splitlines()):
 if int(r['season'])in seasons and r['game_type']=='REG':games.append(dict(game_id=r['game_id'],season=int(r['season']),week=int(r['week']),game_type=r['game_type'],home_team=r['home_team'],away_team=r['away_team']))
assert len(games)==272*len(seasons)
x=build_unavailable_opportunity(absence,weekly,ancestry,games)
assert len(x['rows'])==11 and len(x['excluded_source_domains'])==3
unknown_identity=[r['source_fact']for r in x['rows']if r['player_master_id']is None]
for fact in unknown_identity:assert any(q['source_record_key']==fact['source_row_key']for q in absence['identity_review_requests'])
queue_proof=dict(original_source_adapter_receipt='research/official_absence_path_20261020/v1/actual_receipt.json',inherited_original_identity_readback=a['identity_readback'],current_database_replay=False,new_cases=0,source_unresolved_ordinary_facts=len(unknown_identity))
x['provenance']=dict(absence_input_ref=absence_ref,weekly_input_ref=weekly_ref,normalization_ancestry_ref=ancestry_ref,schedule_csv_ref=schedule_ref,reviewed_schedule_parent_ref=vr['full_ref'],original_absence_source_provenance=absence['provenance'],weekly_stage_normalization_limits=ancestry['imputation_ancestry'],inherited_identity_evidence=queue_proof,actual_read_at=started.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),actual_publication_at=datetime.now(UTC).isoformat(),producer_code_sha256=sha(Path('backend/app/product_services/unavailable_teammate_opportunity.py').read_bytes()),availability='Original PDF source is public status fact, roster/weekly canonical bindings later revised; no historical original-pregame or health/workload forecast claim')
data=json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode();h=sha(data);p=Path('artifacts/unavailable_teammate_opportunity')/(h+'.json');p.parent.mkdir(exist_ok=True)
if p.exists():assert p.read_bytes()==data
else:
 with p.open('xb')as f:f.write(data)
 p.chmod(0o444)
ref=dict(path=str(p.resolve()),sha256=h,bytes=len(data));out=dict(actual_started_at=started.isoformat(),actual_completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-timer,full_ref=ref,semantic_sha256=x['semantic_sha256'],ordinary_source_facts=len(x['rows']),canonical_source_facts=sum(r['player_master_id']is not None for r in x['rows']),unresolved_source_facts=len(unknown_identity),excluded_source_facts=len(x['excluded_source_domains']),exact_actor_baselines={c:sum(r['metrics'][c]['catalog_unavailable_prior_mean']is not None for r in x['rows'])for c in CHANNELS},exact_team_totals={c:sum(t['metrics'][c]['complete_unavailable_prior_mean_sum']is not None for t in x['team_game_totals'])for c in CHANNELS},team_totals=x['team_game_totals'],parent_refs=dict(absences=absence_ref,weekly=weekly_ref,ancestry=ancestry_ref),source_adapter_replays=0,database_reads=0,database_writes=0,alias_queries=0,new_captures=0,source_fetches=0,models=0)
(ROOT/'actual_receipt.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out),flush=True)
