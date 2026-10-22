from copy import deepcopy
import pytest
from backend.app.product_services.deep_coverage_response import build_deep_coverage_response,FAMILIES
from backend.app.product_services.coverage_receiver_performance import VERSION as PARENT
from backend.app.product_services.participation_source_components import VERSION as SOURCE
G='2023_01_BUF_MIA'


def fixture():
    events=[];part=[];depth=[]
    for play,family,air,complete,epa in [(1,'COVER_2',20,True,3.),(2,'COVER_3',19.99,False,-2.),(3,'COVER_3',35,False,-1.),(4,'COMBO',-3,True,0.)]:
        events.append(dict(game_id=G,play_id=str(play),offense='BUF',defense='MIA',eligible_target_attempt=True,source_join_conflict=False,complete_pass=complete,target_play_EPA=epa))
        part.append(dict(game_id=G,play_id=str(play),season=2023,week=1,native_phase='REG',possession_team='BUF',measurements=dict(defense_coverage_type=family)))
        depth.append(dict(game_id=G,play_id=play,season=2023,week=1,season_type='REG',posteam='BUF',defteam='MIA',air_yards=air))
    parent=dict(version=PARENT,season=2023,before_period=202607,pregame_serving_eligible=False,semantic_sha256='parent',event_basis=events,missing_PBP_game_ids=[],
        expected_games=[dict(game_id=G,season=2023,week=1,sides=['BUF','MIA'])])
    part=dict(version=SOURCE,season=2023,pregame_serving_eligible=False,semantic_sha256='part',rows=part)
    return parent,part,depth


def build(p=None,c=None,d=None):
    a,b,e=fixture();return build_deep_coverage_response(p or a,c or b,e if d is None else d)

def offense(out):return next(r for r in out['game_rows']if r['team']=='BUF')['offense']


def test_direct_family_conditioned_depth_threshold_outcomes_opportunity_and_baseline():
    out=build();c=offense(out)
    assert c['COVER_2']['reported_family']['exact_deep_attempts']==1
    assert c['COVER_3']['reported_family']['exact_official_attempts']==2
    assert c['COVER_3']['reported_family']['deep_opportunity_fraction']==.5
    assert c['COVER_2']['family_minus_other_deep_EPA']==4
    assert c['COVER_2']['family_minus_other_deep_completion']==1
    assert c['COMBO']['reported_family']['exact_deep_attempts']==0
    assert out['deep_threshold_air_yards']==20 and out['pregame_serving_eligible']is False and out['forecast']is None
    defender=next(r for r in out['game_rows']if r['team']=='MIA')['defense']
    assert defender==c


def test_all_published_literal_families_retained_without_safety_count_inference():
    for family in FAMILIES:
        p,c,d=fixture();c['rows'][0]['measurements']['defense_coverage_type']=family
        out=build(p,c,d)
        assert out['event_basis'][0]['reported_family']==family
    assert 'BLOWN'in FAMILIES and 'COMBO'in FAMILIES and '2_MAN'in FAMILIES


@pytest.mark.parametrize('label',[None,'','MAN_COVERAGE','COVER_99','PREVENT'])
def test_missing_unsupported_category_masks_full_cells_and_other_baseline(label):
    p,c,d=fixture();c['rows'][0]['measurements']['defense_coverage_type']=label
    v=offense(build(p,c,d))['COVER_3']
    assert v['reported_family']['completion_rate']is None
    assert v['other_explicit_classified_families']['completion_rate']is None
    assert v['family_minus_other_deep_EPA']is None
    assert v['reported_family']['known_outcome_sample_EPA']==-1


def test_unknown_depth_affects_only_compatible_family_and_its_complement():
    p,c,d=fixture();d[0]['air_yards']=None
    v=offense(build(p,c,d))
    assert v['COVER_2']['reported_family']['exact_deep_attempts']is None
    assert v['COVER_3']['reported_family']['EPA_per_deep_attempt']==-1
    assert v['COVER_3']['other_explicit_classified_families']['EPA_per_deep_attempt']is None
    assert v['COVER_3']['family_minus_other_deep_EPA']is None


def test_known_nondeep_unknown_category_does_not_pollute_deep_outcome_sample():
    p,c,d=fixture();c['rows'][1]['measurements']['defense_coverage_type']=None
    v=offense(build(p,c,d))['COVER_2']
    assert v['reported_family']['EPA_per_deep_attempt']==3
    assert v['family_minus_other_deep_EPA']==4
    assert v['reported_family']['deep_opportunity_fraction']is None


def test_unknown_eligibility_deep_attempt_is_not_zero_but_known_nondeep_excludes_it():
    p,c,d=fixture();p['event_basis'][0]['eligible_target_attempt']=None
    assert offense(build(p,c,d))['COVER_2']['reported_family']['exact_deep_attempts']is None
    d[0]['air_yards']=10
    assert offense(build(p,c,d))['COVER_2']['reported_family']['exact_deep_attempts']==0
    assert offense(build(p,c,d))['COVER_2']['reported_family']['exact_official_attempts']is None


def test_missing_outcomes_separate_epa_from_completion_masks_signed_values_preserved():
    p,c,d=fixture();p['event_basis'][0]['complete_pass']=None
    a=offense(build(p,c,d))['COVER_2']['reported_family']
    assert a['EPA_per_deep_attempt']==3 and a['completion_rate']is None
    p['event_basis'][0]['target_play_EPA']=None;p['event_basis'][0]['complete_pass']=True
    a=offense(build(p,c,d))['COVER_2']['reported_family']
    assert a['completion_rate']==1 and a['EPA_per_deep_attempt']is None
    assert offense(build())['COVER_3']['reported_family']['EPA_per_deep_attempt']==-1


def test_empty_family_and_zero_attempts_undefined_not_zero_response():
    c=offense(build())['COVER_9']
    assert c['reported_family']['exact_deep_attempts']==0
    assert c['reported_family']['completion_rate']is None and c['family_minus_other_deep_EPA']is None
    p,c,d=fixture()
    for e in p['event_basis']:e['eligible_target_attempt']=False
    assert all(v['reported_family']['exact_official_attempts']==0 for v in offense(build(p,c,d)).values())


def test_missing_participation_native_join_conflict_and_missing_games_unknown():
    p,c,d=fixture();c['rows']=c['rows'][1:]
    assert offense(build(p,c,d))['COVER_2']['reported_family']['exact_deep_attempts']is None
    p,c,d=fixture();c['rows'][0]['possession_team']='MIA'
    assert build(p,c,d)['event_basis'][0]['source_join_conflict']is True
    p,c,d=fixture();p['missing_PBP_game_ids']=[G];p['event_basis']=[];d=[]
    assert offense(build(p,c,d))['COVER_2']['reported_family']['exact_deep_attempts']is None


def test_duplicate_missing_native_depth_or_period_side_mismatch_rejected():
    p,c,d=fixture();d.append(deepcopy(d[0]))
    with pytest.raises(ValueError,match='Duplicate PBP'):build(p,c,d)
    p,c,d=fixture();d=d[1:]
    with pytest.raises(ValueError,match='native event/depth'):build(p,c,d)
    p,c,d=fixture();d[0]['posteam']='MIA'
    with pytest.raises(ValueError,match='side differs'):build(p,c,d)
    p,c,d=fixture();d[0]['week']=2
    with pytest.raises(ValueError,match='game/period'):build(p,c,d)


def test_source_profile_pools_counts_before_rates_and_known_depth_sample_excludes_missing():
    p,c,d=fixture();d[1]['air_yards']=None
    out=build(p,c,d);profile=next(r for r in out['profiles']if r['team']=='BUF')['offense']
    assert profile['COVER_3']['reported_family']['known_depth_sample_opportunity_fraction']==1
    assert profile['COVER_3']['reported_family']['deep_opportunity_fraction']is None
    assert profile['COVER_2']['reported_family']['EPA_per_deep_attempt']==3


def test_unknown_native_side_masks_both_team_candidates_no_position_filter():
    p,c,d=fixture();p['event_basis'][0].update(offense=None,defense=None);d[0].update(posteam=None,defteam=None)
    out=build(p,c,d)
    assert all(r['offense']['COVER_2']['reported_family']['exact_deep_attempts']is None for r in out['game_rows'])


def test_two_games_pool_counts_before_response_rates():
    p,c,d=fixture();other='2023_02_BUF_MIA'
    p['expected_games'].append(dict(game_id=other,season=2023,week=2,sides=['BUF','MIA']))
    for number in range(3):
        p['event_basis'].append(dict(game_id=other,play_id=str(number),offense='BUF',defense='MIA',eligible_target_attempt=True,source_join_conflict=False,complete_pass=False,target_play_EPA=-1.))
        c['rows'].append(dict(game_id=other,play_id=str(number),season=2023,week=2,native_phase='REG',possession_team='BUF',measurements=dict(defense_coverage_type='COVER_2')))
        d.append(dict(game_id=other,play_id=number,season=2023,week=2,season_type='REG',posteam='BUF',defteam='MIA',air_yards=25))
    v=next(x for x in build(p,c,d)['profiles']if x['team']=='BUF')['offense']['COVER_2']['reported_family']
    assert v['completion_rate']==.25 and v['EPA_per_deep_attempt']==0


def test_actual_native_parent_reader_bytes_and_future_publication(tmp_path):
    from pathlib import Path
    from datetime import datetime,UTC,timedelta
    import json,hashlib
    from backend.app.product_services.deep_coverage_response import read_native_attempt_parent
    from backend.app.product_services.evaluation_record import digest
    p,_,_=fixture();now=datetime.now(UTC)
    p['semantic_sha256']=digest({k:v for k,v in p.items()if k not in ('semantic_sha256','pregame_serving_eligible')})
    p['provenance']=dict(actual_read_at=(now-timedelta(seconds=2)).isoformat(),actual_derived_at=(now-timedelta(seconds=1)).isoformat(),producer_code_hashes={
        str(path):hashlib.sha256(path.read_bytes()).hexdigest()for path in (Path('backend/app/product_services')/(name+'.py')for name in ('coverage_receiver_performance','participation_source_components','fumble_event_components'))})
    raw=json.dumps(p).encode();path=tmp_path/'parent.json';path.write_bytes(raw)
    ref=dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    assert read_native_attempt_parent(ref,actual_read_at=now,published_at=now,directory=tmp_path)['season']==2023
    with pytest.raises(ValueError,match='chronology'):
        read_native_attempt_parent(ref,actual_read_at=now,published_at=now+timedelta(days=1),directory=tmp_path)
    path.write_bytes(raw+b' ')
    with pytest.raises(ValueError,match='bytes differ'):
        read_native_attempt_parent(ref,actual_read_at=now,published_at=now,directory=tmp_path)


def test_missing_participation_phase_uses_explicit_same_native_pbp_reg_not_absence():
    p,c,d=fixture();c['rows'][0]['native_phase']=None
    assert offense(build(p,c,d))['COVER_2']['reported_family']['exact_deep_attempts']==1
    c['rows'][0]['native_phase']='POST'
    assert offense(build(p,c,d))['COVER_2']['reported_family']['exact_deep_attempts']is None
