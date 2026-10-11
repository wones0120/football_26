"""Offline expanded-candidate shadow; production services never import this module."""
from __future__ import annotations
import argparse
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from backend.app.product_services.classic_strategy_contract import execute_strategy_contract, portfolio_audit, digest
from backend.app.product_services.gpp_recommendation import candidate_id, evaluate_candidates
from backend.app.product_services.optimizer_effectiveness import chronological_validation
from scripts.audit_sunday_projection_generation import recommend

POLICY='single_gpp_expanded_candidates_shadow_v1'
FORBIDDEN={'actual_points','actual_score','actual_rank','postgame'}


def finite(value):
    if isinstance(value,bool): raise ValueError('Boolean forecast')
    value=float(value)
    if not math.isfinite(value): raise ValueError('Non-finite forecast')
    return value


def projection_contract(contract):
    result=deepcopy(contract)
    result.pop('sha256')
    result['execution_mode']='RESEARCH_SHADOW'
    result['strategy_label']=contract['strategy_id']+' + single recommendation coverage probe'
    weights=result['effective']['resolved_config']['objective_weights']
    for key in weights: weights[key]=1.0 if key=='projection' else 0.0
    result['deviations']=['Projection-only candidate coverage probe; same frozen players and all original lineup/portfolio constraints.']
    result['effective_sha256']=digest(result['effective']);result['sha256']=digest(result)
    return result


def compare(rosters,source):
    for roster in rosters:
        if any(FORBIDDEN.intersection(row) for row in roster): raise ValueError('Outcome-contaminated roster')
    return evaluate_candidates(rosters,run_id=source['optimizer_run_id'],season=source.get('season',2026),
        week=source.get('week',5),slate=source.get('slate_id','SUNDAY_MAIN'),contest_format=source.get('contest_format','classic'),
        projection_run_id=source['projection_run_id'],data_cutoff_at=source['data_cutoff_at'])


def snapshot(source,control,challenger,kickoff):
    completed=datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(kickoff)<=datetime.now(timezone.utc): raise ValueError('Slate already locked')
    def arm(roster):
        frozen=[dict(p,projection=p.get('baseline_projection',p['projection'])) for p in roster]
        return dict(roster=frozen,forecast_points=sum(p['projection'] for p in frozen),candidate_id=candidate_id(frozen),completed_at=completed)
    return dict(season=source.get('season',2026),week=source.get('week',5),slate=source.get('slate_id','SUNDAY_MAIN'),
        contest_format=source.get('contest_format','classic'),source_run_id=source['optimizer_run_id'],
        label=('Classic' if source.get('contest_format','classic')=='classic' else 'Captain')+' single GPP shortlist shadow',
        first_kickoff_at=kickoff,forecast_basis='unconditioned_slot_weighted',policy=POLICY,
        projection_run_id=source['projection_run_id'],data_cutoff_at=source['data_cutoff_at'],
        arms={'control':arm(control),'expanded_candidates':arm(challenger)})


def classic(source):
    params=source['constraint_config_json'];contract=params['effective_strategy_contract']
    metadata=params['strategy_runtime']['classic_run_input_snapshot']['payload']['metadata']
    if (metadata['season'],metadata['week'],metadata['slate']) != (2026,5,'SUNDAY_MAIN'):
        raise ValueError('This predeclared Classic experiment is limited to 2026 Week 5 Sunday Main')
    saved=params['portfolio_controls_report']['candidate_rosters']
    rows=params['strategy_runtime']['classic_run_input_snapshot']['payload']['final_solver_rows']
    portfolios={};all_rosters=[]
    for label,current in [('control',contract),('projection_probe',projection_contract(contract))]:
        print('Classic:',label,flush=True)
        result=execute_strategy_contract(current)
        proof=portfolio_audit(contract,result.lineups,trace=result.selection_trace)
        if result.status!='completed' or proof['validation']['status']!='verified': raise ValueError('Original constraints did not pass')
        rec,rosters=recommend(result,source,rows)
        if label=='control':
            if [sorted(p['player_id'] for p in roster) for roster in rosters]!=[sorted(r['player_ids']) for r in saved]: raise ValueError('Control portfolio parity failed')
            if rec['recommended']['candidate_id']!=params['gpp_recommendation']['recommended']['candidate_id']: raise ValueError('Control recommendation parity failed')
            control=rosters[rec['recommended']['lineup_number']-1]
        portfolios[label]=dict(contract=current,validation=proof,recommendation=rec,rosters=rosters)
        all_rosters.extend(rosters)
    comparison=compare(all_rosters,source)
    challenger=all_rosters[comparison['recommended']['lineup_number']-1]
    timing=chronological_validation(dict(data_cutoff_at=source['data_cutoff_at'],optimizer_created_at=datetime.now(timezone.utc)),
        dict(status='slate_source_pool',candidates=saved))
    if timing['status']!='predecision': raise ValueError('Missing prelock evidence')
    return dict(policy=POLICY,portfolios=portfolios,comparison=comparison,
        changed=candidate_id(control)!=candidate_id(challenger),live_selection_changed=False,
        snapshot=snapshot(source,control,challenger,timing['first_saved_kickoff_at']))


def reconstruct(candidate,pool,native,controls):
    if FORBIDDEN.intersection(candidate) or any(FORBIDDEN.intersection(p) for p in candidate['players']):
        raise ValueError('Outcome-contaminated candidate')
    if candidate.get('comparison_basis')!='common_baseline': raise ValueError('Unknown comparison basis')
    roster=[]
    for p in candidate['players']:
        base=pool[p['player_id']];slot=p['slot']
        if slot not in {'CPT','FLEX'}: raise ValueError('Invalid slot')
        multiplier=1.5 if slot=='CPT' else 1.0
        dk=str(base['dk_captain_id'] if slot=='CPT' else base['dk_player_id'])
        salary=native[dk]
        if salary['Roster Position']!=slot: raise ValueError('Native salary slot mismatch')
        roster.append(dict(player_id=base['player_id'],name=base['name'],player_team=base['player_team'],
            position=base['position'],roster_position=slot,dk_player_id=str(base['dk_player_id']),dk_captain_id=str(base['dk_captain_id']),
            salary=finite(salary['Salary']),projection=finite(base['projection'])*multiplier,
            p90=finite(base['p90'])*multiplier,game_id=base['game_id'],
            official_availability_status=base.get('official_availability_status') or base.get('injury_status')))
    ids={p['player_id'] for p in roster}
    if len(ids)!=6 or len(roster)!=6 or sum(p['roster_position']=='CPT' for p in roster)!=1: raise ValueError('Invalid canonical roster')
    captain=next(p for p in roster if p['roster_position']=='CPT')
    if len({p['player_team'] for p in roster})!=2: raise ValueError('Both teams required')
    if set(controls.get('exclude_player_ids') or []) & ids or not set(controls.get('locked_player_ids') or []).issubset(ids): raise ValueError('User player constraints violated')
    if captain['player_id'] in (controls.get('flex_only_player_ids') or []): raise ValueError('Flex-only preference violated')
    qbs=sum(p['position']=='QB' for p in roster)
    if controls.get('no_qbs') and qbs or controls.get('no_two_qbs') and qbs>1: raise ValueError('QB preference violated')
    if controls.get('no_qb_captain') and captain['position']=='QB': raise ValueError('QB captain preference violated')
    if controls.get('captain_positions') and captain['position'] not in controls['captain_positions']: raise ValueError('Captain position preference violated')
    if controls.get('exclude_questionable') and any(str(p.get('official_availability_status') or '').upper() in {'Q','QUESTIONABLE'} for p in roster): raise ValueError('Questionable exclusion violated')
    for field,metric in [('projection','baseline_mean'),('p90','baseline_p90'),('salary','salary')]:
        if not math.isclose(sum(p[field] for p in roster),finite(candidate[metric]),rel_tol=0,abs_tol=1e-6): raise ValueError('Frozen aggregate mismatch: '+metric)
    return roster


def captain_allowed(roster):
    """Research-only slot restriction: QB FLEX players remain eligible."""
    return not any(p['roster_position']=='CPT' and p['position']=='QB' for p in roster)


def wr_rb_captain_allowed(roster):
    """WR Captain requires same-team QB FLEX; RB Captain requires no QB."""
    captains=[p for p in roster if p['roster_position']=='CPT']
    if len(captains)!=1: return False
    captain=captains[0]
    if captain['position']=='RB': return True
    return captain['position']=='WR' and bool(captain.get('player_team')) and any(
        p['roster_position']=='FLEX' and p['position']=='QB'
        and p.get('player_team')==captain['player_team'] for p in roster)


def captain(source, *, no_qb_captain=False, wr_rb_captain=False):
    if no_qb_captain and wr_rb_captain: raise ValueError('Choose one shadow policy')
    evidence=source['showdown_evidence_snapshot'];pool={p['player_id']:p for p in evidence['player_pool']}
    origins={(p['salary_source_path'],p['salary_source_checksum']) for p in pool.values()}
    if len(origins)!=1: raise ValueError('Expected one frozen native salary source')
    path,sha=next(iter(origins));raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha: raise ValueError('Salary source checksum mismatch')
    values=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()));native={p['ID']:p for p in values}
    if len(native)!=len(values): raise ValueError('Duplicate native salary IDs')
    rec=compare(source['rosters'],source)
    if rec['recommended']['candidate_id']!=source['gpp_recommendation']['recommended']['candidate_id']: raise ValueError('Captain control parity failed')
    control=source['rosters'][rec['recommended']['lineup_number']-1]
    candidates=source['candidate_selection']['ranked_metrics']
    eligible=[c for c in candidates if c.get('quality_eligible') is True and c.get('baseline_constraint_survives') is True]
    if not eligible: raise ValueError('No explicitly feasible candidate')
    expanded=[reconstruct(c,pool,native,source['controls']) for c in eligible]
    # Incumbent is never lost when broadening coverage. Every expanded roster must be export-valid.
    for roster in expanded:
        if not compare([roster],source)['recommended']: raise ValueError('Expanded roster failed export validation')
    all_rosters=[control,*expanded];comparison=compare(all_rosters,source)
    challenger=all_rosters[comparison['recommended']['lineup_number']-1]
    unrestricted=challenger
    if no_qb_captain or wr_rb_captain:
        predicate=wr_rb_captain_allowed if wr_rb_captain else captain_allowed
        allowed=[r for r in all_rosters if predicate(r)]
        if not allowed: raise ValueError('No feasible non-QB Captain candidate')
        comparison=compare(allowed,source)
        challenger=allowed[comparison['recommended']['lineup_number']-1]
    selected=next((c for c,r in zip(eligible,expanded) if candidate_id(r)==candidate_id(challenger)),None)
    kicks=[g['kickoff_at'] for g in source['prepared_input_evidence']['games']]
    kickoff=min(datetime.fromisoformat(k) for k in kicks).isoformat()
    frozen=snapshot(source,control,challenger,kickoff)
    if no_qb_captain or wr_rb_captain:
        arm_label='wr_rb_captain' if wr_rb_captain else 'no_qb_captain'
        frozen['policy']=arm_label+'_shadow_v1'
        frozen['label']='WR/RB Captain shadow; WR requires same-team QB' if wr_rb_captain else 'Captain no-QB Captain shadow (QB FLEX eligible)'
        frozen['arms'][arm_label]=frozen['arms'].pop('expanded_candidates')
        frozen['arms']['unrestricted_shortlist']=snapshot(source,control,unrestricted,kickoff)['arms']['expanded_candidates']
    return dict(policy=frozen['policy'],candidate_count=len(candidates),eligible_count=len(eligible),controls=source['controls'],
        comparison=comparison,challenger_audit=selected,changed=candidate_id(control)!=candidate_id(challenger),
        source_evidence_sha256=evidence['sha256'],native_salary_sha256=sha,live_selection_changed=False,
        snapshot=frozen)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format',choices=['classic','showdown'],required=True)
    parser.add_argument('--no-qb-captain',action='store_true',help='Captain-only research restriction; retain QB FLEX eligibility')
    parser.add_argument('--wr-rb-captain',action='store_true',help='WR/RB Captain only; WR requires same-team QB FLEX')
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise ValueError('Refusing to overwrite frozen shadow')
    source=json.loads(args.source.read_text())
    if (args.no_qb_captain or args.wr_rb_captain) and args.format!='showdown': raise ValueError('Captain-only experiment')
    result=classic(source) if args.format=='classic' else captain(source,no_qb_captain=args.no_qb_captain,wr_rb_captain=args.wr_rb_captain)
    result['source_file_sha256']=hashlib.sha256(args.source.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,default=str,allow_nan=False)+'\n')
    print(json.dumps(dict(changed=result['changed'],recommended=result['comparison']['recommended']),indent=2))

if __name__=='__main__':main()
