from copy import deepcopy
import pytest
from backend.app.tests.product.test_team_market_interactions import fixture
from backend.app.product_services.team_context_interaction_bins import build_team_context_interaction_bins,_summary,_quantile


def args():
    env,official,markets=fixture()
    # Same native team, alternate target venue, never infer venue from actor data.
    for source,key in ((env,'game_rows'),(official,'full_team_denominators'),(markets,'rows')):
        for r in source[key]:
            if r['game_id'].startswith('2026_04_'):r['game_id']='2026_04_SF_WAS'
    return env,official,markets


def run(a=None):return build_team_context_interaction_bins(*(a or args()),before_period=202607,reference_before_period=202604)


def test_native_home_away_materially_partitions_total_and_signed_spread_responses():
    r=run();m=r['rows'][0]['metrics']
    assert m['X01-M04']['home']['physical_snaps']['mean_response']==40
    assert m['X01-M04']['away']['physical_snaps']['mean_response'] is None
    assert m['X01-M04']['away']['physical_snaps']['known_sample_mean_response']==50
    assert m['X01-M05']['home']['official_carries']['known_sample_mean_condition']==-4
    assert m['X01-M05']['home']['called_pass_fraction']['mean_response']==.8
    assert r['forecast']is None and r['pregame_serving_eligible']is False


def test_reference_only_cutpoints_and_observed_target_not_lagged_response():
    a=args();old=run(a);a[0]['game_rows'][3]['known_offensive_snaps']=400
    new=run(a)
    assert old['cutpoints']==new['cutpoints']
    assert new['rows'][0]['metrics']['X01-M04']['home']['physical_snaps']['mean_response']==400
    assert new['cutpoints']['total_low_q25']==41.5 and new['cutpoints']['total_high_q75']==42.5
    assert new['cutpoints']['close_abs_spread_q50']==2


def test_high_low_total_and_signed_favorite_axes_consumed():
    a=args();a[2]['rows'][3].update(game_total_line=40,team_spread_line=1,team_implied_points=19.5)
    r=run(a)['rows'][0]['metrics']
    assert r['X01-M07']['groups']['underdog']['physical_snaps']['mean_response']==40
    assert r['X01-M06']['groups']['favorite']['physical_snaps']['known_sample_mean_response']==50
    assert r['X01-M07']['groups']['favorite']['physical_snaps']['known_paired_logs']==0
    assert r['X01-M08']['close']['physical_snaps']['mean_response']==40
    assert r['X01-M08']['large']['physical_snaps']['mean_response']is None


@pytest.mark.parametrize('channel',['physical_snaps','called_pass_fraction','official_carries'])
def test_missing_current_log_remains_unknown_in_observed_response(channel):
    r=run()['rows'][0]
    assert r['logs'][-1]['response'][channel]is None
    assert r['metrics']['X01-M06']['groups']['favorite'][channel]['unknown_pairs']==1


def test_missing_quote_does_not_become_pickem_or_known_condition():
    a=args();a[2]['rows'][3].update(game_total_line=None,team_spread_line=None,team_implied_points=None)
    r=run(a)['rows'][0]
    assert r['logs'][0]['favorite_state']is None
    assert r['metrics']['X01-M06']['unknown_condition_logs']==1
    assert r['metrics']['X01-M08']['unknown_condition_logs']==1


def test_mean_and_crossmoment_are_observed_not_fitted_slope():
    r=_summary([dict(condition_value=40,response={'physical_snaps':50}),dict(condition_value=44,response={'physical_snaps':70})],'physical_snaps')
    assert r['mean_response']==60 and r['population_covariance']==20
    assert r['known_sample_centered_cross_sum']==40 and r['predictive_fit']is False
    assert _summary([],'physical_snaps')['mean_response']is None
    assert _quantile([], .5)is None


def test_unknown_outcome_and_known_zero_not_conflated():
    a=args();a[1]['full_team_denominators'][3]['measurements']['official_carries']['exact_within_log_count']=0
    assert run(a)['rows'][0]['metrics']['X01-M04']['home']['official_carries']['mean_response']==0
    a[1]['full_team_denominators'][3]['measurements']['official_carries']['exact_within_log_count']=None
    assert run(a)['rows'][0]['metrics']['X01-M04']['home']['official_carries']['mean_response']is None


def test_parent_input_order_and_execution_provenance_not_semantic():
    a=args();old=run(a)
    for obj,key in ((a[0],'game_rows'),(a[1],'full_team_denominators'),(a[2],'rows')):obj[key].reverse()
    a[0]['provenance']['actual_read_at']='later execution'
    assert run(a)['semantic_sha256']==old['semantic_sha256']


def test_native_alias_home_team_not_false_away():
    a=args()
    for obj,key in ((a[0],'game_rows'),(a[1],'full_team_denominators'),(a[2],'rows')):
        for r in obj[key]:r['team']='LAR';r['game_id']=r['game_id'].replace('WAS','LA')
    assert run(a)['rows'][0]['logs'][0]['home']is True


def test_lineage_mismatch_rejected_not_merged():
    a=args();a[1]['provenance']['source']['snapshot_id']='other'
    with pytest.raises(ValueError,match='ancestry'):run(a)


def test_unknown_bin_membership_masks_exact_cell_not_measured_known_sample():
    a=args();a[2]['rows'][4].update(game_total_line=None,team_spread_line=None,team_implied_points=None)
    m=run(a)['rows'][0]['metrics']
    cell=m['X01-M06']['groups']['favorite']['physical_snaps']
    assert cell['known_sample_mean_response']==40 and cell['mean_response'] is None
    assert cell['unknown_condition_membership_logs']==1
    # Unknown line can belong in either spread cell and either total-tail state.
    for mid in ('X01-M06','X01-M07'):
        for group in m[mid]['groups'].values():
            assert group['physical_snaps']['mean_response'] is None
    for group in ('close','large'):
        assert m['X01-M08'][group]['physical_snaps']['population_covariance'] is None
        assert m['X01-M08'][group]['physical_snaps']['mean_response'] is None


def test_unknown_total_with_known_underdog_does_not_pollute_favorite_membership():
    a=args();a[2]['rows'][4].update(game_total_line=None,team_spread_line=2,team_implied_points=None)
    cell=run(a)['rows'][0]['metrics']['X01-M06']['groups']['underdog']['physical_snaps']
    assert cell['unknown_condition_membership_logs']==1 and cell['mean_response'] is None
