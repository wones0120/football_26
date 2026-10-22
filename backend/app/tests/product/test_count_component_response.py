from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

import pandas as pd
import pytest

from backend.app.product_services.count_component_response import component_response

IDS=[str(UUID(int=i)) for i in (1,2,3)]
NOW=datetime(2026,9,25,tzinfo=UTC)


def fixture():
    rows=[]
    for period in (202601,202602,202603):
        for i,(pid,pos,passes,rush,targets,py,ints,comp,ry,rec,recv) in enumerate([
            (IDS[0],'QB',10,1,0,80,1,6,2,0,0),
            (IDS[1],'RB',0,4,3,0,0,0,16,2,20),
            (IDS[2],'WR',0,0,5,0,0,0,0,4,60)]):
            rows.append(dict(player_master_id=pid,source_player_id='native'+str(i),team='BUF',position=pos,period=period,
                pass_attempts=passes,rush_attempts=rush,targets=targets,passing_yards=py,passing_interceptions=ints,
                completions=comp,rushing_yards=ry,receptions=rec,receiving_yards=recv,source_id=period*10+i,
                imported_at='2026-09-24T10:00:00Z'))
    history=pd.DataFrame(rows)
    reference=dict(version='SYNTHETIC_COUNT',before_period=202604,teams={'BUF':dict(pass_attempts=10.,rush_attempts=5.,targets=8.)},players=[])
    for pid,pos,counts in [(IDS[0],'QB',dict(pass_attempts=10.,rush_attempts=1.,targets=None)),
                           (IDS[1],'RB',dict(pass_attempts=None,rush_attempts=4.,targets=3.)),
                           (IDS[2],'WR',dict(pass_attempts=None,rush_attempts=0.,targets=5.))]:
        reference['players'].append(dict(player_master_id=pid,position=pos,team='BUF',counts=counts,
            raw_history={c:dict(periods=[202601,202602,202603]) for c in counts},conditional_on='SYNTHETIC verified role'))
    return history,reference,{IDS[0]:10.,IDS[1]:6.,IDS[2]:12.}


def scaled(reference,factor):
    value=deepcopy(reference)
    for budget in value['teams'].values():
        for k in budget:budget[k]*=factor
    for p in value['players']:
        p['counts']={k:v*factor if v is not None else None for k,v in p['counts'].items()}
    return value


def test_matched_count_change_drives_signed_linear_dk_delta_and_shared_budgets():
    history,reference,bases=fixture()
    result=component_response(history,reference,scaled(reference,2),bases,before_period=202604,cutoff=NOW)
    actors={p['player_master_id']:p for p in result['players']}
    assert actors[IDS[0]]['delta_points']==pytest.approx(2.4)
    assert actors[IDS[1]]['delta_points']==pytest.approx(5.6)
    assert actors[IDS[2]]['delta_points']==pytest.approx(10.)
    assert actors[IDS[2]]['conditional_mean']==22.
    new=result['new_shared_budgets']['BUF']
    assert new['passing_yards']==160 and new['receptions']==12
    assert new['reconciliation']['receiving_yards']['allocated']==pytest.approx(160)
    assert new['reconciliation']['receptions']['allocated']==12
    assert new['passing_yard_residual']==0
    reduced=component_response(history,reference,scaled(reference,.5),bases,before_period=202604,cutoff=NOW)
    assert reduced['players'][0]['delta_points']==pytest.approx(-1.2)


def test_partial_matched_components_anchor_diagnostic_and_signed_yards_stay_explicit():
    history,reference,bases=fixture()
    history.loc[history.player_master_id.eq(IDS[2]),'receiving_yards']=None
    bases[IDS[1]]=1.
    result=component_response(history,reference,scaled(reference,2),bases,before_period=202604,cutoff=NOW)
    actors={p['player_master_id']:p for p in result['players']}
    assert actors[IDS[2]]['delta_points']==4.
    assert actors[IDS[2]]['new_components']['receiving_yards'] is None
    assert 'receiving_yards' in actors[IDS[2]]['unchanged_unsupported_components']
    assert actors[IDS[1]]['anchoring_diagnostic']<0 and actors[IDS[1]]['anchor_inconsistency']
    history.loc[history.player_master_id.eq(IDS[0]),'rushing_yards']=-2
    new=deepcopy(reference);new['teams']['BUF']['rush_attempts']=6;new['players'][0]['counts']['rush_attempts']=2.
    signed=component_response(history,reference,new,bases,before_period=202604,cutoff=NOW)
    assert signed['players'][0]['delta_points']==pytest.approx(-.2)


@pytest.mark.parametrize('change',['negative','over_budget','targets_over_passes','team'])
def test_rejects_invalid_physical_counts_and_team_reassignment(change):
    history,reference,bases=fixture();new=deepcopy(reference)
    if change=='negative':new['players'][0]['counts']['rush_attempts']=-1
    elif change=='over_budget':new['players'][1]['counts']['rush_attempts']=6
    elif change=='targets_over_passes':new['teams']['BUF']['targets']=11
    else:new['players'][1]['team']='MIA'
    with pytest.raises(ValueError):component_response(history,reference,new,bases,before_period=202604,cutoff=NOW)


def test_recapture_ids_and_execution_clocks_are_not_numerical_dependency():
    history,reference,bases=fixture();new=scaled(reference,2)
    first=component_response(history,reference,new,bases,before_period=202604,cutoff=NOW)
    history['source_id']+=100
    history['imported_at']='2026-09-24T11:00:00Z'
    reference['created_at']='2026-09-24T12:00:00Z';new['created_at']='2026-09-24T12:00:00Z'
    second=component_response(history,reference,new,bases,before_period=202604,cutoff=NOW)
    assert first['semantic_sha256']==second['semantic_sha256']
    assert first['reference_count_sha256']!=second['reference_count_sha256']
