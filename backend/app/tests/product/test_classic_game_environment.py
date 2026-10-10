from copy import deepcopy
from types import SimpleNamespace
import json
from pathlib import Path
import pytest

from backend.app.product_services import classic_data_readiness as gate
from backend.app.product_services.classic_game_environment import build_review, review_job, total_tiers
from backend.app.product_services.slate_preparation import digest
from backend.app.product_services.single_lineup import select_single_lineup, CLASSIC_SINGLE_LINEUP_STRATEGY_ID
from backend.app.tests.product.test_classic_data_readiness import fixture, assess, NOW, CUT, OWNERSHIP, PROJECTION


def review_fixture():
    rows, evidence = fixture()
    evidence['ownership_lineage']={OWNERSHIP:{'status':'completed','metrics_json':{'input_provenance':{'target_projection_run_id':PROJECTION}}}}
    for i,m in enumerate(evidence['source_manifest']['markets']):
        m.update(game_total=[40.,48.,56.][i],home_spread=[-6.,4.,0.][i])
    for r in rows:
        m=next(m for m in evidence['source_manifest']['markets'] if m['game_id']==r['canonical_game_id'])
        g=next(g for g in evidence['source_manifest']['games'] if g['game_id']==r['canonical_game_id'])
        spread=m['home_spread'] if r['player_team']==g['home_team'] else -m['home_spread']
        r.update(game_total_line=m['game_total'],team_spread_line=spread,team_implied_total=(m['game_total']-spread)/2)
    ready=assess(rows,evidence)
    assert ready['status']=='READY',ready['reason_codes']
    frozen=gate.freeze_evidence(rows,ready,optimizer_run_id='fixture',evidence=evidence)
    roster=[]
    for pos,slot,team in [('QB','QB','ARI'),('RB','RB','DEN'),('RB','RB','BUF'),
                          ('WR','WR','CHI'),('WR','WR','DAL'),('WR','WR','DEN'),
                          ('TE','TE','DET'),('RB','FLEX','CHI'),('DST','DST','BUF')]:
        p=next(r for r in rows if r['position']==pos and r['player_team']==team and r['player_id'] not in {p['player_id'] for p in roster})
        roster.append({**p,'roster_position':slot})
    return roster,frozen


def review(roster,frozen):
    return build_review(roster,frozen,run_id='fixture',season=NOW.year,week=5,slate='SUNDAY_MAIN',cutoff=CUT)


def rehash(frozen):
    frozen['sha256']=digest({k:v for k,v in frozen.items() if k!='sha256'})


def test_current_slate_tiers_handle_equal_totals_and_exact_boundaries():
    assert total_tiers(dict(a=40,b=44,c=48,d=52))==dict(a='lowest_quarter',b='middle_half',c='middle_half',d='highest_quarter')
    assert total_tiers(dict(a=40,b=40,c=48,d=48))==dict(a='lowest_quarter',b='lowest_quarter',c='highest_quarter',d='highest_quarter')
    assert set(total_tiers(dict(a=48,b=48,c=48)).values())=={'middle_half'}


def test_canonical_market_association_spread_signs_implied_sum_and_eight_offense():
    roster,frozen=review_fixture();result=review(roster,frozen)
    assert result['status']=='AVAILABLE' and result['roster_valid']
    assert result['composition']['offensive_slots']==8
    assert sum(result['composition'][k] for k in ('highest_quarter','middle_half','lowest_quarter','unavailable'))==8
    assert result['composition']['by_position']['RB']['slots']==3
    assert result['dst']['position']=='DST'
    for r in result['rows']:
        g=next(g for g in frozen['canonical_evidence']['source_manifest']['games'] if g['game_id']==r['game_id'])
        m=next(m for m in frozen['canonical_evidence']['source_manifest']['markets'] if m['game_id']==r['game_id'])
        assert r['game_total']==m['game_total']
        spread=m['home_spread'] if r['team']==g['home_team'] else -m['home_spread']
        assert r['team_spread']==spread
        assert r['team_implied_points']==(m['game_total']-spread)/2
        assert r['opponent_implied_points']==(m['game_total']+spread)/2
        assert r['team_implied_points']+r['opponent_implied_points']==r['game_total']
    assert result['dst']['opponent_implied_points']==result['dst']['game_total']-result['dst']['team_implied_points']
    assert all(r['projected_ownership']==10 for r in result['rows'])


@pytest.mark.parametrize('kind',['post_cutoff','stale','unsourced','late_ingest','unknown_clock'])
def test_unusable_markets_never_fallback_to_embedded_or_historical_numbers(kind):
    roster,frozen=review_fixture();m=frozen['canonical_evidence']['source_manifest']['markets'][0]
    if kind=='post_cutoff':m['observed_at']=frozen['frozen_at']
    elif kind=='late_ingest':m['ingested_at']=frozen['frozen_at']
    elif kind=='stale':m['observed_at']='2020-01-01T00:00:00Z'
    elif kind=='unsourced':m['source_snapshot_id']=None
    else:m['observed_at']=None
    rehash(frozen)
    result=review(roster,frozen)
    assert result['status']=='PARTIAL'
    assert all(r['tier'] is None for r in result['rows']), 'Incomplete slate must not fabricate relative tiers'
    affected=[r for r in result['rows'] if r['game_id']==m['game_id']]
    assert affected and all(r['game_total'] is None for r in affected)
    assert result['composition']['mean_offensive_game_total'] is None


def test_postgame_fields_cannot_influence_review_and_ownership_requires_lineage():
    roster,frozen=review_fixture();before=review(roster,frozen)
    for p in frozen['player_pool']:
        p.update(actual_points=900,actual_ownership=99,realized_ownership=98,rank=1)
    for p in roster:p.update(game_total_line=100,actual_ownership=99,ownership=99,projection=900)
    frozen['historical_research']={'high_total_target':8,'actual_points':999}
    rehash(frozen);after=review(roster,frozen)
    assert {k:v for k,v in before.items() if k!='evidence_sha256'}=={k:v for k,v in after.items() if k!='evidence_sha256'}
    assert 'actual_points' not in json.dumps(after)
    frozen['canonical_evidence']['ownership_lineage']={};rehash(frozen)
    assert all(p['projected_ownership'] is None for p in review(roster,frozen)['rows'])


def test_missing_hash_scope_or_late_freeze_fails_closed():
    roster,frozen=review_fixture()
    for mutation in [lambda f:f.update(sha256='bad'),lambda f:f.update(optimizer_run_id='different'),
                     lambda f:f.update(frozen_at='2099-01-01T00:00:00Z')]:
        value=deepcopy(frozen);mutation(value)
        if value['sha256']!='bad':rehash(value)
        result=review(roster,value)
        assert result['status']=='UNAVAILABLE' and all(r['game_total'] is None for r in result['rows'])


def test_optional_spread_and_partial_evidence_do_not_invent_implied_points():
    roster,frozen=review_fixture()
    for m in frozen['canonical_evidence']['source_manifest']['markets']:m['home_spread']=None
    rehash(frozen);result=review(roster,frozen)
    assert all(r['game_total'] is not None for r in result['rows'])
    assert all(r['team_spread'] is None and r['team_implied_points'] is None and r['opponent_implied_points'] is None for r in result['rows'])


def test_saved_job_review_is_read_only_and_other_strategies_keep_original_reports():
    roster,frozen=review_fixture();params={'classic_evidence_snapshot':frozen};before=deepcopy(params)
    job=SimpleNamespace(strategy=CLASSIC_SINGLE_LINEUP_STRATEGY_ID,status='completed',results=[roster],params=params,
        job_id='fixture',season=NOW.year,week=5,slate='SUNDAY_MAIN',data_cutoff_at=CUT)
    assert review_job(job)['status']=='AVAILABLE' and params==before
    job.strategy='captain_single_lineup_v1';assert review_job(job) is None
    job.strategy='classic_large_gpp_v1';assert review_job(job) is None


def test_archived_frozen_selection_and_scores_identical_to_before_enhancement():
    path=Path(__file__).resolve().parents[4]/'artifacts/classic_game_environment_review/task_start/frozen_control.json'
    baseline=json.loads(path.read_text());candidates=baseline['candidates'];original=deepcopy(candidates)
    selected,report=select_single_lineup(candidates,strategy=CLASSIC_SINGLE_LINEUP_STRATEGY_ID)
    assert selected==baseline['selected'] and report==baseline['report'] and len(selected)==1
    build_review(selected[0],None,run_id='archived',season=2026,week=3,slate='SUNDAY_MAIN',cutoff='2026-09-27T12:00:00Z')
    assert candidates==original
    # Adversarial research metadata remains outside all optimizer numeric inputs.
    annotated=deepcopy(candidates)
    for c in annotated:
        for p in c:p['game_environment_research']={'target':8,'bonus':1e9,'actual_cash':True}
    chosen,metadata_report=select_single_lineup(annotated,strategy=CLASSIC_SINGLE_LINEUP_STRATEGY_ID)
    assert [p['player_id'] for p in chosen[0]]==[p['player_id'] for p in selected[0]]
    assert metadata_report['recommended']['selection_score']==report['recommended']['selection_score']


def test_unverified_player_market_and_future_model_rows_remain_unavailable():
    roster,frozen=review_fixture();p=frozen['player_pool'][0]
    pid=p['player_id'];p['market_context_point_in_time_safe']=False
    p['projection_created_at']='2099-01-01T00:00:00Z'
    p['ownership_observed_at']='2099-01-01T00:00:00Z';rehash(frozen)
    selected=next(x for x in review(roster,frozen)['rows'] if x['player_id']==pid)
    assert selected['game_total'] is None and selected['projection'] is None and selected['projected_ownership'] is None


def test_research_endpoint_provenance_matches_reproduced_results():
    from hashlib import sha256
    from backend.app.api.product_routes import get_classic_environment_research
    notes=get_classic_environment_research()
    root=Path(__file__).resolve().parents[4]
    source=root/notes['source']['path']
    assert sha256(source.read_bytes()).hexdigest()==notes['source']['sha256']
    assert notes['sample']['top_10_entries']==93218 and notes['sample']['independent_slates']==3
    assert notes['label']=='RESEARCH_ONLY / OBSERVATIONAL / NOT PRODUCTION VALIDATED'
    assert notes['cash_outcomes']=='Unavailable'


def test_api_contract_returns_read_only_review_for_one_primary_and_legacy_none():
    from unittest.mock import MagicMock
    from backend.app.api.product_routes import get_optimizer_results
    from backend.app.product_services.optimizer import OptimizerJob
    roster,frozen=review_fixture();selected,report=select_single_lineup([roster],strategy=CLASSIC_SINGLE_LINEUP_STRATEGY_ID)
    job=OptimizerJob(job_id='fixture',status='completed',created_at=NOW,updated_at=NOW,season=NOW.year,week=5,
        slate='SUNDAY_MAIN',strategy=CLASSIC_SINGLE_LINEUP_STRATEGY_ID,contest_format='classic',objective='cash',
        params={'classic_evidence_snapshot':frozen,'strategy_runtime':{'single_lineup':report}},data_cutoff_at=CUT,results=selected)
    original=deepcopy(job)
    service=MagicMock();service.get_job.return_value=job
    response=get_optimizer_results('fixture',service=service)
    assert response.classic_game_environment_review['primary_lineup_only'] is True
    assert len(response.results)==1 and job==original
    service.run_job.assert_not_called()
    job.strategy='classic_large_gpp_v1'
    assert get_optimizer_results('fixture',service=service).classic_game_environment_review is None
