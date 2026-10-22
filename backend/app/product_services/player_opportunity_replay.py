"""Append-only, non-entry player-model→count→world→portfolio evaluation.

Uses server-owned frozen jobs, model/matrix artifacts and the exact captured
legal model. It never refreshes sources, fits models or writes live lineups.
"""
from copy import deepcopy
from datetime import UTC,datetime
from pathlib import Path
import hashlib,json,re
from uuid import UUID
from sqlalchemy import text
from ..models import OperationalJob
from .analyst_shadow import digest,validate_snapshot
from .player_opportunity_serving import infer_player_counts
from .shared_world_runtime import generate_and_select,explain_rosters
from .shared_world_selection import MEAN_CONTRACT
from .count_scenario_response import count_world
from .analyst_packets import load_packet

ROOT=Path(__file__).resolve().parents[3]/'artifacts/player_opportunity_replays'
MATRICES=ROOT.parent/'player_opportunity_matrices'


def _read_matrix(sha,directory=None):
    if not re.fullmatch(r'[0-9a-f]{64}',sha):raise ValueError('Invalid managed player matrix SHA')
    p=Path(directory or MATRICES)/(sha+'.json')
    if p.stat().st_size>256*1024*1024:raise ValueError('Player matrix exceeds bounded artifact size')
    raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Player matrix byte checksum mismatch')
    return json.loads(raw)


def evaluate(config,prepared,*,model_result_sha256,matrix,packet=None,now=None,model_directory=None,generation_seconds=30):
    now=now or datetime.now(UTC);old=prepared['workload_forecast']
    if digest({k:v for k,v in old.items() if k!='sha256'})!=old.get('sha256'):raise ValueError('Frozen count receipt checksum mismatch')
    analyst=config['strategy_runtime']['football_analyst'];snapshot=deepcopy(analyst['input_snapshot'])
    validate_snapshot(snapshot,mean_only=True)
    if snapshot['scope']['season']*100+snapshot['scope']['week']!=old['before_period']:raise ValueError('Frozen legal/count scope mismatch')
    result=infer_player_counts(model_result_sha256,matrix,old,cutoff=now,purpose='offline_retrospective_evaluation',directory=model_directory)
    counts=result['counts'];response=counts['component_response'];by_id={p['player_master_id']:p for p in response['players']}
    mapping_ids={p['player_master_id'] for p in snapshot['variable_players'].values()}
    if mapping_ids-set(by_id):raise ValueError('Legal actor lacks frozen count/component assessment')
    if any(by_id[pid].get('world_activity') is False for pid in mapping_ids):raise ValueError('Captured legal pool contains a factually inactive actor in frozen count scope')
    rows=[deepcopy(r) for r in config['strategy_runtime']['player_pool']['rows'] if str(r.get('player_id')) in mapping_ids]
    if {str(r['player_id']) for r in rows}!=mapping_ids:raise ValueError('Captured legal actor pool differs')
    for row in rows:
        row['projection']=by_id[str(row['player_id'])]['base_fp']
        if row['projection'] is None:raise ValueError('Legal actor lacks frozen base FP')
    scope=dict(contest_format=snapshot['scope']['format'].lower(),season=prepared['season'],week=prepared['week'],slate=prepared['slate'])
    input_sha=digest(dict(model_inference=result['semantic_sha256'],legal_model=snapshot['sha256'],source_counts=old['sha256']))
    means={pid:by_id[pid]['conditional_mean'] for pid in mapping_ids}
    worlds=[dict(world_id='frozen_base_fp_reference',kind='baseline',anchor_basis='explicit_base_model_expected',frozen_scope=scope,input_sha256=input_sha,source_refs=[old['sha256']],mechanism='Preserved frozen base FP; diagnostic anchor, not a claim of new-model quality',mean_contract=MEAN_CONTRACT,likelihood='unknown',player_means={pid:by_id[pid]['base_fp'] for pid in mapping_ids}),dict(world_id='player_count_point_reference',kind='contrary',frozen_scope=scope,input_sha256=input_sha,
        source_refs=[model_result_sha256,result['semantic_sha256']],mechanism='Measured partial linear scoring response to pooled player-count point estimates; not calibrated Expected Game means',
        mean_contract=MEAN_CONTRACT,conditional_response_contract='frozen_base_plus_matched_linear_component_delta_v1',likelihood='unknown',player_means=means)]
    base={pid:p['base_fp'] for pid,p in by_id.items()}
    world_receipts=[]
    if packet:
        for scenario in packet['scenario_assumptions']['scenarios']:
            world=count_world(counts,scenario,base,cutoff=now);world_receipts.append(world)
            points={p['player_master_id']:p['conditional_mean'] for p in world['response']['players']}
            worlds.append(dict(world_id=scenario['scenario_id'],kind='conditional',frozen_scope=scope,input_sha256=input_sha,
                source_refs=[digest(packet),world['semantic_sha256']],mechanism=scenario['label'],
                declared_assumptions=deepcopy(scenario['assumptions']),mean_contract=MEAN_CONTRACT,conditional_response_contract='frozen_base_plus_matched_linear_component_delta_v1',likelihood='unknown',
                player_means={pid:points[pid] for pid in mapping_ids},research_binding='Original authored mechanisms reused for isolated sensitivity; not a new endorsed research handoff'))
    requested=int(config['num_lineups']);selected,selection=generate_and_select(snapshot,rows,worlds,
        anchor_world_id=worlds[0]['world_id'],requested=requested,params=config,fmt=snapshot['scope']['format'],generation_seconds=generation_seconds,max_candidates=48)
    explain_rosters(selection,worlds,rows)
    for lineup in selected:
        for actor in lineup['roster']:
            p=next(r for r in counts['players'] if r['player_master_id']==actor['player_master_id']);c=by_id[actor['player_master_id']]
            actor.update(name=next(r.get('name') for r in rows if str(r['player_id'])==actor['player_master_id']),counts=deepcopy(p['counts']),
                base_fp=c['base_fp'],conditional_fp=c['conditional_mean'],slot_conditional_fp=c['conditional_mean']*(1.5 if actor['role']=='CPT' else 1),component_delta=c['conditional_delta_points'])
    return dict(status='completed' if len(selected)==requested else 'bounded_pool_incomplete',research_only=True,entry_ready=False,pregame_serving_eligible=False,
        actual_created_at=now.isoformat(),chronology='Postlock isolated evaluation using revised historical sources and preserved legal constraints; never a fresh historical pregame claim',
        requested=requested,achieved=len(selected),selected=selected,selection=selection,worlds=worlds,world_responses=world_receipts,
        model_inference=result,source_legal_model_sha256=snapshot['sha256'],settings_sha256=digest({k:v for k,v in config.items() if k!='strategy_runtime'}),scope=scope)


def build(session,optimizer_run_id,*,source_prepared_input_job_id,model_result_sha256,matrix_sha256,packet_sha256=None,directory=None):
    UUID(optimizer_run_id);UUID(source_prepared_input_job_id)
    config=session.execute(text('SELECT constraint_config_json FROM target.optimizer_run WHERE optimizer_run_id=:id'),dict(id=optimizer_run_id)).scalar_one_or_none()
    if config is None:raise LookupError('Frozen source optimizer not found')
    job=session.get(OperationalJob,source_prepared_input_job_id)
    if job is None or job.status!='completed' or job.job_type!='slate_preparation':raise ValueError('Completed frozen Prepare required')
    identity=dict(contract='player_model_count_portfolio_evaluation_v1',optimizer_run_id=optimizer_run_id,source_prepare_job_id=source_prepared_input_job_id,
        model_result_sha256=model_result_sha256,matrix_sha256=matrix_sha256,packet_sha256=packet_sha256,source_config_sha256=digest(config),
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    key=digest(identity);root=Path(directory or ROOT);path=root/(key+'.json')
    if path.exists():return read(key,directory=root)
    result=evaluate(config,job.result_json,model_result_sha256=model_result_sha256,matrix=_read_matrix(matrix_sha256),packet=load_packet(packet_sha256) if packet_sha256 else None)
    result.update(replay_id=key,input_identity=identity);result['artifact_sha256']=digest(result);root.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(result,f,sort_keys=True,separators=(',',':'),allow_nan=False)
    return result


def read(key,*,directory=None):
    if not re.fullmatch(r'[0-9a-f]{64}',key):raise ValueError('Invalid player replay ID')
    path=Path(directory or ROOT)/(key+'.json')
    if not path.exists():raise LookupError('Player replay not found')
    value=json.loads(path.read_text())
    if digest({k:v for k,v in value.items() if k!='artifact_sha256'})!=value.get('artifact_sha256'):raise ValueError('Saved player replay checksum mismatch')
    return value


def html_report(value):
    """Visible saved consumer; all data escaped and non-entry state prominent."""
    from html import escape
    def e(v):return escape(str(v))
    def n(v):return 'unknown' if v is None else f'{v:.3f}'
    blocks=[]
    for index,lineup in enumerate(value['selected'],1):
        rows=[]
        for p in lineup['roster']:
            counts=p['counts'];rows.append('<tr>'+''.join('<td>'+e(x)+'</td>' for x in [p['role'],p['name'],n(p['salary']),n(counts['pass_attempts']),n(counts['rush_attempts']),n(counts['targets']),n(p['base_fp']),n(p['conditional_fp']),n(p['slot_conditional_fp'])])+'</tr>')
        blocks.append(f'<h2>Lineup {index}</h2><table><thead><tr><th>Slot</th><th>Player</th><th>Salary</th><th>Pass attempts</th><th>Carries</th><th>Targets</th><th>Base FP</th><th>Conditional FP</th><th>Slot FP</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>')
    return '<!doctype html><meta charset="utf-8"><title>Player opportunity evaluation</title><style>body{font:16px system-ui;margin:28px;color:#102c40}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #ccd4da;text-align:left}.notice{background:#fff3ce;padding:16px}</style><h1>Saved player-model evaluation</h1><p class="notice">Post-lock isolated evaluation. Not entry-ready. Revised historical inputs are not original pregame evidence. Numerical point sensitivities are not calibrated Expected Game means.</p><p>Requested '+e(value['requested'])+' / achieved '+e(value['achieved'])+' · '+e(value['status'])+' · actual creation '+e(value['actual_created_at'])+'</p>'+''.join(blocks)+'<details><summary>Model, scope and constraints</summary><pre>'+e(json.dumps(dict(input_identity=value.get('input_identity'),scope=value['scope'],selection=value['selection']),indent=2))+'</pre></details>'
