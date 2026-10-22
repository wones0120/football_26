"""One bounded serial indexed local source pass; no download/DB/model mutation."""
from pathlib import Path
from datetime import datetime,timezone
from collections import defaultdict,Counter
import json,csv,hashlib,io,re,time
from proof import *
from backend.app.product_services.official_injuries import _Document
from Database.player_identity import normalize_player_name
OUT=Path(__file__).resolve().parent
ROOT=Path('research/readiness_2026_20261020/v1')
FIELDS=('game_id','play_id','season','week','season_type','posteam','defteam','play_type','play_type_nfl','no_play','pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt','quarter_end','fumble','desc','passer_player_id','rusher_player_id','receiver_player_id','lateral_rush','lateral_rusher_player_id','lateral_rushing_yards')
def sha(b):return hashlib.sha256(b).hexdigest()
def read_source(r,cap):
 p=Path(r['artifact_path']);b=p.read_bytes();assert len(b)==r['byte_count']<=cap and sha(b)==r['content_sha256'];return b

def source_csv(r,cap):
 b=read_source(r,cap);rows=list(csv.DictReader(io.StringIO(b.decode('utf-8-sig'))));assert r['row_count']is None or len(rows)==r['row_count'];return rows

def save(v,kind):
 b=json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode();assert len(b)<64*1024*1024
 p=Path('artifacts')/kind/(sha(b)+'.json');p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():assert p.read_bytes()==b
 else:
  with p.open('xb')as f:f.write(b)
  p.chmod(0o444)
 return dict(path=str(p.resolve()),sha256=sha(b),bytes=len(b))

def inspect_article(r):
 v=json.loads(read_source(r,1024*1024));body=v.get('body','');doc=_Document(body).root
 titles=[x.content()for x in doc.find('h1')];pub=[]
 for x in doc.find('meta'):
  if (x.attrs.get('property')or x.attrs.get('name')or'').lower()in{'article:published_time','parsely-pub-date','pubdate','datepublished'}:pub.append(x.attrs.get('content'))
 pub+=re.findall(r'"datePublished"\s*:\s*"([^"]+)"',body)
 paragraphs=[x.content()for x in doc.find('p')];return dict(snapshot_id=r['snapshot_id'],source_uri=r['source_uri'],captured_at=r['captured_at'],observed_at=r['observed_at'],titles=titles,published_values=sorted(set(x for x in pub if x)),paragraphs=paragraphs)

def main():
 started=datetime.now(timezone.utc).isoformat();timer=time.monotonic();ready=json.loads((ROOT/'MANIFEST.json').read_text());old=json.loads((ROOT/'CACHE_2026_PROJECTION.json').read_text());db=json.loads((ROOT/'DB_READONLY_PROJECTION.json').read_text())['results'];snap=json.loads((ROOT/'DB_SOURCE_INVENTORY_COMPLETE.json').read_text())['snapshots'];index={r['snapshot_id']:r for r in snap}
 pbp_source=next(r for r in snap if r['dataset']=='play_by_play');ftn_source=next(r for r in snap if r['dataset']=='ftn_charting');weekly_source=index['cd2fb202-545d-5d0c-ac17-718296f64031']
 raw=source_csv(pbp_source,40*1024*1024);pbp=[{k:r[k]for k in FIELDS if k in r}for r in raw];del raw
 ftn=source_csv(ftn_source,3*1024*1024);newweekly=source_csv(weekly_source,512*1024);assert all(num(r['season'])==2026 and num(r['week'])==6 and r['season_type']=='REG'for r in newweekly)
 observed={(r.get('player_id')or None,canonical_team(r['team'])):{'pass_attempts':num(r.get('attempts')),'rush_attempts':num(r.get('carries')),'targets':num(r.get('targets'))}for r in newweekly};assert len(observed)==len(newweekly)
 expected={(r['source_player_id'],r['team']):r['counts']for r in ready['current_native_actor_projection']if r['week']==6};assert observed==expected,'W6immutable CSV must exactly match captured DBnativecount projection'
 schedule=[dict(g,home_team=canonical_team(g['home_team']),away_team=canonical_team(g['away_team']))for g in old['schedule_rows']if g['week']<=6];census,events=build_census(pbp,schedule);eventkeys={(r['game_id'],r['play_id'])for r in events};ftn_keys=set();ftn_unknown=[];ftn_summary=defaultdict(Counter)
 for r in ftn:
  gid=r['nflverse_game_id'];play=num(r['nflverse_play_id'])
  if gid not in {g['game_id']for g in schedule}or play is None or num(r['season'])!=2026:
   ftn_unknown.append(dict(game_id=gid,play_id=play,reason='unscoped_or_invalid_FTN_native_key'));continue
  if(gid,play)in ftn_keys:
   ftn_unknown.append(dict(game_id=gid,play_id=play,reason='duplicate_FTN_native_key;notconsumed'));continue
  ftn_keys.add((gid,play));w=int(gid.split('_')[1]);ftn_summary[w]['rows']+=1
  for field in('is_throw_away','is_screen_pass','is_qb_out_of_pocket'):ftn_summary[w][field+'_known']+=_bool(r.get(field))is not None
  if(gid,play)not in eventkeys:ftn_unknown.append(dict(game_id=gid,play_id=play,reason='FTNnativeplay_missing_in_current_PBPsource_scope; eligibility/side_unassessed'))
 # FTN is metadata support only; no throwaway or on-field inference changes target proof.
 weekly=defaultdict(dict);invalid=[]
 for r in ready['current_native_actor_projection']:
  if not r['native_valid']:invalid.append(r);continue
  key=r['game_id'],r['team'];n=r['source_player_id']
  if n in weekly[key]:raise ValueError('Duplicate same-game native weeklyactor')
  weekly[key][n]=r
 identities=resolve_all_edges(db['aliases']);inverse={pid:n for n,pid in identities.items()if pid is not None};positive=defaultdict(set)
 for r in old['positive_missing']:positive[r['native_game_id'],canonical_team(r['team'])].add(r['player_master_id'])
 rows=[];summary={};allcandidates=set()
 for g in sorted(schedule,key=lambda r:(r['week'],r['game_id'])):
  for t in[g['home_team'],g['away_team']]:
   prior=sorted([x for x in schedule if x['week']<g['week']and t in[x['home_team'],x['away_team']]],key=lambda r:r['week'])[-3:];candidates=set().union(*(set(weekly[x['game_id'],t])for x in prior))if len(prior)==3 else set();allcandidates|=candidates;key=g['game_id'],t
   proof={ch:group_proof(candidates,weekly[key],census[key][ch],ch,identities,positive[key])for ch in CHANNELS}
   threats=[r for r in invalid if r['game_id']==g['game_id']and r['team']==t]
   for ch,p in proof.items():
    if any(r['counts'][ch]!=0 for r in threats):p.update(native_group_complete=False,canonical_group_complete=False,invalid_native_source_possible_mass=True)
   P,T=proof['pass_attempts'],proof['targets'];pt=bool(P['event_count_exact']and T['native_credit_census_exact']and P['source_budget']is not None and T['source_budget']is not None and P['source_budget']==P['native_event_count']and T['source_budget']==T['native_event_count']and P['source_budget']>=T['source_budget'])
   rows.append(dict(game_id=g['game_id'],week=g['week'],team=t,opponent=g['away_team']if t==g['home_team']else g['home_team'],prior_games=[x['game_id']for x in prior],prior3_achieved=len(prior)==3,coldstart=len(prior)<3,channels=proof,target_and_pass_budget_compatible=pt,target_joint_native_group=pt and T['native_group_complete'],target_joint_canonical_group=pt and T['canonical_group_complete'],completed_status_verified=g['game_id']in{r['game_id']for r in old['completed_score_games']},FTN_unmatched_native_plays=[r for r in ftn_unknown if r['game_id']==g['game_id']],original_input_availability='RECONSTRUCTED_LATEST; original-vintage prior features not yet matched'))
 for w in range(1,7):
  gs=[r for r in rows if r['week']==w];summary[w]=dict(sides=len(gs),coldstarts=sum(r['coldstart']for r in gs),prior3=sum(r['prior3_achieved']for r in gs),known_source_rush_census=sum(r['channels']['rush_attempts']['native_credit_census_exact']for r in gs),known_source_target_census=sum(r['channels']['targets']['native_credit_census_exact']for r in gs),rush_native_complete=sum(r['channels']['rush_attempts']['native_group_complete']for r in gs),rush_canonical_complete=sum(r['channels']['rush_attempts']['canonical_group_complete']for r in gs),target_joint_native_complete=sum(r['target_joint_native_group']for r in gs),target_joint_canonical_complete=sum(r['target_joint_canonical_group']for r in gs),completed_canonical_rush=sum(r['completed_status_verified']and r['channels']['rush_attempts']['canonical_group_complete']for r in gs),completed_canonical_target=sum(r['completed_status_verified']and r['target_joint_canonical_group']for r in gs),conflict_sides={ch:sum(bool(r['channels'][ch]['conflicts'])for r in gs)for ch in CHANNELS})
 source_refs=dict(PBP=pbp_source,FTN=ftn_source,updated_W6_weekly=weekly_source)
 core=dict(version='2026_native_source_credit_proof_v1',groups=rows,event_basis=events,weekly_revision=dict(source=weekly_source,old_component_ref=old['source_refs']['component'],new_rows=ready['latest_DB_vs_frozen_component']['summary'],original_snapshot_unchanged=True),coverage=summary,FTN_measurement_coverage=dict(ftn_summary),FTN_unmatched=ftn_unknown,FTN_effect='Not consumed for targetzero/eligibility or exact11; unmatched rows remain explicit scope gap',identities=dict(native_universe=sorted(allcandidates|{n for g in census.values()for c in g.values()for n in c['credits']}),canonical_qualified=sum(identities.get(n)is not None for n in allcandidates),unknown=sum(identities.get(n)is None for n in allcandidates),mapping_as_of_now_not_original_pregame=True),source_refs=source_refs,source_observed_only=True,independent_NFL_census='UNKNOWN',model_fit=False,activation=False)
 full=save(core,'verification_2026_source_proof')
 # Two source-selected potential replacement cases; raw titles/dates/native role proof remain auditable.
 roster=next(r for r in snap if r['snapshot_id']=='20d2733f-ed55-5818-a090-227fe4e0ee41');roster_rows=source_csv(roster,1024*1024)
 cases=[]
 for gid,team,donor,recipient,source_ids in [('2026_06_BAL_CLE','BAL','Lamar Jackson','Tyler Huntley',['016c9c74-ed44-5839-830b-74398b06fc91']),('2026_06_CAR_PHI','PHI','Jalen Hurts','Tanner McKee',['0bac0466-b9de-5a5e-b8be-6f2753b81279','b06e415d-011e-550e-adbc-cf8572f42929'])]:
  docs=[inspect_article(index[x])for x in source_ids];actors=[]
  for name in[donor,recipient]:
   matches=[r for r in roster_rows if r.get('team')==team and r.get('position')=='QB'and normalize_player_name(r.get('full_name')or r.get('player_name')or'')==normalize_player_name(name)]
   natives={r.get('gsis_id')for r in matches if valid(r.get('gsis_id'))};native=next(iter(natives))if len(natives)==1 else None;actors.append(dict(name=name,team=team,position='QB',native_GSIS=native,canonical_UUID=identities.get(native),identity_basis='unique same-team QB normalized-name corroboration in nativeGSIS roster, never unscoped namejoin',roster_snapshot_id=roster['snapshot_id'],roster_capture=roster['captured_at']))
  cases.append(dict(game_id=gid,team=team,actors=actors,source_documents=docs,automatic_replacement_admission=False,reason='Article date/matchup/native subject and explicitabsence-plus-named-start assertion require narrow Highreview; no usage increase or inferred backup promotion'))
 case_ref=save(dict(version='2026_dated_replacement_source_inspection_v1',cases=cases,roster_source=roster,not_a_replacement_cohort_yet=True),'verification_2026_replacement_sources')
 receipt=dict(version='2026_verification_actual_v1',started_at=started,completed_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-timer,full_ref=full,case_ref=case_ref,coverage=summary,source_refs=source_refs,pbp_rows=len(events),FTN_rows=len(ftn),FTN_missing_PBP_keys=len(ftn_unknown),updated_W6_rows=len(newweekly),source_requests=0,DB_mutations=0,fits=0,original_input_vintage_replay=False,W6_final_status='UNKNOWN_NO_NEW_FINAL_SOURCE',scope='Retained-source proof only; no completeNFL/currentactivation claim')
 with(OUT/'ACTUAL_RECEIPT.json').open('x')as f:json.dump(receipt,f,indent=2,sort_keys=True);f.write('\n')
 print(json.dumps(receipt,indent=2))

def _bool(v):
 if v in('True','true','1','1.0'):return True
 if v in('False','false','0','0.0'):return False
 return None
if __name__=='__main__':main()
