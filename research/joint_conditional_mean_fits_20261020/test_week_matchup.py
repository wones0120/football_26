from evaluate_week_matchup import matched_report,metric,opponent,tags
import pytest


def test_paired_week_macro_and_matchup_keep_counts():
    rows=[dict(year=2025,week=4,game_id='2025_04_A_B',team='A',opponent='B',label=0,new=1,saved=2,tags=['all','zero']),dict(year=2025,week=5,game_id='2025_05_A_B',team='A',opponent='B',label=3,new=1,saved=2,tags=['all','positive'])]
    report=matched_report(rows)
    assert report['macro_week']['2025']['improved_weeks']==1 and report['macro_week']['2025']['worsened_weeks']==1
    assert report['pooled_by_stratum']['2025|all']['new']['n']==2
    assert report['paired_by_native_team_opponent']['2025_04_A_B|A|vs_B']['new']['n']==1
    assert metric([])['mae']is None


def test_native_team_alias_and_unknowns_not_replacement():
    assert opponent('2025_04_LA_SF','LAR')=='SF'
    with pytest.raises(ValueError):opponent('2025_04_LA_SF','BUF')
    assert 'prior3_exposure_unknown'in tags(dict(kind='candidate',label=1),'UNKNOWN',None)
    assert 'prior3_exposure_known_zero'in tags(dict(kind='candidate',label=1),'RB',0)
