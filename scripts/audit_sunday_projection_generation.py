#!/usr/bin/env python3
"""Frozen-input Sunday Main projection audit and isolated generation shadows."""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
from backend.app.product_services.classic_strategy_contract import (
    execute_strategy_contract, portfolio_audit, validate_strategy_contract, digest)
from backend.app.product_services.gpp_recommendation import evaluate_candidates
from backend.app.product_services.optimizer_effectiveness import chronological_validation

ROLE_FIELDS=('pregame_expected_snaps','pregame_expected_routes','pregame_expected_carries',
    'pregame_expected_targets','pregame_red_zone_share','pregame_goal_line_share')
FIELDS=('player_id','name','position','player_team','salary','projection','predicted_p10','predicted_p50','p90',
    'projected_carries','projected_targets','projected_opportunity_source','role_confidence',
    'pregame_role_uncertain','official_availability_status','practice_participation',
    'practice_observed_at','availability_observed_at','role_observed_at','market_observed_at',
    'game_total_line','expected_workload_status','role_resolution_warning','calibration_sample_size',
    'calibration_method','snap_share_mean_3','target_share_mean_3','carry_share_mean_3',*ROLE_FIELDS)


def number(v):
    try:return float(v) if v is not None and math.isfinite(float(v)) else None
    except (TypeError,ValueError):return None


def replay_source(source):
    """Persist only the inputs consumed here, excluding nested runtime reports."""
    params=source['constraint_config_json']
    payload=params['strategy_runtime']['classic_run_input_snapshot']['payload']
    def rows(values):
        return [{k:r.get(k) for k in (*FIELDS,'dk_player_id')} for r in values]
    return dict(
        **{k:source[k] for k in ('optimizer_run_id','projection_run_id','data_cutoff_at')},
        constraint_config_json=dict(
            effective_strategy_contract=deepcopy(params['effective_strategy_contract']),
            gpp_recommendation=deepcopy(params['gpp_recommendation']),
            portfolio_controls_report={'candidate_rosters':deepcopy(params['portfolio_controls_report']['candidate_rosters'])},
            strategy_runtime={'classic_run_input_snapshot':{'payload':{
                'metadata':deepcopy(payload['metadata']), 'final_solver_rows':rows(payload['final_solver_rows'])}}},
            classic_evidence_snapshot={'player_pool':rows(params['classic_evidence_snapshot']['player_pool'])}))


def audit_rows(rows, chosen_ids, cutoff):
    checks=[]
    for row in rows:
        warnings=[]
        mean,p10,p50,p90=(number(row.get(k)) for k in ('projection','predicted_p10','predicted_p50','p90'))
        if mean is None or p90 is None or mean>p90:
            warnings.append('missing_or_inconsistent_mean_p90')
        if None not in (p10,p50,p90) and not p10<=p50<=p90:
            warnings.append('unordered_quantiles')
        if row.get('position') in {'RB','WR','TE'} and number(row.get('projected_targets')) is None:
            warnings.append('missing_projected_targets')
        if row.get('position')=='RB' and number(row.get('projected_carries')) is None:
            warnings.append('missing_projected_carries')
        future=[]
        for key in ('role_observed_at','availability_observed_at','practice_observed_at','market_observed_at'):
            value=row.get(key)
            if value in (None,'NaT','nan',''):continue
            try:
                clock=datetime.fromisoformat(str(value))
                if clock.tzinfo is None:
                    warnings.append('ambiguous_clock:'+key)
                elif clock>cutoff:future.append(key)
            except ValueError:warnings.append('invalid_clock:'+key)
        if future:warnings.append('evidence_after_cutoff:'+','.join(future))
        if row.get('role_resolution_warning'):warnings.append('role_resolution_warning')
        if row.get('pregame_role_uncertain'):warnings.append('role_uncertain')
        if str(row.get('official_availability_status') or '').upper() in {'OUT','DOUBTFUL','QUESTIONABLE','O','D','Q'}:
            warnings.append('availability_risk')
        checks.append(dict(**{k:row.get(k) for k in FIELDS},in_recommended_lineup=row['player_id'] in chosen_ids,
                           missing_explicit_role_fields=[k for k in ROLE_FIELDS if number(row.get(k)) is None],warnings=warnings))
    return dict(players=checks,count=len(rows),unique_ids=len({r['player_id'] for r in rows}),
        field_coverage={k:sum(number(r.get(k)) is not None for r in rows) for k in (*ROLE_FIELDS,'projected_carries','projected_targets')},
        warnings=dict(Counter(w for row in checks for w in row['warnings'])),
        limitations=['Frozen saved-input audit, not a fresh injury/news check or final entry clearance.',
                    'Missing explicit role fields do not imply the model has no historical role features.',
                    'Audits evidence completeness and consistency, not forecast accuracy before games finish.'])


def shadow_contract(source,arm):
    result=deepcopy(source)
    result.pop('sha256')
    result['execution_mode']='RESEARCH_SHADOW'
    result['strategy_label']=source['strategy_id']+' + '+arm
    cfg=result['effective']['resolved_config']
    if arm=='mean_led':
        weights=cfg['objective_weights']
        weights['projection']+=.20;weights['ceiling']-=.20
        result['deviations']=['Transfer 0.20 normalized objective weight from ceiling to projection; all other weights, inputs and constraints unchanged.']
    elif arm=='template_rotation':
        templates=cfg['stack_templates']
        cfg['stack_templates']=templates[1:]+templates[:1]
        result['deviations']=['Rotate existing compatible stack-template cycle by one slot; all scores and user constraints unchanged.']
    else:raise ValueError('Unknown shadow arm')
    result['effective_sha256']=digest(result['effective']);result['sha256']=digest(result)
    return result


def recommend(result,source,solver_rows):
    lookup={r['player_id']:r for r in solver_rows}
    rosters=[]
    for lineup in result.lineups:
        rosters.append([dict(player_id=p.player_id,dk_player_id=lookup[p.player_id]['dk_player_id'],
            name=p.name,position=p.position,roster_position=p.position,salary=p.salary,
            projection=p.projection,p90=p.ceiling) for p in lineup])
    rec=evaluate_candidates(rosters,run_id=source['optimizer_run_id'],season=2026,week=5,slate='SUNDAY_MAIN',
                            contest_format='classic',projection_run_id=source['projection_run_id'],data_cutoff_at=source['data_cutoff_at'])
    return rec,rosters


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--output-dir',type=Path,default=Path('artifacts/sunday_projection_generation'))
    args=parser.parse_args();out=args.output_dir
    if (out/'experiment.json').exists():raise ValueError('Choose a fresh output directory')
    out.mkdir(parents=True,exist_ok=True)
    source=json.loads(args.source.read_text());params=source['constraint_config_json']
    contract=params['effective_strategy_contract'];validate_strategy_contract(contract)
    metadata=params['strategy_runtime']['classic_run_input_snapshot']['payload']['metadata']
    if (metadata['season'],metadata['week'],metadata['slate'])!=(2026,5,'SUNDAY_MAIN'):
        raise ValueError('This predeclared experiment targets 2026 Week 5 Sunday Main')
    rows=params['strategy_runtime']['classic_run_input_snapshot']['payload']['final_solver_rows']
    saved=params['portfolio_controls_report']['candidate_rosters']
    chosen=params['gpp_recommendation']['recommended']['lineup_number']-1
    cutoff=datetime.fromisoformat(source['data_cutoff_at'])
    def save(name,data): (out/name).write_text(json.dumps(data,indent=2,default=str,allow_nan=False)+'\n')
    save('replay_source.json',replay_source(source))
    save('frozen_contract.json',contract)
    audit=audit_rows(rows,set(saved[chosen]['player_ids']),cutoff)
    audit['upstream_pool_count']=len(params['classic_evidence_snapshot']['player_pool'])
    audit['upstream_field_coverage']=audit_rows(params['classic_evidence_snapshot']['player_pool'],set(),cutoff)['field_coverage']
    audit['source_run_id']=source['optimizer_run_id'];audit['projection_run_id']=source['projection_run_id'];audit['data_cutoff_at']=source['data_cutoff_at']
    save('projection_audit.json',audit)
    print('Projection audit saved; establishing exact production replay',flush=True)
    experiment=dict(source_run_id=source['optimizer_run_id'],projection_run_id=source['projection_run_id'],
        source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),started_at=datetime.now(timezone.utc),
        saved_recommendation=params['gpp_recommendation']['recommended'],live_changes=False,arms={})
    for arm in ('control','mean_led','template_rotation'):
        current=contract if arm=='control' else shadow_contract(contract,arm)
        save(arm+'_contract.json',current)
        result=execute_strategy_contract(current)
        proof=portfolio_audit(current,result.lineups,trace=result.selection_trace)
        if result.status!='completed' or proof['validation']['status']!='verified':
            raise ValueError(f'{arm}: generation or constraints failed')
        rec,rosters=recommend(result,source,rows)
        if arm=='control':
            parity=[sorted(p.player_id for p in lineup) for lineup in result.lineups]==[sorted(r['player_ids']) for r in saved]
            if not parity:raise ValueError('Exact control roster parity failed; shadows blocked')
            if rec['recommended']['candidate_id']!=params['gpp_recommendation']['recommended']['candidate_id']:
                raise ValueError('Control recommendation parity failed')
            experiment['parity']='PASS'
        finished=datetime.now(timezone.utc)
        timing=chronological_validation(dict(data_cutoff_at=source['data_cutoff_at'],optimizer_created_at=finished),
                    dict(status='slate_source_pool',candidates=saved))
        experiment['arms'][arm]=dict(recommendation=rec,rosters=rosters,portfolio=proof,
            completed_at=finished,prelock_timing=timing,contract_sha256=current['sha256'],
            paid_finish_probability=None,expected_return=None)
        save('experiment.json',experiment)
        print(arm,rec['recommended'],flush=True)
    print('Completed all arms; outcomes pending; live selector unchanged',flush=True)


if __name__=='__main__':main()
