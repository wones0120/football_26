"""Descriptive observed Classic standings; canonical roster construction only."""
from pathlib import Path
from collections import Counter,defaultdict
import json,gzip,math,hashlib,sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from scripts.analyze_classic_historical_study import build_players,SLOTS,team
P=Path(__file__).resolve().parent
POPS=('winner','top_1','field')
METRICS=('two_wr','exactly_two_wr_max','three_plus_wr','wr_te','two_passcatchers','two_wr_with_own_qb','two_wr_without_own_qb')
def classify(players):
 wr=Counter(p['team'] for p in players if p['position']=='WR');te=Counter(p['team'] for p in players if p['position']=='TE');pc=wr+te;qb=next(p for p in players if p['position']=='QB');doubles={t for t,n in wr.items() if n>=2};m=max(wr.values(),default=0)
 return dict(two_wr=bool(doubles),exactly_two_wr_max=m==2,three_plus_wr=m>=3,wr_te=bool(set(wr)&set(te)),two_passcatchers=max(pc.values(),default=0)>=2,two_wr_with_own_qb=qb['team'] in doubles,two_wr_without_own_qb=bool(doubles) and qb['team'] not in doubles),wr,qb

def parse(lineup,resolver):
 parsed=SLOTS.findall(lineup or '')
 if len(parsed)!=9 or Counter(s for s,n in parsed)!=Counter({'QB':1,'RB':2,'WR':3,'TE':1,'FLEX':1,'DST':1}):return None,'not_legal_classic_slots'
 players=[resolver(slot,name) for slot,name in parsed]
 if any(p is None or not p['canonical'] for p in players):return None,'canonical_identity_unresolved'
 if len({p['id'] for p in players})!=9:return None,'duplicate_canonical_player'
 if all(p['salary'] is not None for p in players) and sum(p['salary'] for p in players)>50000:return None,'salary_over_50000'
 return players,None

def empty():return {pop:{'raw_entries':0,'valid_entries':0,'entry':Counter(),'unique_rosters':0,'unique':Counter()} for pop in POPS}
def main():
 inv=json.loads((P/'inventory.json').read_text());salaries=json.loads((P/'salaries.json').read_text());schedule=json.loads((P/'schedule.json').read_text());aliases=defaultdict(set)
 for r in json.loads((P/'aliases.json').read_text()):aliases[r['source_key']].add(r['player_master_id'])
 results=[];qb_results=defaultdict(lambda:{'name':None,'id':None,'teams':set(),'contests':set(),'slates':set(),'cohorts':{p:Counter() for p in POPS}});winner_rosters=[]
 for contest in inv['contests']:
  cid=contest['contest_id'];path=P/'inputs'/(cid+'.json.gz')
  if not path.exists():continue
  payload=json.load(gzip.open(path,'rt'));season,week=contest['season'],contest['week'];sal=[r for r in salaries if r['season']==season and r['week']==week and r['slate'].upper()=='SUNDAY_MAIN'];resolver,cache=build_players(sal,[],{})
  teams={team(r['team']) for r in sal};games={frozenset((team(r['team']),team(r['opponent']))) for r in sal if r.get('team') and r.get('opponent')};actual_qb={};actual_qb_missing=[]
  for g in schedule:
   if (g['season'],g['week'])!=(season,week) or frozenset((team(g['home_team']),team(g['away_team']))) not in games:continue
   raw=g['raw_row_json']
   for side in ['home','away']:
    tm=team(g[side+'_team']);native=raw.get(side+'_qb_id');ids=aliases.get(native,set());match=[s for s in sal if s['position']=='QB' and team(s['team'])==tm and s.get('player_master_id') in ids]
    identities={s['player_master_id'] for s in match}
    if len(identities)==1:actual_qb[tm]=dict(id=next(iter(identities)),name=match[0]['player_name'],team=tm,native=native,game_id=g['game_id'],schedule_ingest=g['ingest_run_id'])
    else:actual_qb_missing.append(dict(team=tm,native_id=native,reason='native_alias_or_scoped_QB_membership_missing'))
  counts=empty();seen={p:set() for p in POPS};audit=Counter();available=Counter();qc={tm:{pop:Counter() for pop in POPS} for tm in actual_qb}
  for row in payload['entries']:
   weights=dict(field=row['n'],winner=row.get('winner',0),top_1=row.get('top_1',0))
   for pop,w in weights.items():counts[pop]['raw_entries']+=w
   players,error=parse(row['lineup_text'],resolver)
   if error:audit[error]+=row['n'];continue
   flags,wr,rostered_qb=classify(players);sig=hashlib.sha256('|'.join(sorted(p['id'] for p in players)).encode()).hexdigest()
   for pop,w in weights.items():
    if not w:continue
    counts[pop]['valid_entries']+=w;counts[pop]['entry'].update({k:w for k,v in flags.items() if v})
    if sig not in seen[pop]:
     seen[pop].add(sig);counts[pop]['unique_rosters']+=1;counts[pop]['unique'].update({k:1 for k,v in flags.items() if v})
    for tm,context in actual_qb.items():
     c=qc[tm][pop];c['applicable_entries']+=w
     if wr[tm]>=1:c['at_least_one_wr']+=w
     if wr[tm]>=2:c['two_wr']+=w
     if rostered_qb['id']==context['id']:
      c['own_qb_entries']+=w
      if wr[tm]>=2:c['two_wr_and_actual_qb']+=w
   if weights['winner']:
    winner_rosters.append(dict(contest_id=cid,season=season,week=week,entries=weights['winner'],rank=1,canonical_roster=sig,players=[{k:p[k] for k in ['id','team','position','salary']} for p in players],flags=flags,observed_roster_qb=rostered_qb['id']))
  for tm,context in actual_qb.items():
   key=str(season)+'|'+context['id'];dest=qb_results[key];dest.update(name=context['name'],id=context['id'],season=season);dest['teams'].add(tm);dest['contests'].add(cid);dest['slates'].add((season,week))
   for pop in POPS:dest['cohorts'][pop].update(qc[tm][pop])
  out=dict(contest=contest,source_scope=contest['slate_id'],analysis_scope='SUNDAY_MAIN',scope_correction='existing verified nine-slot Classic + multi-game Main salary membership' if contest['slate_id']!='SUNDAY_MAIN' else None,cohorts=counts,audit=dict(audit),pool_games=len(games),actual_qbs=actual_qb,actual_qb_unresolved=actual_qb_missing,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest());results.append(out)
  print(cid,'winners',counts['winner']['entry']['two_wr'],'/',counts['winner']['valid_entries'],'fieldvalid',counts['field']['valid_entries'],flush=True)
 serial=[]
 for q in qb_results.values():
  q={**q,'teams':sorted(q['teams']),'contests':sorted(q['contests']),'slates':sorted(q['slates'])};serial.append(q)
 (P/'results.json').write_text(json.dumps(dict(contests=results,qb_contexts=serial,winners=winner_rosters),indent=2)+'\n')
if __name__=='__main__':main()
