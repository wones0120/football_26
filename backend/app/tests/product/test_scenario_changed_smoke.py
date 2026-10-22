"""Isolated dispatch/accounting fixtures; never invoke a real smoke."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from backend.app.product_services.game_progression_runtime import STATS
from research.game_progression_pilot_20261020.scenario_04 import common as c
from research.game_progression_pilot_20261020.scenario_04 import run


def fixture():
    games=[dict(game_id='2026_01_DEN_KC',context_by_side=[{},{}])];prior=[];audit=[]
    statuses=['UNKNOWN_SOURCE_STATE','UNKNOWN_SOURCE_STATE','UNKNOWN_CENSORED_SUCCESSOR','COMPLETE_REGULATION','NOT_RUN_AFTER_CAP_OR_FAILURE','NOT_RUN_AFTER_CAP_OR_FAILURE']
    for i,status in enumerate(statuses):
        path=i//2;arm=c.ARM_ORDER[i%2];trace=[dict(cycle_id='native:one',tier='CONTROL',pool_size=8,pre_remaining=100,status=status)]
        row=dict(game_id=games[0]['game_id'],path=path,arm=arm,uniform_stream_sha256=c.uniforms(games[0]['game_id'],path)[1],result=dict(status=status,trace=trace))
        prior.append(row);item=dict(game_id=row['game_id'],path=path,arm=arm,original_status=status,cycle_id='native:one',
            disposition='SOURCE_TRANSITION_NOW_PROVEN_NOT_A_COMPLETED_PATH'if i==0 else'SOURCE_EVIDENCE_STILL_REQUIRED',
            changed_source_certified=i==0,source_transition_proofs=[{'native':'proof'}]if i==0 else[],changed_source_barriers=[]if i==0 else['unknown'])
        audit.append(item)
    return prior,audit,games


def test_plan_dispatches_only_changed_and_original_unfinished_slots():
    prior,audit,games=fixture();before=deepcopy((prior,audit));plan=c.plan_paths(prior,audit,games,3)
    assert [r['disposition']for r in plan]==[c.REPAIRED,c.SKIP_SOURCE,c.SKIP_CENSOR,c.SKIP_COMPLETE,c.UNFINISHED,c.UNFINISHED]
    assert (prior,audit)==before and len({r['record_id']for r in plan})==6
    assert all(r['original_record_sha256']==c.digest(old)for r,old in zip(plan,prior))

@pytest.mark.parametrize('problem',['missing','duplicate','audit_key','status','proof','native_cycle'])
def test_plan_rejects_ambiguous_or_unproved_dispatch(problem):
    prior,audit,games=fixture()
    if problem=='missing':prior.pop()
    if problem=='duplicate':prior[-1]=prior[0]
    if problem=='audit_key':audit[-1]['path']=99
    if problem=='status':audit[0]['original_status']='COMPLETE_REGULATION'
    if problem=='proof':audit[0]['source_transition_proofs']=[]
    if problem=='native_cycle':audit[0]['cycle_id']='wrong:native'
    with pytest.raises(ValueError):c.plan_paths(prior,audit,games,3)


def test_native_audit_copy_changes_only_certification_barriers_and_proof():
    source=dict(cycles=[dict(cycle_id='2023_01_A_B:1',state_certified=False,barriers=['fumble'],start={'field':75},production={'carries':1})],threats=['unscopable'])
    audit=dict(kernel_inputs_and_production_unchanged=True,all_unknown_candidates_retained=True,newly_source_certified_cycles=['2023_01_A_B:1'],partially_repaired_cycles=[],changed_state_certified=1,
        source_evidence_ledger=[dict(cycle_id='2023_01_A_B:1',source_state_certified=True,proofs=[dict(game_id='2023_01_A_B',play_id='1',discharges='fumble')])])
    before=deepcopy(source);out=c.apply_audit(source,audit)
    assert source==before and out['threats']==source['threats']
    assert out['cycles'][0]['state_certified']and out['cycles'][0]['production']==source['cycles'][0]['production']
    audit['source_evidence_ledger'][0]['proofs'][0]['play_id']='2'
    with pytest.raises(ValueError):c.apply_audit(source,audit)


def test_uniform_stream_matches_original_saved_seed17_hash():
    values,sha=c.uniforms('2026_01_DEN_KC',0)
    assert len(values)==401 and sha=='57a8318dc48b5151a1cb62c1035490ac0b65a4de46cec3f3518a5aa44b5ad550'
    assert c.uniforms('2026_01_DEN_KC',0)==(values,sha)


def test_prefix_verification_preserves_selected_sources_without_requiring_unknown_mass():
    prior,_,_=fixture();out=deepcopy(prior[0]['result']);out['trace'][0].update(status='TRANSFERRED',unknown_state_pool=0)
    assert c.prefix_check(prior[0],out).endswith('REPAIRED_STOP_TRANSFERRED')
    out['trace'][0]['cycle_id']='wrong'
    with pytest.raises(ValueError):c.prefix_check(prior[0],out)
    assert c.prefix_check(prior[0],dict(status='INCOMPLETE_TIME_CAP',trace=[]))=='INCOMPLETE_BEFORE_ORIGINAL_STOP'


def test_skips_or_unfinished_rows_never_become_zero_forecasts():
    prior,audit,games=fixture();plan=c.plan_paths(prior,audit,games,3);rows=c.assemble(plan,[],[]);summary=c.summarize(rows,3)
    assert len(rows)==6 and all(r['result']is None for r in rows)
    assert summary['selected_dispatch']==3 and summary['undispatched_selected']==3 and summary['new_complete_states']==0
    with pytest.raises(ValueError):c.assemble(plan,[],[c.key(plan[1])])


def test_complete_state_channel_paths_and_forecasts_are_distinct():
    prior,audit,games=fixture();plan=c.plan_paths(prior,audit,games,3);item=plan[0]
    stats=[dict.fromkeys(STATS,0)for _ in (0,1)];stats[0]['official_targets']=None
    result=dict(status='COMPLETE_REGULATION',full_law_known=False,team_stats=stats)
    done=[dict(game_id=item['game_id'],path=item['path'],arm=item['arm'],result=result)]
    summary=c.summarize(c.assemble(plan,done,[c.key(item)]),3)
    assert summary['new_complete_states']==1 and summary['complete_channel_paths']['official_pass_attempts']==1
    assert summary['complete_channel_paths']['official_targets']==0 and summary['complete_supported_joint_law_paths']==0
    assert all(v==0 for v in summary['complete_channel_forecast_groups'].values())


def setup_run(tmp_path,monkeypatch):
    prior,audit,games=fixture();plan=c.plan_paths(prior,audit,games,3)
    baseline=tmp_path/'prior.jsonl';baseline.write_text(''.join(json.dumps(r)+'\n'for r in prior));original=baseline.read_bytes()
    manifest=dict(run_id=c.RUN_ID,plan=plan,bounds=dict(preparation_seconds=30,whole_run_seconds=30,max_dispatched_paths=106,max_actions_per_path=400,uniforms_per_path=401),
        code_refs=[],preserved_refs=[run.ref(baseline)],recipe_ref=run.ref(baseline),baseline_paths_ref=run.ref(baseline),
        games_ref={'fixture':'games'},library_ref={'fixture':'library'},openings_ref={'fixture':'openings'})
    path=tmp_path/'manifest.json';path.write_text(json.dumps(manifest))
    actual_load=run.load
    def load(ref):
        if 'fixture'in ref:return {'games':games,'library':dict(cycles=[],threats=['unscopable']),'openings':[dict(certified=False)]}[ref['fixture']]
        return actual_load(ref)
    monkeypatch.setattr(run,'load',load)
    def fake_rollout(*args):
        trace=deepcopy(prior[0]['result']['trace']);trace[0]['status']='TRANSFERRED'
        return dict(status='UNKNOWN_CENSORED_SUCCESSOR',trace=trace,full_law_known=False)
    monkeypatch.setattr(run,'rollout',fake_rollout)
    return path,baseline,original


def test_runner_never_reexecutes_skips_and_preserves_all_rows(tmp_path,monkeypatch):
    path,baseline,original=setup_run(tmp_path,monkeypatch)
    summary=run.execute(path,tmp_path/'new_run')
    assert summary['newly_finished_paths']==3 and summary['execution_counts']=={'NEW_RESULT':3,'SKIPPED_BY_FROZEN_PLAN':3}
    assert summary['preserved_evidence_unchanged']and baseline.read_bytes()==original
    assert summary['unknown_opening_count']==1 and summary['actual_labels_loaded']is False
    with pytest.raises(ValueError):run.execute(path,tmp_path/'new_run')

@pytest.mark.parametrize('error,status',[(TimeoutError('cap'),'INCOMPLETE_TIME_CAP'),(RuntimeError('fixture failure'),'FAILED_NO_AUTOMATIC_RETRY')])
def test_run_cap_or_failure_keeps_started_and_unrun_slots_explicit(tmp_path,monkeypatch,error,status):
    path,baseline,original=setup_run(tmp_path,monkeypatch)
    def fail(*args):raise error
    monkeypatch.setattr(run,'rollout',fail)
    summary=run.execute(path,tmp_path/'failed_run')
    assert summary['status']==status and summary['newly_finished_paths']==0
    assert summary['started_unfinished']==1 and summary['undispatched_selected']==2
    assert summary['execution_counts']=={'NOT_FINISHED_CAP_OR_FAILURE':3,'SKIPPED_BY_FROZEN_PLAN':3}
    assert baseline.read_bytes()==original and not summary['original_run_extended']


def test_partial_journal_tail_is_preserved_and_explicit(tmp_path):
    p=tmp_path/'journal.jsonl';p.write_text('{"path":1}\n{"path":')
    assert c.read_journal(p)==([{'path':1}],True)
    assert p.read_text().endswith('{"path":')
    p.write_text('{oops}\n')
    with pytest.raises(ValueError):c.read_journal(p)
