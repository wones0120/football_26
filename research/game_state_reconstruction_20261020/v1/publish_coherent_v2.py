"""Small receipt/truth-only evidence publication; no source or trajectory decode."""
from pathlib import Path
from datetime import datetime,UTC
from collections import Counter
import json,gzip,hashlib
D=Path(__file__).resolve().parent;ROOT=D.parents[2]
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b))
def load(r):
 b=Path(r['path']).read_bytes()
 if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:raise ValueError('Truth ref changed')
 return json.loads(gzip.decompress(b) if r.get('encoding')=='gzip_json_v1' else b)
r=json.loads((D/'COHERENT_CACHED_RECEIPT_v2b.json').read_text());assert r['status']=='COMPLETED_CACHED_TRANSFORM_NO_RAW_REPLAY'
old=json.loads((D/'CACHED_COVERAGE.json').read_text());fixed=['2026_01_DEN_KC','2026_02_MIN_CHI','2026_03_SEA_WAS','2026_04_LA_PHI','2026_05_MIN_NO'];seasons=[];truth2026={}
for o in r['outputs']:
 t=load(o['regulation_truth_ref']);stats=t['games'][0]['production_by_side'][0]
 seasons.append(dict(**o,regulation_known_side_channels={k:sum(g['production_by_side'][side][k] is not None for g in t['games']for side in range(2))for k in stats},
    remaining_mass='UNCERTIFIED_GROUP_COUNTS_NOT_PROBABILITIES;unknown groups retained, no renormalization',
    event_type_classification='Existing reason counts explicit. New native-start-class classification may be collected within High/A sole new-block decode; B does not repeat large source/block decode.'))
 if o['season']==2026:truth2026={g['game_id']:g for g in t['games']}
statuses=[]
for status in old['scheduled_2026_side_statuses']:
 status=dict(status);truth=truth2026.get(status['game_id']);status['regulation_truth']='CERTIFIED_Q4_SCORE'if truth and truth['regulation_score_certified']else'UNKNOWN_OR_ABSENT_SOURCE'
 status['regulation_score_metrics_admitted']=bool(truth and truth['metrics_admitted'])
 status['regulation_production_channels']='PER_CHANNEL_UNKNOWN_MASKS;score admission never admits unknown production'
 statuses.append(status)
coverage=dict(version='coherent_cached_coverage_v2',recorded_at=datetime.now(UTC).isoformat(),status='READY_HIGH_ACTUAL_SOURCE_REVIEW_NOT_SIMULATION_ADMISSION',
 operations=dict(raw_reads=0,cached_recompose_seconds=r['elapsed_seconds'],zero_decode_failed_preflight_seconds=.0022921250201761723,DB_queries=0,fits=0,pilot_runs=0),
 seasons=seasons,scheduled_2026_side_statuses=statuses,scheduled_2026_sides=len(statuses),
 fixed_selected_2026_truth=[truth2026[g]for g in fixed],
 fixed_truth_summary='All5 Q4 source scores certified and independently completed; ALL production totals remain None for both sides in these5games. Score-only evaluation possible after integrated gate; no attempt/target/yard metrics claimed.',
 all_source_score_games=92,independently_completed_2026_score_games=79,W6_final='UNKNOWN_NOT_INFERRED_FROM_SOURCE_END_MARKER',
 original_vintage='LATEST_RECONSTRUCTED;not original pregamedata',target_observed_states_used_for_generation=False,
 source_support='TRAIN full3242/6091, state3716/6091; kickofffull1477/2682,state1695/2682. Genuine unresolved mass remains.',
 contract='Only High-source/integrated gate and root may admit runtime smoke; no full-joint/calibration/forecast claim.')
assert len(statuses)==214 and sum(s['coldstart_team_scenario']for s in statuses)==96
(D/'COHERENT_COVERAGE_v2.json').write_text(json.dumps(coverage,indent=2)+'\n')
paths=[D/'COHERENT_CACHED_RECEIPT_v2b.json',D/'COHERENT_COVERAGE_v2.json',D/'COHERENT_PURE_PACKET_v2.json',D/'COHERENT_PROOF_API_v2.json',D/'COHERENT_COMPLETION_SCOPE_PREFLIGHT.json',D/'HIGH_COHERENT_PURE_REVIEW_v2.json',D/'COHERENT_EVENT_PROTOCOL_AMENDMENT_v2.json',D/'recompose_coherent_v2.py',D/'coherent_metadata_failure/COHERENT_CACHED_RECEIPT_v2.json',D/'coherent_metadata_failure/recompose_coherent_v2.py',D/'prior_103test_cached_revision/PRESERVED.json',D/'prior_128test_coherent_revision/PRESERVED.json',ROOT/'backend/app/product_services/game_state_reconstruction.py',ROOT/'backend/app/tests/product/test_game_state_reconstruction.py']
for o in r['outputs']:
 paths.extend(Path(o[k]['path'])for k in ['reconstruction_ref','blocks_ref','openings_ref','regulation_truth_ref'])
packet=dict(version='coherent_actual_source_packet_v2',recorded_at=datetime.now(UTC).isoformat(),status='READY_HIGH_CHANGED_SOURCE_REVIEW',pins=[ref(p)for p in paths],tests=dict(passed=137,elapsed_seconds=.53),
 receipt=str(D/'COHERENT_CACHED_RECEIPT_v2b.json'),coverage=str(D/'COHERENT_COVERAGE_v2.json'),
 limitations=coverage['fixed_truth_summary'],old_refs='Immutable original61/103 and prior128 guard artifacts preserved;same3minimalprojections,zero originalsource replay',next='High actualsource gate then A lossless adapter/library preparation; root dispatches changed-version smoke only after integratedPASS.')
(D/'COHERENT_ACTUAL_PACKET_v2.json').write_text(json.dumps(packet,indent=2)+'\n')
print(json.dumps(dict(packet=str(D/'COHERENT_ACTUAL_PACKET_v2.json'),pins=len(paths),fixed_scores=[g['regulation_scores']for g in coverage['fixed_selected_2026_truth']],all214statuses_preserved=True)))
