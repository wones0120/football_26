from copy import deepcopy

import pandas as pd
import pulp
import pytest

from scripts.audit_showdown_gameday import core_sensitivity, verify_salary_rows
from scripts.research_showdown_gameday import ReliabilityGatedFrozenService
from scripts.research_showdown_prelock import FrozenService


def salary_pair():
    rows=[{'ID':str(i),'Name':'Canonical Player','TeamAbbrev':'PIT','Position':'WR',
           'Roster Position':slot,'Game Info':'PIT@CLE','Salary':str(salary)}
          for i,slot,salary in [(10,'CPT',9000),(11,'FLEX',6000)]]
    stored=[{'source_player_key':row['ID'],'source_system':'draftkings','player_master_id':'canonical-id',
             'player_name':row['Name'],'team':'PIT','position':'WR','roster_position':row['Roster Position'],
             'game_info':row['Game Info'],'salary':int(row['Salary'])} for row in rows]
    return rows,stored


def test_slot_verification_uses_native_identity_and_requires_complete_pairs():
    rows,stored=salary_pair()
    assert verify_salary_rows(rows,stored)['canonical_players']==1
    stored[0]['player_master_id']='another-canonical'
    with pytest.raises(ValueError,match='Incomplete CPT/FLEX'):verify_salary_rows(rows,stored)


@pytest.mark.parametrize('failure', ['salary','native_id','team','duplicate','missing_slot'])
def test_salary_verification_fails_closed(failure):
    rows,stored=salary_pair()
    if failure=='salary':rows[0]['Salary']='10000'
    elif failure=='native_id':rows[0]['ID']='unknown'
    elif failure=='team':rows[0]['TeamAbbrev']='CLE'
    elif failure=='duplicate':rows.append(deepcopy(rows[0]))
    else:rows.pop()
    with pytest.raises(ValueError):verify_salary_rows(rows,stored)


def test_complete_ownership_still_cannot_bypass_calibration_gate(monkeypatch):
    frame=pd.DataFrame([{'ownership':20.,'captain_ownership':10.,'flex_ownership':20.}])
    monkeypatch.setattr(FrozenService,'_load_player_pool',lambda *a,**k:frame.copy())
    result=ReliabilityGatedFrozenService({})._load_player_pool()
    assert all(result[field].isna().all() for field in ('ownership','captain_ownership','flex_ownership'))
    assert result['diagnostic_ownership'].iloc[0]==20.
    assert frame['ownership'].iloc[0]==20.


def test_core_cap_compares_three_entries_under_identical_thesis_overlap_policy(monkeypatch):
    monkeypatch.setattr('scripts.research_showdown_prelock.make_cbc_solver',lambda backend:pulp.PULP_CBC_CMD(msg=False))
    records=[{'captain_id':str(i),'captain':str(i),'rank':i+1,'single_entry_score':1-i*.01,
              'research_thesis':str(min(i,2)),'mean':10-i,'p90':20-2*i} for i in range(4)]
    lineups=[[{'player_id':p} for p in core] for core in ['Xabcde','Xabfgh','Xabijk','abklmn']]
    result=core_sensitivity(records,lineups,'X',{})
    assert result['100_percent']['ranks']==[1,2,3]
    assert result['maximum_two']['ranks']==[1,2,4]
    assert result['three_entry_feasible']
    assert result['costs']['selector']==pytest.approx(.01)
    assert result['costs']['mean']==1
    assert result['100_percent']['theses']==result['maximum_two']['theses']


def test_missing_third_entry_is_not_reported_as_a_quality_gain(monkeypatch):
    monkeypatch.setattr('scripts.research_showdown_prelock.make_cbc_solver',lambda backend:pulp.PULP_CBC_CMD(msg=False))
    records=[{'captain_id':str(i),'captain':str(i),'rank':i+1,'single_entry_score':1.,'research_thesis':str(i),'mean':10,'p90':20} for i in range(3)]
    lineups=[[{'player_id':p} for p in core] for core in ['Xabcde','Xabfgh','Xabijk']]
    result=core_sensitivity(records,lineups,'X',{})
    assert not result['three_entry_feasible']
    assert result['maximum_two']['count']==2
    assert all(value is None for value in result['costs'].values())
