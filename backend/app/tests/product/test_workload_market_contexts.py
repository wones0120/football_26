from copy import deepcopy
import pytest
from backend.app.product_services.workload_market_contexts import normalize_archived_market_context,build_workload_market_contexts
from backend.app.tests.product.test_workload_venue_splits import sources

def fixture():
    weekly,schedule=sources();raw=[]
    schedule['provenance']=dict(snapshot_id='indexed-schedule',sha256='verified-source-sha')
    for game in schedule['game_rows']:
        game['home_team']='LAR' if game['home_team']=='LA' else game['home_team']
        game['away_team']='LAR' if game['away_team']=='LA' else game['away_team']
        game['game_id']=f"{game['season']}_{game['week']:02d}_{game['away_team']}_{game['home_team']}"
        # LAR has a -3 wager spread in all four games: native margin flips by venue.
        raw.append(dict(**{k:game[k] for k in ('game_id','season','week','game_type','home_team','away_team')},
            total_line=40+game['week'],spread_line=3 if game['home_team']=='LAR' else -3,
            home_score=90,away_score=1,total=91))
    return weekly,schedule,raw

def run(w=None,s=None,raw=None):
    weekly,schedule,records=fixture();w=w or weekly;s=s or schedule
    m=normalize_archived_market_context(records if raw is None else raw,s,before_period=202607)
    return build_workload_market_contexts(w,s,m,before_period=202607)

def test_official_count_vs_total_exact_descriptive_slope_not_score_substitution():
    r=run()['rows'][0];m=r['metrics']['G21-M02']['channels']['rush_attempts']
    assert m['slope']==1 and m['population_covariance']==1.25 and m['known_paired_logs']==4
    assert [x['market']['game_total_line'] for x in r['logs']]==[41,42,43,44]
    assert run()['forecast'] is None and run()['pregame_serving_eligible'] is False

def test_spread_sign_and_team_implied_points_same_game_orientation():
    w,s,raw=fixture();m=normalize_archived_market_context(raw,s,before_period=202607)
    for row in m['rows']:
        assert row['team_spread_line']==(-3 if row['team']=='LAR' else 3)
        assert row['team_implied_points']==(row['game_total_line']-row['team_spread_line'])/2
    r=run()['rows'][0];assert r['metrics']['G21-M03']['channels']['rush_attempts']['slope'] is None
    assert r['metrics']['G21-M04']['channels']['rush_attempts']['slope']==2

@pytest.mark.parametrize('kind',['quote','count','unbound'])
def test_unknown_context_exposure_never_completecase_exact(kind):
    w,s,raw=fixture()
    if kind=='quote':raw[0]['total_line']=None
    elif kind=='count':w['rows'][0]['metrics']['G07-M01']['denominator']=None
    else:w['rows'][0]['team']=None
    r=run(w,s,raw);m=r['rows'][0]['metrics']['G21-M02']['channels']['rush_attempts']
    assert m['slope'] is None
    assert any(x['metrics']['G21-M02']['channels']['rush_attempts']['unknown_pairs'] for x in r['rows'])

def test_single_pair_or_no_line_variation_is_undefined_not_zero():
    w,s,raw=fixture();w['rows']=w['rows'][:1]
    m=run(w,s,raw)['rows'][0]['metrics']['G21-M02']['channels']['rush_attempts']
    assert m['slope'] is None and m['population_covariance'] is None
    for x in raw:x['total_line']=42
    assert run(raw=raw)['rows'][0]['metrics']['G21-M02']['channels']['rush_attempts']['slope'] is None

def test_zero_official_counts_are_known_and_missing_rows_not_added():
    w,s,raw=fixture()
    for r in w['rows']:r['metrics']['G07-M01']['denominator']=0
    a=run(w,s,raw)['rows'][0]['metrics']['G21-M02']['channels']['rush_attempts']
    assert a['slope']==0 and a['known_paired_logs']==4

@pytest.mark.parametrize('kind',['orientation','duplicate','score','nonfinite','future'])
def test_native_source_and_market_guards(kind):
    w,s,raw=fixture()
    if kind=='orientation':raw[0]['home_team']='GB'
    elif kind=='duplicate':raw.append(deepcopy(raw[0]))
    elif kind=='score':raw[0]['total_line']=91
    elif kind=='nonfinite':raw[0]['spread_line']=float('nan')
    else:w['rows'][0]['season']=2027
    if kind=='nonfinite':
        r=run(w,s,raw);assert r['rows'][0]['metrics']['G21-M03']['channels']['rush_attempts']['unknown_pairs']==1
    else:
        with pytest.raises(ValueError):run(w,s,raw)

def test_paired_source_attachment_and_implied_contradiction_reject():
    w,s,raw=fixture();m=normalize_archived_market_context(raw,s,before_period=202607)
    m['provenance']['snapshot_id']='other-source'
    with pytest.raises(ValueError):build_workload_market_contexts(w,s,m,before_period=202607)
    m=normalize_archived_market_context(raw,s,before_period=202607);m['rows'][0]['team_implied_points']=99
    with pytest.raises(ValueError):build_workload_market_contexts(w,s,m,before_period=202607)

def test_source_row_order_and_execution_clocks_not_extra_measurements():
    w,s,raw=fixture();a=run(w,s,raw)['semantic_sha256'];raw.reverse();w['rows'].reverse()
    for row in w['rows']:row['source_ref']['imported_at']='2026-10-20T04:00:00Z'
    assert run(w,s,raw)['semantic_sha256']==a

def test_market_period_is_prior_and_conflicting_opposite_side_rejected():
    w,s,raw=fixture();future=deepcopy(s['game_rows'][0]);future.update(season=2026,week=7,game_id='2026_07_SF_LAR');s['game_rows'].append(future)
    raw.append({**future,'total_line':50,'spread_line':7})
    m=normalize_archived_market_context(raw,s,before_period=202607)
    assert all(r['season']*100+r['week']<202607 for r in m['rows'])
    home=m['rows'][0];home['game_total_line']+=1;home['team_implied_points']=(home['game_total_line']-home['team_spread_line'])/2
    with pytest.raises(ValueError,match='same-game'):build_workload_market_contexts(w,s,m,before_period=202607)
