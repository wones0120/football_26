"""Offline game-day identity/delta and core-exposure audits; no model tuning."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import csv
from datetime import UTC, datetime
import json
from pathlib import Path

from backend.app.product_services.classic_prospective import digest_payload
from scripts.finalize_showdown_prelock_shadow import read_frozen
from scripts.research_showdown_prelock import joint_portfolio, signature, validate_lineup


def save(path, payload):
    if path.exists():
        raise ValueError(f'Immutable output already exists: {path}')
    path.write_text(json.dumps({'payload':payload,'sha256':digest_payload(payload)},indent=2,sort_keys=True)+'\n')


def verify_salary_rows(rows, salaries):
    """Join exclusively by DK native slot ID; verify all slot attributes."""
    by_slot = {str(row['source_player_key']):row for row in salaries if row['source_system']=='draftkings'}
    if len({row['ID'] for row in rows}) != len(rows) or not rows:
        raise ValueError('Empty or duplicate native slot IDs')
    pairs = {}
    audit = []
    for row in rows:
        stored = by_slot.get(row['ID'])
        if stored is None or not stored['player_master_id']:
            raise ValueError('Unresolved DK native slot: '+row['ID'])
        expected = {'Name':'player_name','TeamAbbrev':'team','Position':'position','Roster Position':'roster_position','Game Info':'game_info'}
        if any(row[key] != str(stored[value]) for key,value in expected.items()) or int(row['Salary'])!=stored['salary'] or (row.get('Status') or None)!=(stored.get('player_status') or None):
            raise ValueError('Native slot attributes differ: '+row['ID'])
        pid = str(stored['player_master_id'])
        if row['Roster Position'] not in {'CPT','FLEX'} or row['Roster Position'] in pairs.setdefault(pid,{}):
            raise ValueError('Invalid or duplicate canonical roster slot')
        pairs[pid][row['Roster Position']] = row
        audit.append({'canonical_player_id':pid,**row})
    for pid, slots in pairs.items():
        if set(slots) != {'CPT','FLEX'} or int(slots['CPT']['Salary']) != 1.5*int(slots['FLEX']['Salary']):
            raise ValueError('Incomplete CPT/FLEX identity or salary pair: '+pid)
    if set(by_slot) != {row['ID'] for row in rows}:
        raise ValueError('Database salary universe differs from fresh file')
    return {'verified_slots':len(rows),'canonical_players':len(pairs),'all_pairs_verified':True,'rows':audit}


def freeze_changes(directory, overnight):
    old = read_frozen(overnight/'refreshed_database_freeze.json')['payload']
    new_envelope = read_frozen(directory/'refreshed_database_freeze.json');new = new_envelope['payload']
    with (directory/'DKSalaries_2026_4_THURSDAY_NIGHT.csv').open(encoding='utf-8-sig',newline='') as file:
        verification = verify_salary_rows(list(csv.DictReader(file)),new['salaries'])
    metadata = json.loads((directory/'draftkings_salary_download.json').read_text())
    verification.update({'source':metadata,'authenticated_account_session':False,'download_basis':'fresh official public DK endpoint; contest draft-group 154084 verified independently'})
    save(directory/'salary_verification.json',verification)
    fields = ('salary','dk_player_id','dk_captain_id','projection','p90','pregame_availability_probability','pregame_role_label','pregame_role_uncertain','pregame_start_probability','injury_status','player_status','projected_carries','projected_targets','snap_share_mean_3','game_total_line','team_spread_line','team_implied_total','ownership','captain_ownership','flex_ownership')
    prior = {row['player_id']:row for row in old['player_pool']}
    changes = []
    for row in new['player_pool']:
        old_row = prior[row['player_id']]
        for field in fields:
            before,after = old_row.get(field),row.get(field)
            if isinstance(before,(int,float)) and isinstance(after,(int,float)) and abs(before-after)<1e-9:continue
            if before == after:continue
            changes.append({'player_id':row['player_id'],'player':row['name'],'field':field,'old':before,'new':after,
                'source':'normal production projection/feature rebuild on fresh DK, Operations injury and official context',
                'observed_at':new['frozen_at'],'consequence':'changes eligibility' if 'availability' in field or field=='player_status' else 'changes lineup quality if projection/opportunity changed; ownership remains diagnostic'})
    old_weather = json.loads((overnight/'public_sources/weather_hourly.json').read_text())['properties']
    new_weather = json.loads((directory/'public_sources/weather_hourly.json').read_text())['properties']
    hours = lambda weather:[row for row in weather['periods'] if row['startTime'][:13] in {f'2026-10-01T{hour}' for hour in (20,21,22,23)}]
    result={'frozen_at':datetime.now(UTC).isoformat(),'before_portfolio_selection':True,'input_sha256':new_envelope['sha256'],
        'old_projection_run':old['projection_run_id'],'new_projection_run':new['projection_run_id'],
        'old_projection_rows':len(old['projections']),'new_projection_rows':len(new['projections']),
        'player_changes':changes,'weather_old':hours(old_weather),'weather_new':hours(new_weather),
        'weather_model_policy':'Fresh NWS evidence retained for readiness; no manual weather/projection adjustment.',
        'salary_changes':[{'slot':r['ID'],'name':r['Name'],'old':next(x for x in old['salaries'] if str(x['source_player_key'])==r['ID'])['player_status'],'new':r['Status']} for r in verification['rows'] if (next(x for x in old['salaries'] if str(x['source_player_key'])==r['ID'])['player_status'] or '')!=r['Status']],
        'ownership_status':'diagnostic only; same reliability policy as overnight',
        'inactives':'Unpublished at morning observation; availability 1 is pending-inactives, not a final-active assertion.'}
    save(directory/'changes_before_selection.json',result)
    print({'verified_slots':verification['verified_slots'],'changes':len(changes),'projection_rows':len(new['projections'])})


def metrics(records, indices):
    return {'count':len(indices),'ranks':[records[i]['rank'] for i in indices],
            'total_selector':sum(records[i]['single_entry_score'] for i in indices),
            'total_mean':sum(records[i]['mean'] for i in indices),'total_p90':sum(records[i]['p90'] for i in indices),
            'theses':dict(Counter(records[i]['research_thesis'] for i in indices)),
            'captains':dict(Counter(records[i]['captain'] for i in indices))}


def core_sensitivity(records, lineups, player, fragile_limits):
    kwargs = {'different_captains':True,'different_theses':True,'max_shared':4,'exposure_limits':fragile_limits}
    containing = [i for i,lineup in enumerate(lineups) if any(str(row['player_id'])==player for row in lineup)]
    all_three = joint_portfolio([records[i] for i in containing],[lineups[i] for i in containing],3,**kwargs)
    baseline = metrics(records,[containing[i] for i in all_three])
    capped = joint_portfolio(records,lineups,3,**{**kwargs,'exposure_limits':{**fragile_limits,player:2}})
    alternative = metrics(records,capped)
    feasible = baseline['count']==alternative['count']==3
    costs = {field:baseline['total_'+field]-alternative['total_'+field] if feasible else None for field in ('selector','mean','p90')}
    return {'player_id':player,'100_percent':baseline,'maximum_two':alternative,'three_entry_feasible':feasible,'costs':costs,'eligibility_tolerance':.10}


def analyze(directory):
    envelope = read_frozen(directory/'quality_shadow.json');data=envelope['payload']
    records,lineups=data['all_candidates'],data['raw_lineups'];best=records[0]['single_entry_score']
    for lineup in lineups:validate_lineup(lineup)
    eligible = [i for i,row in enumerate(records) if best-row['single_entry_score'] <= .10+1e-8]
    er,el = [records[i] for i in eligible],[lineups[i] for i in eligible]
    limits=data['research_policy']['primary_fragile_limits']
    core = [row for row in data['prepared_pool'] if row['name'] in {'DK Metcalf','Deshaun Watson','Jerry Jeudy'}]
    sensitivities = {row['name']:core_sensitivity(er,el,str(row['player_id']),limits) for row in core}
    unconstrained = joint_portfolio(er,el,3)
    primary = [rank-1 for rank in data['primary_three_ranks']]
    comparisons={'A_unconstrained':metrics(er,unconstrained),'B_captain_only':metrics(records,[r-1 for r in data['captain_only_three_ranks']]),'C_primary':metrics(records,primary)}
    old_records=data['overnight_three_rescored'];comparisons['D_overnight_on_fresh_model']=metrics(old_records,list(range(len(old_records))))
    for result in comparisons.values():
        result['selector_cost_vs_A']=comparisons['A_unconstrained']['total_selector']-result['total_selector'] if result['count']==3 else None
    frontier = {}
    for row in records:
        group=frontier.setdefault(row['captain'],{'best':row,'counts':{str(t):0 for t in (.05,.10,.15,.20,.30)}})
        for t in (.05,.10,.15,.20,.30):group['counts'][str(t)]+=best-row['single_entry_score'] <= t+1e-8
    thesis_frontier={}
    for row in records:
        group=thesis_frontier.setdefault(row['research_thesis'],{'best':row,'counts':{str(t):0 for t in (.05,.10,.15,.20,.30)},'captains':set(),'allocations':set()})
        group['captains'].add(row['captain']);group['allocations'].add(str(row['team_counts']))
        for t in (.05,.10,.15,.20,.30):group['counts'][str(t)]+=best-row['single_entry_score'] <= t+1e-8
    for group in thesis_frontier.values():group['captains']=sorted(group['captains']);group['allocations']=sorted(group['allocations'])
    cheap={}
    for player in data['prepared_pool']:
        if player['salary']>4000:continue
        pid=str(player['player_id']);containing=[r for r,l in zip(records,lineups) if any(str(p['player_id'])==pid for p in l)];avoiding=[r for r,l in zip(records,lineups) if all(str(p['player_id'])!=pid for p in l)]
        cheap[player['name']]={'player':player,'best_containing':containing[0] if containing else None,'best_avoiding':avoiding[0] if avoiding else None,'avoidance_cost_vs_global':best-avoiding[0]['single_entry_score'] if avoiding else None}
    primary_lineups=[lineups[i] for i in primary]
    exposure=Counter(row['name'] for lineup in primary_lineups for row in lineup)
    overlap=[{'left':i+1,'right':j+1,'shared':len({str(r['player_id']) for r in primary_lineups[i]} & {str(r['player_id']) for r in primary_lineups[j]})} for i in range(len(primary_lineups)) for j in range(i+1,len(primary_lineups))]
    qb={}
    for player in data['prepared_pool']:
        if player['position']!='QB':continue
        pid=str(player['player_id']);flex=[r for r,l in zip(records,lineups) if any(str(p['player_id'])==pid and p['roster_position']=='FLEX' for p in l)]
        qb[player['name']]={'rushing_carries_mean_3':player.get('carries_mean_3'),'salary_premium':player['salary']*.5,'cpt':frontier[player['name']]['best'],'flex':flex[0],'cost_cpt_vs_flex':flex[0]['single_entry_score']-frontier[player['name']]['best']['single_entry_score']}
    result={'frozen_at':datetime.now(UTC).isoformat(),'quality_sha256':envelope['sha256'],'candidate_count':len(records),'eligible_count':len(eligible),'all_candidates_legal':True,'comparisons':comparisons,'core_sensitivities':sensitivities,'captain_frontier':frontier,'thesis_frontier':thesis_frontier,'cheap':cheap,'qb':qb,'primary_exposure':dict(exposure),'primary_overlap':overlap,'primary_lineups':primary_lineups,'primary_records':[records[i] for i in primary]}
    save(directory/'decision_audit.json',result)
    print(json.dumps({'comparisons':comparisons,'core_sensitivities':sensitivities},indent=2))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);parser.add_argument('--overnight',type=Path);parser.add_argument('--changes',action='store_true');args=parser.parse_args()
    if args.changes:freeze_changes(args.directory,args.overnight)
    else:analyze(args.directory)


if __name__=='__main__':main()
