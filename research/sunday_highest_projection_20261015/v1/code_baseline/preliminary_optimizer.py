"""Explicit preliminary research, isolated from normal live preparation approval.

A frozen failed/partial preparation can support a disclosed research comparison.
It never clears entry readiness, renews source clocks, or mutates source facts.
"""
from copy import deepcopy
from datetime import UTC, datetime
import json
import re
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..models import OperationalJob
from ..product_schemas import OptimizerRunRequest
from .analyst_shadow import digest
from .optimizer import OptimizerService, _json_safe
from .slate_preparation import (SlatePreparationRequest, source_manifest, projection_proof, assess_prepared_inputs,
                                require_prelock, verify_artifacts, digest as source_digest)

LEDGER=Path('artifacts/preliminary_optimizer_snapshots')
CONTRACT='preliminary_optimizer_snapshot_v1'


class PreliminarySnapshotRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    preparation_job_id: str = Field(min_length=1,max_length=128)
    injury_policy: Literal['exclude_current_questionable', 'exclude_unknown_and_questionable'] = 'exclude_unknown_and_questionable'
    analyst_mode: Literal['AUTO','MANUAL','BASELINE'] | None = None
    analyst_packet_sha256: str | None = Field(default=None,pattern=r'^[0-9a-f]{64}$')
    analyst_strategy: Literal['MERGED_SCENARIOS','CONSTRUCTION'] | None = None


class PreliminaryOptimizerRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    snapshot_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    optimizer: OptimizerRunRequest


def _entry_report(snapshot):
    return dict(status='PRELIMINARY_NOT_ENTRY_CLEARED',entry_ready=False,
        reason_codes=sorted(set(snapshot['normal_readiness']['reason_codes']+['preliminary_research_only'])),
        preliminary_snapshot_sha256=snapshot['sha256'],
        explanation='Research lineup assumptions do not certify current injuries, workload or final game-day clearance.')


def save_snapshot(value,*,directory=None):
    root=Path(directory) if directory is not None else LEDGER;root.mkdir(parents=True,exist_ok=True)
    key=digest(value);snapshot={**value,'sha256':key};path=root/(key+'.json')
    try:
        with path.open('x') as handle:handle.write(json.dumps(snapshot,indent=2,allow_nan=False)+'\n')
    except FileExistsError:
        if json.loads(path.read_text())!=snapshot:raise ValueError('Preliminary snapshot ledger conflict')
    return snapshot


def load_snapshot(key,*,directory=None):
    if not isinstance(key,str) or not re.fullmatch(r'[0-9a-f]{64}',key):raise ValueError('Invalid preliminary snapshot hash')
    try: snapshot=json.loads(((Path(directory) if directory is not None else LEDGER)/(key+'.json')).read_text())
    except (OSError,ValueError) as exc:raise ValueError('Preliminary snapshot unavailable') from exc
    if snapshot.get('contract_id')!=CONTRACT or digest({k:v for k,v in snapshot.items() if k!='sha256'})!=key:raise ValueError('Preliminary snapshot hash/contract mismatch')
    if snapshot.get('entry_ready') is not False:raise ValueError('Preliminary snapshot cannot assert entry readiness')
    return snapshot


def create_snapshot(session,request,service,*,directory=None):
    job=session.scalar(select(OperationalJob).where(OperationalJob.job_id==request.preparation_job_id))
    if job is None or job.job_type!='slate_preparation' or job.status not in {'failed','completed'}:raise ValueError('A finished preparation with saved projection evidence is required')
    prepared=deepcopy(job.result_json or (job.checkpoint_json or {}).get('preparation_result') or {})
    req=SlatePreparationRequest.model_validate(job.request_json)
    req=req.model_copy(update={k:getattr(request,k) for k in ('analyst_mode','analyst_packet_sha256','analyst_strategy') if getattr(request,k) is not None})
    if req.action!='prepare' or req.contest_format!='classic':raise ValueError('Preliminary research currently supports prepared Classic slates')
    readiness=assess_prepared_inputs(service,req,prepared)
    if (prepared.get('data_readiness') or {}).get('status') not in {'READY','NOT_READY','ERROR'}:raise ValueError('Saved normal readiness report is required')
    for name in ('salary_pool','market','projection','ownership'):
        if (readiness.get('required_sources',{}).get(name) or {}).get('status')!='READY':raise ValueError('Preliminary research requires verified '+name+' evidence')
    if not prepared.get('projection_run_id') or not prepared.get('ownership_run_id'):raise ValueError('A newly built projection and ownership are required')
    # Preserve every normal source error; only unresolved injury/usage evidence is
    # eligible for explicit research assumptions, not identity/market/projection gaps.
    allowed={'official_player_status_refresh_failed','player_status_timestamp_missing','questionable_usage_context_unresolved'}
    if req.preliminary_research:
        allowed |= set(readiness.get('required_sources',{}).get('player_status',{}).get('reason_codes',[]))
    if set(readiness.get('reason_codes',[]))-allowed:raise ValueError('Unsupported preliminary readiness blocker: '+', '.join(sorted(set(readiness.get('reason_codes',[]))-allowed)))
    current=source_manifest(session,req);require_prelock(current['games']);verify_artifacts(current,session)
    if source_digest(current)!=prepared.get('source_sha256'):raise ValueError('Sources changed since preparation; prepare again before freezing preliminary research')
    proof=projection_proof(session,prepared)
    if source_digest(proof)!=prepared.get('projection_lineage_sha256'):raise ValueError('Projection lineage changed since preparation')
    pool=service._load_player_pool(req.season,req.week,req.slate,projection_run_id=prepared['projection_run_id'],ownership_run_id=prepared['ownership_run_id'],evidence_cutoff_at=datetime.fromisoformat(prepared['data_cutoff_at'].replace('Z','+00:00')),require_explicit_runs=True)
    from .player_roles import resolve_player_roles
    from .kicker_roles import assign_kicker_roles
    pool,_=assign_kicker_roles(pool);pool,_=resolve_player_roles(pool)
    rows=_json_safe(pool.to_dict('records'));attrs=_json_safe(dict(pool.attrs))
    unresolved=[p for p in readiness.get('players',[]) if p.get('reason_codes')]
    if any(p.get('availability')!='questionable_elevated' for p in unresolved) and not (req.preliminary_research and request.injury_policy == 'exclude_unknown_and_questionable'):
        raise ValueError('Unknown players require explicit preliminary preparation with conservative unknown exclusions')
    # Some native OUT rows are outside normal-readiness assessment, but stale
    # evidence still excluded them from research scoring. Preserve those decisions
    # too, rather than relying on roster absence as their assumption receipt.
    scoring_unknown=((proof.get('run') or {}).get('source_versions_json') or {}).get('preliminary_research',{}).get('exclude_player_ids',[])
    recorded={p['player_id'] for p in unresolved}
    contexts={str(r['player_master_id']):r for r in current.get('availability',[])}
    salary={str(r['player_master_id']):r for r in current.get('salaries',[])}
    for pid in scoring_unknown:
        if pid not in recorded:
            context=contexts.get(pid,{})
            unresolved.append(dict(player_id=pid,player=context.get('player_name') or salary.get(pid,{}).get('player_name') or pid,
                availability='unknown',reason_codes=['availability_or_role_unknown_at_projection_cutoff'],
                source_context=deepcopy(context)))
    exclusions=sorted({p['player_id'] for p in unresolved})
    assumption_manifest=dict(contract_id='preliminary_injury_assumptions_v1',declared_at=datetime.now(UTC).isoformat(),
        injury_policy=request.injury_policy,exclude_player_ids=exclusions,
        source_truth='Original designation, role and observation clocks remain unchanged.',
        practice_assumption='Exclude every player with unknown, stale or missing availability/role evidence, and questionable players with unresolved practice/workload; no healthy or full-workload assumption.',
        other_player_assumption='Retain existing sourced active roster/expected role and unchanged base projections; this does not establish game-day dressing or injury clearance.',
        known_unavailable_policy='Preserve existing OUT/IR/practice-squad/role and salary ineligibility exclusions.',
        players=[{**p, "research_assumption": "EXCLUDE_FROM_RESEARCH", "source_truth_unchanged": True} for p in unresolved],assumed_healthy_player_ids=[],assumed_available_player_ids=[])
    snapshot = save_snapshot(_json_safe(dict(contract_id=CONTRACT,classification='PRELIMINARY_RESEARCH',entry_ready=False,
        preparation_job_id=str(job.job_id),scope=dict(season=req.season,week=req.week,slate=req.slate,contest_format=req.contest_format),
        projection_run_id=prepared['projection_run_id'],ownership_run_id=prepared['ownership_run_id'],data_cutoff_at=prepared['data_cutoff_at'],
        source_sha256=prepared['source_sha256'],projection_lineage_sha256=prepared['projection_lineage_sha256'],
        source_manifest=prepared['source_manifest'],normal_readiness=readiness,source_refresh=prepared['source_refresh'],
        assumption_manifest=assumption_manifest,assumption_manifest_sha256=digest(assumption_manifest),pool=rows,pool_attrs=attrs,pool_sha256=digest(dict(rows=rows,attrs=attrs)))),directory=directory)
    from .analyst_preparation import save_snapshot_handoff
    from .analyst_personal_context import load_inputs
    save_snapshot_handoff(snapshot,req,prepared,personal_context_inputs=load_inputs(session.get_bind()))
    return snapshot


def validate_request(request,snapshot):
    optimizer=request.optimizer
    from .analyst_preparation import load_snapshot_handoff, bind_handoff
    handoff=load_snapshot_handoff(snapshot['sha256'])
    if handoff:
        payload=optimizer.model_dump(mode='json')
        bind_handoff(payload,{'analyst_handoff':handoff,'analyst_intent_handoffs':handoff.get('analyst_intent_handoffs',{})})
        optimizer.params=payload['params']
    scope=snapshot['scope']
    if (optimizer.season,optimizer.week,optimizer.slate,optimizer.contest_format)!=(scope['season'],scope['week'],scope['slate'],'classic'):raise ValueError('Preliminary request scope mismatch')
    if optimizer.objective!='gpp' or optimizer.strategy!='classic_large_gpp_v1':raise ValueError('Preliminary comparison currently requires Classic Large GPP')
    if optimizer.projection_run_id!=snapshot['projection_run_id']:raise ValueError('Preliminary projection mismatch')
    if optimizer.params.get('analyst_packet_sha256'):
        from .analyst_packets import load_packet
        discovery=load_packet(optimizer.params['analyst_packet_sha256']).get('discovery')
        if discovery and discovery['scan_snapshot_sha256']!=snapshot['sha256']:raise ValueError('Discovery investigation snapshot mismatch')
    if optimizer.params.get('exclude_questionable') is not True:raise ValueError('The frozen preliminary assumption requires current questionable exclusions')
    if optimizer.params.get('availability_overrides') or optimizer.params.get('assume_questionable_out'):raise ValueError('Preliminary research cannot mutate projection availability assumptions')
    if optimizer.params.get('prepared_input_job_id') or optimizer.params.get('allow_incomplete_evidence'):raise ValueError('Preliminary request must use its snapshot, not an ordinary readiness claim')
    if optimizer.params.get('ownership_run_id') not in {None,snapshot['ownership_run_id']}:raise ValueError('Preliminary ownership mismatch')
    locks=set(optimizer.params.get('locked_player_ids') or [])|set(optimizer.params.get('lock_player_ids') or [])
    if locks & set(snapshot['assumption_manifest']['exclude_player_ids']):raise ValueError('A lock conflicts with the explicit preliminary injury exclusion')
    return optimizer


def run_preliminary(request,*,run_id,context=None,service=None,directory=None):
    snapshot=load_snapshot(request.snapshot_sha256,directory=directory);optimizer=validate_request(request,snapshot)
    require_prelock(snapshot['source_manifest']['games'])
    base=service or OptimizerService()
    from .analyst_preparation import load_snapshot_handoff
    personal_handoff=load_snapshot_handoff(snapshot['sha256']) or {}
    personal_context=(optimizer.params.get('analyst_handoff_applied') or {}).get('personal_context') or {}
    if personal_context.get('considered'):
        from .analyst_personal_context import load_inputs,validate_current
        validate_current(personal_context,load_inputs(base.engine),checked_at=datetime.now(UTC).isoformat())
    class FrozenPreliminaryService(OptimizerService):
        def _load_player_pool(self,*args,**kwargs):
            frame=pd.DataFrame(deepcopy(snapshot['pool']));frame.attrs=deepcopy(snapshot['pool_attrs']);return frame
        def _persist_optimizer_run(self,job):
            from .analyst_preparation import load_snapshot_handoff
            checked_handoff=load_snapshot_handoff(snapshot['sha256'])
            if job.params.get('analyst_optimization_intent','MIXED') != 'MIXED':
                checked_handoff=(checked_handoff or {}).get('analyst_intent_handoffs',{}).get(job.params['analyst_optimization_intent'])
            if checked_handoff:
                job.params['analyst_handoff_applied']=dict(mode=job.params.get('analyst_handoff_mode','AUTO'),compatibility_sha256=checked_handoff['compatibility_sha256'],source_packet_sha256=checked_handoff['source_packet_sha256'],checked_packet_sha256=checked_handoff['checked_packet_sha256'],checked_at=checked_handoff['checked_at'])
                if checked_handoff.get('personal_context') and job.params.get('analyst_handoff_mode','AUTO')!='BASELINE':
                    job.params['analyst_handoff_applied']['personal_context']=deepcopy(checked_handoff['personal_context'])
                analyst=job.params.get('strategy_runtime',{}).get('football_analyst')
                if analyst is not None:analyst.update(prepared_research=job.params['analyst_handoff_applied'],preparation_compatibility=checked_handoff)
            job.params['preliminary_report']=dict(classification='PRELIMINARY_RESEARCH',entry_ready=False,
                snapshot_sha256=snapshot['sha256'],preparation_job_id=snapshot['preparation_job_id'],
                assumption_manifest_sha256=snapshot['assumption_manifest_sha256'],assumption_manifest=snapshot['assumption_manifest'],
                source_sha256=snapshot['source_sha256'],pool_sha256=snapshot['pool_sha256'],
                normal_readiness=snapshot['normal_readiness'],source_refresh=snapshot['source_refresh'])
            job.params['data_readiness']=deepcopy(snapshot['normal_readiness'])
            job.params['entry_readiness']=_entry_report(snapshot)
            if not str(job.message or '').startswith('PRELIMINARY RESEARCH'):
                job.message='PRELIMINARY RESEARCH — not entry cleared; '+str(job.message or '')
            for lineup in job.results or []:
                for player in lineup:
                    player['preliminary_research']=True;player['entry_ready']=False
                    player['preliminary_snapshot_sha256']=snapshot['sha256']
            return super()._persist_optimizer_run(job)
    frozen=FrozenPreliminaryService(base.connection_string);frozen.engine=base.engine
    params=deepcopy(optimizer.params)
    params['ownership_run_id']=snapshot['ownership_run_id'];params['refresh_ownership']=False
    params['exclude_player_ids']=sorted(set(params.get('exclude_player_ids') or [])|set(snapshot['assumption_manifest']['exclude_player_ids']))
    # This server-only internal research switch is confined to this typed path.
    # The normal API continues requiring READY preparation; no source is rewritten.
    job=frozen.run_job(optimizer.season,optimizer.week,optimizer.slate,optimizer.strategy,params,
        contest_format='classic',objective='gpp',projection_run_id=snapshot['projection_run_id'],
        data_cutoff_at=datetime.fromisoformat(snapshot['data_cutoff_at'].replace('Z','+00:00')),optimizer_run_id=run_id,
        allow_incomplete_evidence=True,progress=context.progress if context else None)
    return job
