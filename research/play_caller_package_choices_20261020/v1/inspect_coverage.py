"""Two-game approved-cache feasibility only, zero feature promotion."""
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter,defaultdict
import json,hashlib,time
from backend.app.product_services.personnel_package_continuity import load_package_physical_component
from backend.app.product_services.environment_context_evidence import _call
from backend.app.product_services.fumble_event_components import _flag


def main():
    start=datetime.now(timezone.utc);tick=time.monotonic();receipt=json.loads(Path('research/personnel_package_continuity_20261020/v1/actual_receipt.json').read_text())
    o=next(o for o in receipt['outputs'] if o['season']==2023);s=next(s for s in receipt['source_inputs'] if s['season']==2023)
    ref=o['full_ref'];raw=Path(ref['path']).read_bytes();assert len(raw)==ref['bytes'] and hashlib.sha256(raw).hexdigest()==ref['sha256'];p=json.loads(raw)
    physical=load_package_physical_component(s['physical_component_ref'],cutoff=start)
    gids=['2023_10_DEN_BUF','2023_11_NYJ_BUF'];events={(e['game_id'],e['play_id']):e for e in p['event_basis'] if e['game_id'] in gids};calls=defaultdict(Counter);unknown=Counter()
    for r in physical['rows']:
        if r['game_id'] not in gids or r.get('posteam')!='BUF':continue
        key=r['game_id'],str(int(r['play_id']));e=events.get(key)
        if e is None:continue
        if e['physical_membership'] is not True or e['unit_id'] is None:unknown[r['game_id']]+=1;continue
        u=p['unit_registry'][e['unit_id']];package=str(u['role_count_tuple'])
        event=dict(status='included',raw_flags=r,opportunities=[dict(channel=channel) for flag,channel in [('pass_attempt','pass_attempts'),('rush_attempt','rush_attempts')] if _flag(r.get(flag)) is True])
        call='spike' if _flag(r.get('qb_spike')) is True else 'kneel' if _flag(r.get('qb_kneel')) is True else _call(event)
        calls[r['game_id']][package,call]+=1
        if call=='unknown':unknown[r['game_id']]+=1
    games=[]
    for gid in gids:
        g=next(g for g in p['game_rows'] if g['game_id']==gid and g['team']=='BUF')
        games.append(dict(game_id=gid,parent_counters={k:v for k,v in g.items() if k!='unit_snaps'},joint_cells=[dict(literal_package=package,call=call,count=n) for (package,call),n in sorted(calls[gid].items())],unknown_call_or_unit_events=unknown[gid]))
    packages=[{package for package,call in calls[g] if call in ('pass','rush')} for g in gids]
    shared=sorted(set.intersection(*packages));r=dict(status='two_game_feasibility_zero_promotions',started_at=start.isoformat(),completed_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-tick,games=games,shared_position_count_tuples=shared,source_refs=dict(personnel=ref,physical=s['physical_component_ref']),caution='Calling taxonomy reused for feasibility; exact change contract and canonical/full unknown propagation still require pure producer/tests/review')
    Path('research/play_caller_package_choices_20261020/v1/coverage_feasibility.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r))

if __name__=='__main__':main()
