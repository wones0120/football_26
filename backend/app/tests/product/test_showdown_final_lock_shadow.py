"""Final decision count and identity invariants, independent of tonight's results."""
from copy import deepcopy
import json
from math import nan
import pytest

from backend.app.product_services.optimizer import _json_safe
from scripts.audit_showdown_gameday import save
from scripts.finalize_showdown_gameday_shadow import mask_diagnostic_ownership, read_frozen
from scripts.refresh_showdown_lock_inputs import normalize_name
from scripts.solve_showdown_final_lock_shadow import metrics


def example():
    lineups = [[{'player_id':p,'name':p} for p in core] for core in ['abcdef','abcdgh','abceij']]
    records = [{'rank':i+1,'single_entry_score':1-i*.01,'mean':60+i,'p90':100+i,
                'captain':str(i),'research_thesis':str(i)} for i in range(3)]
    return records,lineups


def test_underfilled_decision_is_not_reported_as_three_feasible_entries():
    records,lineups = example()
    result = metrics(records,lineups,[0,1])
    assert result=={'feasible':False,'count':2,'ranks':[1,2]}
    assert 'total_selector' not in result


def test_pairwise_overlap_uses_canonical_identity_and_exact_requested_count():
    records,lineups = example()
    lineups[1][0]['name']='Different display alias'
    result = metrics(records,lineups,[0,1,2])
    assert result['feasible'] and result['count']==3
    assert result['pairwise_overlap']==[4,4,3]
    assert result['total_selector']==pytest.approx(2.97)


def test_absent_dataframe_diagnostics_can_be_frozen_without_scoring_ownership(tmp_path):
    source = [{'player_id':'canonical','ownership':nan,'captain_ownership':nan,'flex_ownership':nan,
               'unavailable_diagnostic':nan,'projection':12.5,'p90':25.0}]
    masked = _json_safe(mask_diagnostic_ownership(deepcopy(source)))
    save(tmp_path/'freeze.json',{'lineups':[masked]})
    frozen = read_frozen(tmp_path/'freeze.json')['payload']['lineups'][0]
    assert frozen[0]['projection']==12.5 and frozen[0]['p90']==25.0
    assert frozen[0]['ownership'] is None and frozen[0]['unavailable_diagnostic'] is None
    assert frozen[0]['solver_ownership_weight']==0
    json.dumps(frozen,allow_nan=False)


def test_suffix_normalization_only_prepares_a_team_position_identity_check():
    assert normalize_name('KC Concepcion Jr.')==normalize_name('KC Concepcion')
    assert normalize_name('Robert Tonyan')!=normalize_name('Robert Thomas')
