"""One bounded retained-cache diagnosis; no repairs or source rereads."""
from pathlib import Path
from collections import Counter
from datetime import datetime,UTC
import json,gzip,hashlib,signal,time
from backend.app.product_services.game_state_reconstruction import state_before,_event,event_count_label_proof
D=Path(__file__).resolve().parent
FIXED={'2026_01_DEN_KC','2026_02_MIN_CHI','2026_03_SEA_WAS','2026_04_LA_PHI','2026_05_MIN_NO'}
def load(r):
 b=Path(r['path']).read_bytes();assert hashlib.sha256(b).hexdigest()==r['sha256']
 return json.loads(gzip.decompress(b)if r.get('encoding')=='gzip_json_v1'else b)
def main():
 start=time.monotonic()
 def timeout(*_):raise TimeoutError('Five second cacheddiagnosis cap')
 signal.signal(signal.SIGALRM,timeout);signal.setitimer(signal.ITIMER_REAL,5)
 original=json.loads((D/'COHERENT_CACHED_RECEIPT_v2b.json').read_text())['outputs'][-1]
 latest=json.loads((D/'COUNT_LABEL_ACTUAL_RECEIPT.json').read_text())['outputs'][-1]
 projection=load(original['projection_ref']);truth=load(latest['regulation_truth_ref'])
 ftnpath=Path('research/charting_source_components_20261020/v1/validated_2026.json');ftn=json.loads(ftnpath.read_text())
 bygame={g['game_id']:g for g in truth['games']if g['game_id']in FIXED};raws={}
 for values in projection['rows']:
  raw=dict(zip(projection['columns'],values))
  if raw['game_id']in FIXED:raws[raw['game_id'],str(int(float(raw['play_id'])))]=raw
 games=[];allreasons=Counter();allreplays=Counter()
 fields=('play_type','play_type_nfl','qtr','game_half','posteam','defteam','pass_attempt','rush_attempt','sack','qb_dropback','qb_scramble','qb_spike','qb_kneel','complete_pass','incomplete_pass','interception','no_play','play_deleted','replay_or_challenge','replay_or_challenge_result','two_point_attempt','receiver_player_id','passer_player_id','rusher_player_id','fumble','lateral_rush','lateral_reception','penalty','desc')
 for gid,g in sorted(bygame.items()):
  unknown=set(p for side in g['unknown_production_play_ids_by_side']for field in ('official_pass_attempts','official_carries','official_targets','physical_plays')for p in side[field])
  details=[];reasons=Counter();replays=Counter()
  for pid in sorted(unknown,key=int):
   raw=raws[gid,pid];state=state_before(raw,g['source_sides']);event=_event(raw,state,g['source_sides']);proof=event_count_label_proof(raw,state,event)
   basis=proof['basis']if isinstance(proof['basis'],str)else 'PER_FIELD_NATIVE_COUNT_PROOF'
   reasons[basis]+=1;literal=raw.get('replay_or_challenge_result');replays[str(literal)]+=1
   membership=[{field:pid in g['unknown_production_play_ids_by_side'][side][field]for field in ('official_pass_attempts','official_carries','official_targets','physical_plays')}for side in range(2)]
   details.append(dict(play_id=pid,unknown_membership_by_side=membership,raw_fields={k:raw[k]for k in fields if k in raw},missing_projected_fields=[k for k in fields if k not in raw],source_official_counts=event['official_counts'],physical_membership=event['physical_offensive_snap'],choice=event['choice'],helper_basis=basis,helper_barriers=proof['barriers'],helper_values=proof['production_by_side'],replay_literal_class='SOURCE_LITERAL_UPHELD'if str(literal).lower()=='upheld'else'SOURCE_LITERAL_REVERSED_REQUIRES_FINAL_FIELD_PROOF'if str(literal).lower()=='reversed'else'UNRESOLVED_OR_NA_LITERAL',
      text_only_throwaway_hint='throw' in str(raw.get('desc','')).lower() and 'away' in str(raw.get('desc','')).lower(),text_not_numeric_proof=True))
  allreasons.update(reasons);allreplays.update(replays)
  games.append(dict(game_id=gid,sides=g['source_sides'],count_labels=[{f:s[f]for f in ('official_pass_attempts','official_carries','official_targets','physical_plays')}for s in g['production_by_side']],regulation_score=g['regulation_scores'],independently_completed=g['independently_completed'],unknown_native_rows=len(details),helper_reason_counts=dict(reasons),replay_result_literals=dict(replays),details=details))
 result=dict(version='fixed2026_count_truth_diagnosis_v1',recorded_at=datetime.now(UTC).isoformat(),status='DIAGNOSIS_ONLY_NO_NUMERIC_LABEL_CHANGE',games=games,helper_reason_counts=dict(allreasons),replay_result_literals=dict(allreplays),
 refs=dict(projection=original['projection_ref'],count_truth=latest['regulation_truth_ref'],FTN_metadata=dict(path=str(ftnpath.resolve()),sha256=hashlib.sha256(ftnpath.read_bytes()).hexdigest())),
 FTN_metadata={k:ftn[k]for k in ('snapshot_id','captured_at','rows','field_availability','field_missingness','native_join','original_pregame_availability')},
 FTN_assessment='is_throw_away exists and is nonmissing13621rows with exact nativePBP joins proven. Per-fixed-unknown-key VALUE NOT inspected in this metadata-only pass; no zero-target inference. Need primary taxonomy plus samekey/native scope/positive recipient+credit contradictions before consuming.',
 cached_PBP_omissions=[k for k in ('qb_throwaway','is_throw_away')if k not in projection['columns']],
 weekly_alternative='Existing full-native weekly counts are whole-game revised source labels; not automatically regulation labels whenOT or sourcecountuniverse uncertain. Fixed5 have noOT per earlier source diagnosis and source Q4 binding, but per-game weekly target/carry/pass full-native census+native identity scope equality remains UNASSESSED here. No NFL completeness claim.',
 operations=dict(projection_decodes=1,count_truth_decodes=1,FTN_metadata_reads=1,FTN_rows_decoded=0,raw_reads=0,repairs=0,fits=0),elapsed_seconds=time.monotonic()-start)
 signal.setitimer(signal.ITIMER_REAL,0)
 (D/'FIXED2026_COUNT_TRUTH_DIAGNOSIS.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(dict(seconds=result['elapsed_seconds'],reason_counts=result['helper_reason_counts'],replays=result['replay_result_literals'],unknown_rows={g['game_id']:g['unknown_native_rows']for g in games})))
if __name__=='__main__':main()
