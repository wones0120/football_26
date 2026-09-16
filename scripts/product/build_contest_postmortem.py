"""Build a read-only contest postmortem from reconciled archive observations."""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sqlalchemy import text
from Database.player_identity import strip_name_suffix
from backend.app.product_services.ownership import OwnershipService


def signature(players):
    return sorted((p['player_id'], p.get('roster_position') == 'CPT') for p in players)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path)
    parser.add_argument('--season',type=int,required=True)
    parser.add_argument('--week',type=int,required=True)
    args=parser.parse_args()
    service=OwnershipService()
    params={'season':args.season,'week':args.week}
    with service.engine.connect() as connection:
        saved=[dict(r) for r in connection.execute(text('''SELECT l.lineup_id,l.optimizer_run_id,l.projected_mean,
            o.slate_id,o.projection_run_id,o.created_at,o.objective,o.strategy,
            lp.player_id,lp.roster_position,lp.projection,lp.player_json
            FROM target.lineup l JOIN target.optimizer_run o USING(optimizer_run_id)
            JOIN target.lineup_player lp USING(lineup_id) WHERE o.season=:season AND o.week=:week'''),params).mappings()]
        projections=[dict(r) for r in connection.execute(text('''SELECT * FROM target.player_projection
            WHERE season=:season AND week=:week'''),params).mappings()]
    by_lineup=defaultdict(list)
    for row in saved: by_lineup[row['lineup_id']].append(row)
    summaries=[]
    for contest in json.loads(args.manifest.read_text()):
        observations=json.loads((args.manifest.parent/'review'/f"{contest['contest_id']}.json").read_text())
        for entry in contest['own_entries']:
            players=[]
            for player in service._parse_lineup(entry['lineup']):
                candidates=[r for r in observations if strip_name_suffix(r['player_display_name'])==strip_name_suffix(player['player_display_name']) and r['resolution_status']=='resolved']
                # Classic FLEX entries use the natural-position side-table label.
                if contest['format']=='showdown':
                    candidates=[r for r in candidates if r['roster_position']==player['roster_position']]
                else:
                    positions={'RB','WR','TE'} if player['roster_position']=='FLEX' else {player['roster_position']}
                    candidates=[r for r in candidates if r['roster_position'] in positions]
                ids={r['player_id'] for r in candidates}
                if len(ids)!=1:
                    raise ValueError(f"Entry player lacks unique reviewed identity: {player}")
                points={r['fpts'] for r in candidates}
                if len(points)!=1: raise ValueError(f"Conflicting actual points: {player}")
                players.append({**player,'player_id':next(iter(ids)), 'actual_points':float(next(iter(points))),
                                'actual_ownership':float(candidates[0]['pct_drafted'])})
            if abs(sum(p['actual_points'] for p in players)-entry['points'])>0.02:
                raise ValueError(f"Slot-weighted scores fail to reconcile for {entry['entry_id']}")
            matches=[rows for rows in by_lineup.values() if rows[0]['slate_id']==contest['slate'] and signature(rows)==signature(players)]
            matches.sort(key=lambda rows: rows[0]['created_at'],reverse=True)
            # When no exact saved lineup exists, use the most recent projection before
            # the slate's first kickoff, with both creation time and cutoff checked.
            kickoffs=[]
            with service.engine.connect() as connection:
                games=connection.execute(text('''SELECT DISTINCT game_info FROM curated_salary
                    WHERE season=:season AND week=:week AND upper(slate)=upper(:slate)'''), {**params,'slate':contest['slate']}).scalars().all()
            import re
            from datetime import datetime
            from zoneinfo import ZoneInfo
            for game in games:
                found=re.search(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}[AP]M)',game or '')
                if found: kickoffs.append(datetime.strptime(found[1],'%m/%d/%Y %I:%M%p').replace(tzinfo=ZoneInfo('America/New_York')))
            lock=min(kickoffs) if kickoffs else None
            matches=[rows for rows in matches if lock and rows[0]['created_at']<lock]
            selected=matches[0] if matches else None
            projection_run=selected[0]['projection_run_id'] if selected else None
            if not projection_run:
                eligible=[p for p in projections if p['slate_id']==contest['slate'] and lock and p['created_at']<lock and p['data_cutoff_at'] and p['data_cutoff_at']<lock]
                if not eligible: raise ValueError('No verified prelock projection reference')
                projection_run=max(eligible,key=lambda p:p['created_at'])['projection_run_id']
            projection_by_id={p['player_id']:p for p in projections if p['projection_run_id']==projection_run}
            saved_by_id={p['player_id']:p for p in selected or []}
            for player in players:
                canonical=projection_by_id.get(player['player_id'])
                chosen=saved_by_id.get(player['player_id'])
                multiplier=1.5 if player['roster_position']=='CPT' else 1
                player['projected_points']=float(chosen['projection']) if chosen else float(canonical['mean'])*multiplier if canonical else None
                player['residual']=None if player['projected_points'] is None else player['actual_points']-player['projected_points']
            summaries.append({**entry,'contest_id':contest['contest_id'],'field_size':contest['field_size'],
                'slate':contest['slate'],'format':contest['format'],'projection_run_id':projection_run,
                'projection_basis':'exact_saved_lineup' if selected else 'latest_prelock_reference',
                'matched_lineup_ids':[rows[0]['lineup_id'] for rows in matches],
                'strategy': selected[0]['strategy'] if selected else None,
                'projected_points':sum(p['projected_points'] for p in players) if all(p['projected_points'] is not None for p in players) else None,
                'players':players})
    output=args.manifest.parent/'postmortem.json'
    output.write_text(json.dumps(summaries,indent=2,default=str)+'\n')
    for item in summaries:
        print(json.dumps({k:v for k,v in item.items() if k not in {'lineup','players','matched_lineup_ids'}}))
        print('matches',len(item['matched_lineup_ids']))
        print('players', [(p['player_display_name'],round(p['actual_points'],2),round(p['projected_points'],2) if p['projected_points'] is not None else None) for p in item['players']])

if __name__=='__main__': main()
