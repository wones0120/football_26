"""Bounded feasibility only; authenticated approved caches, no raw adapters/DB."""
from collections import Counter,defaultdict
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,time


def load(ref):
    raw=Path(ref['path']).read_bytes()
    assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256']
    return json.loads(raw)


def main():
    start=time.monotonic();started=datetime.now(timezone.utc).isoformat()
    parent=json.loads(Path('research/personnel_package_continuity_20261020/v1/actual_receipt.json').read_text())
    coverage=json.loads(Path('research/participation_defense_catalog_20261020/v1/actual_receipt.json').read_text())
    outputs=[]
    for entry,defentry in zip(parent['outputs'],coverage['outputs']):
        assert entry['season']==defentry['season']
        p=load(entry['full_ref']);d=load(defentry['full_ref'])
        units={uid:tuple((n,r) for n,r in v['native_participant_roles'] if r in {'C','G','T'}) for uid,v in p['unit_registry'].items()}
        eligible={(r['game_id'],r['play_id']):r for r in d['event_basis']}
        bygame=defaultdict(Counter);cohorts=defaultdict(set);unknown=Counter();counts=Counter()
        for r in p['event_basis']:
            e=eligible.get((r['game_id'],r['play_id']))
            if e is None:
                if r['physical_membership'] is None:counts['possible_physical_not_in_old_DB_basis']+=1
                continue
            counts['candidate_DB_rows']+=1
            g=(r['game_id'],r['team'])
            if e['eligible_nonspike_dropback'] is not True or r['physical_membership'] is not True or not r['unit_id'] or e['offense']!=r['team']:
                unknown[g]+=1;continue
            unit=units[r['unit_id']]
            if len(unit)!=5 or Counter(role for _,role in unit)!=Counter(C=1,G=2,T=2):
                unknown[g]+=1;counts['known_DB_without_C1G2T2']+=1;continue
            bygame[g][unit]+=1;cohorts[g].add(unit);counts['known_native_exact_five_DBs']+=1
        exact_games=sample_games=positive=0
        for r in p['continuity_rows']:
            if r['first_game_not_applicable']:continue
            now=(r['game_id'],r['team']);prior=(r['prior_scheduled_game_id'],r['team'])
            if not bygame[now] or not bygame[prior]:continue
            sample_games+=1
            retained=sum(n for unit,n in bygame[now].items() if unit in cohorts[prior]);positive+=retained
            exact_games+=not unknown[now] and (not unknown[prior] or all(unit in cohorts[prior] for unit in bygame[now]))
        outputs.append(dict(season=p['season'],counts=dict(counts),native_only_potential_comparison_games=sample_games,native_only_potential_exact_comparison_games=exact_games,positive_same_OL_unit_DBs=positive,warning='Feasibility upper bound only: missing-offense/source-only/all-potential/identity masks not yet fully evaluated; no feature approval.',source_refs=dict(personnel=entry['full_ref'],dropback=defentry['full_ref'])))
    result=dict(started_at=started,ended_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-start,outputs=outputs,raw_rows_decoded=0,models=0,DB_reads=0,IDs_promoted=0)
    Path('research/protection_ol_package_continuity_20261020/v1/compact_feasibility.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
