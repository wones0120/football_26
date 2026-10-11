from unittest.mock import patch
import pytest
from backend.app.product_services.classic_season_rank_preferences import build_rankings, preference, validate
from backend.app.product_services.optimizer import OptimizerService
from backend.app.tests.product.test_single_lineup import roster


def evidence():
    aliases=[dict(source_system=source, source_key='a', player_master_id='id-a') for source in ['nflreadpy','pfr']]
    stat=dict(season=2026,week=1,source_system='nflreadpy',player_id='a',position='RB',ingest_run_id='stats-1',raw_row_json={'rushing_yards':100,'carries':10})
    snap=dict(season=2026,week=2,pfr_player_id='a',position='RB',offense_snaps=10,ingest_run_id='snaps-2')
    return [stat], [snap], aliases


def test_prior_games_zero_participation_duplicate_scores_and_future_exclusion():
    stats,snaps,aliases=evidence()
    future={**stats[0], 'week':3, 'raw_row_json':{'rushing_yards':1000}}
    rows,_=build_rankings(stats+stats+[future],snaps,aliases,season=2026,week=3)
    assert len(rows)==1
    assert rows[0]['games_played']==2 and rows[0]['ppg']==6.5
    assert [g['week'] for g in rows[0]['games']]==[1,2]


def test_conflicting_scores_and_ambiguous_identity_stay_unranked():
    stats,snaps,aliases=evidence()
    conflicting={**stats[0], 'raw_row_json':{'rushing_yards':200,'carries':10}}
    rows,warnings=build_rankings(stats+[conflicting],snaps,aliases,season=2026,week=3)
    assert not rows and warnings['conflicting_players']==1
    aliases += [dict(source_system='nflreadpy',source_key='a',player_master_id='other')]
    rows,warnings=build_rankings(stats,[],aliases,season=2026,week=3)
    assert not rows and warnings['unresolved_stat_rows']==1


def test_cutoff_ties_league_wide_and_disabled_does_not_read_sources():
    assert preference(None,{},season=2026,week=1)['enabled'] is False
    rows=[dict(player_id=str(i),position='RB',ppg=score) for i,score in enumerate([10,10,5,0])]
    with patch('backend.app.product_services.classic_season_rank_preferences.load_rankings',return_value=dict(rows=rows,warnings={},source_sha256='hash')):
        report=preference(None,{'season_ppg_top_pct_rb':25},season=2026,week=3)
    assert report['eligible_ids']['RB']==['0','1']
    assert report['cutoffs']['RB']['ranked_players']==4


@pytest.mark.parametrize('value',[0,30,True,'25',101])
def test_reject_invalid_settings(value):
    with pytest.raises(ValueError):validate({'season_ppg_top_pct_qb':value},showdown=False)


def test_week_one_and_captain_reject_enabled_limits():
    with pytest.raises(ValueError,match='Week 1'):preference(None,{'season_ppg_top_pct_rb':25},season=2026,week=1)
    with pytest.raises(ValueError,match='Classic'):validate({'season_ppg_top_pct_qb':50},showdown=True)


def test_final_validator_checks_flex_natural_position_and_unknown_history():
    rows=roster();rows[7]['position']='RB'
    allowed={p['player_id'] for p in rows if p['position']=='RB'}
    kwargs=dict(requested_lineups=1,max_exposure=1,enforce_single_te=False,avoid_dst_opponents=False,season_ppg_eligible_ids={'RB':allowed})
    assert OptimizerService._validate_classic_lineups([rows],**kwargs)[0]
    allowed.remove(rows[7]['player_id'])
    ok,reason=OptimizerService._validate_classic_lineups([rows],**kwargs)
    assert not ok and 'season-average RB' in reason


def test_missing_historical_coverage_blocks_instead_of_using_partial_rankings():
    from unittest.mock import MagicMock
    from backend.app.product_services.classic_season_rank_preferences import load_rankings
    engine=MagicMock()
    engine.connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value=[]
    with pytest.raises(ValueError,match='complete stats and snap coverage'):
        load_rankings(engine,season=2026,week=3)


def test_optional_kicker_scoring_counts_zero_games_and_excludes_current_week():
    stats,snaps,aliases=evidence()
    stats[0].update(position='K',raw_row_json={'fg_att':3,'fg_made_40_49':1,'fg_made_50_59':1,'pat_made':2,'fg_missed':1})
    snaps[0].update(position='K',offense_snaps=0,st_snaps=3)
    future={**stats[0],'week':3,'raw_row_json':{'fg_made_50_59':20}}
    rows,_=build_rankings(stats+[future],snaps,aliases,season=2026,week=3,include_kickers=True)
    assert rows[0]['ppg']==5.5 and rows[0]['games_played']==2
    assert build_rankings(stats,snaps,aliases,season=2026,week=3)[0]==[]
