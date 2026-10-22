from copy import deepcopy
import pytest
from backend.app.product_services.goal_to_go_allocation import build_goal_to_go_allocation,INPUT_VERSION,CHANNELS


def counter(n):return dict(counted_lower_bound=n,exact_within_log_count=n,unknown_eligibility_events=0,unattributed_eligible_events=0)

def source():
    p=dict(version=INPUT_VERSION,before_period=202603,evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,full_team_denominators=[],actor_game_rows=[],identity_review_requests=[])
    for week,n,d in [(1,1,2),(2,1,8)]:
        gid=f'2026_{week:02}_SF_WAS';p['full_team_denominators'].append(dict(game_id=gid,team='SF',channels={ch:dict(goal_to_go=counter(d)) for ch in CHANNELS}))
        p['actor_game_rows'].append(dict(game_id=gid,team='SF',source_player_id='native',player_master_id='uuid',goal_to_go_channel_shares={ch:dict(numerator=counter(n)) for ch in CHANNELS}))
    return p


def run(p=None):return build_goal_to_go_allocation(p or source(),before_period=202603)


def test_pool_counts_before_dividing_not_average_shares():
    w=run()['windows'][1];assert w['observed_games']==2
    assert w['actors'][0]['channels']['targets']['share']==.2
    assert w['actors'][0]['channels']['pass_attempts']['share']==.2


def test_last_game_separate_and_overlap_not_added():
    w=run()['windows'][0];assert w['actors'][0]['channels']['pass_attempts']['share']==.125
    assert set(w['team_channels'])==set(CHANNELS)


def test_missing_actor_game_stays_unknown_with_known_lower_sample():
    p=source();p['actor_game_rows'].pop(0)
    m=run(p)['windows'][1]['actors'][0]['channels']['targets']
    assert m['share'] is None and m['known_observed_actor_count']==1 and len(m['missing_actor_channel_games'])==1


def test_missing_channel_never_native_actor_zero():
    p=source();p['actor_game_rows'][0]['goal_to_go_channel_shares'].pop('targets')
    assert run(p)['windows'][1]['actors'][0]['channels']['targets']['share'] is None


def test_unknown_team_eligibility_masks_not_completecase():
    p=source();p['full_team_denominators'][0]['channels']['targets']['goal_to_go']['exact_within_log_count']=None
    assert run(p)['windows'][1]['actors'][0]['channels']['targets']['share'] is None


def test_unattributed_known_source_mass_is_retained_not_donated():
    p=source();c=p['full_team_denominators'][0]['channels']['targets']['goal_to_go'];c['unattributed_eligible_events']=1
    p['actor_game_rows'][0]['goal_to_go_channel_shares']['targets']['numerator']['exact_within_log_count']=None
    m=run(p)['windows'][1]['actors'][0]['channels']['targets']
    assert m['full_team_denominator']['known_unattributed_eligible_events']==1 and m['share'] is None


def test_zero_budget_undefined_even_known_actor_zero():
    p=source()
    for r in p['full_team_denominators']:r['channels']['targets']['goal_to_go']=counter(0)
    for r in p['actor_game_rows']:r['goal_to_go_channel_shares']['targets']['numerator']=counter(0)
    assert run(p)['windows'][1]['actors'][0]['channels']['targets']['share'] is None


@pytest.mark.parametrize('kind',['future','duplicate','canonical','budget','serving'])
def test_native_time_identity_budget_guard(kind):
    p=source()
    if kind=='future':p['full_team_denominators'][0]['game_id']='2026_03_SF_WAS'
    if kind=='duplicate':p['actor_game_rows']*=2
    if kind=='canonical':p['actor_game_rows'][0]['player_master_id']='other'
    if kind=='budget':p['actor_game_rows'][0]['goal_to_go_channel_shares']['targets']['numerator']=counter(30)
    if kind=='serving':p['pregame_serving_eligible']=True
    with pytest.raises(ValueError):run(p)


def test_parent_not_modified():
    p=source();prior=deepcopy(p);run(p);assert p==prior


def test_reader_producer_bytes_publication_and_use(tmp_path,monkeypatch):
    import json,hashlib
    from pathlib import Path
    from backend.app.product_services import player_scoring_zone_components as module
    from backend.app.product_services.goal_to_go_allocation import load_goal_to_go_allocation,require_feature_use
    monkeypatch.chdir(tmp_path);p=source();p['provenance']=dict(actual_publication_at='2000-01-02T00:00:00+00:00',producer_code_sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest())
    raw=json.dumps(p).encode();sha=hashlib.sha256(raw).hexdigest();folder=tmp_path/'artifacts/player_scoring_zone_components';folder.mkdir(parents=True);path=folder/(sha+'.json');path.write_bytes(raw);ref=dict(path=str(path),sha256=sha,bytes=len(raw))
    out=load_goal_to_go_allocation(ref,actual_read_at='2000-01-03T00:00:00+00:00');assert out['windows']
    with pytest.raises(ValueError):load_goal_to_go_allocation(ref,actual_read_at='2000-01-01T00:00:00+00:00')
    with pytest.raises(ValueError):require_feature_use(out,purpose='optimizer')
    path.write_text('changed')
    with pytest.raises(ValueError):load_goal_to_go_allocation(ref,actual_read_at='2000-01-03T00:00:00+00:00')
