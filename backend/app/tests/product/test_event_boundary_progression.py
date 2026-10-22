from copy import deepcopy
import pytest
from backend.app.product_services.event_boundary_progression import transfer,physical_key,choose,index_library,rollout,VERSION
from research.game_progression_pilot_20261020.scenario_01.scan_reference import choose as scan_choose
from backend.app.product_services.game_progression_runtime import STATS

def fixture(wait=30,kind='EXACT_NEXT_ACTION',phase='scrimmage'):
    start=dict(field100=75,phase=phase,down=1,distance=10,possession_side=0)
    c=dict(state_certified=True,start=start,source_side=0,wait=dict(seconds=wait,kind=kind),production=[dict.fromkeys(STATS,0)for _ in (0,1)],score_delta=[0,0],points_by_type=[{},{}],touchdown=False,endpoint=dict(start,field100=70,down=2,distance=5))
    c['production'][0].update(official_carries=1,physical_plays=1,rushing_yards=5)
    s=dict(start,half=1,remaining=100,scores=[0,0])
    return c,s

def test_cycle_wait_is_next_action_clock_not_source_game_ending():
    c,s=fixture();before=deepcopy((c,s));r=transfer(c,s)
    assert r['state']['remaining']==70 and r['state']['down']==2 and r['credits'][0]['official_carries']==1
    assert (c,s)==before

def test_deadline_survival_is_not_transport_of_source_half_end():
    c,s=fixture();s['remaining']=20
    r=transfer(c,s);assert r['state']['phase']=='halftime'and r['state']['remaining']==0
    assert r['credits'][0]['official_carries']==1 and 'NO_SUCCESSOR_BEFORE_GENERATED_DEADLINE'in r['clock_basis']

def test_source_censoring_does_not_invent_later_successor():
    c,s=fixture(wait=30,kind='RIGHT_CENSORED');c['endpoint']=None
    r=transfer(c,s);assert r['status']=='UNKNOWN_CENSORED_SUCCESSOR'and r['state']['remaining']==100
    s['remaining']=20;r=transfer(c,s);assert r['status']=='TRANSFERRED'and r['state']['phase']=='halftime'

def test_unknown_target_does_not_become_zero_or_erase_proven_state():
    c,s=fixture();c['production'][0]['official_targets']=None
    r=transfer(c,s);assert r['status']=='TRANSFERRED'and r['credits'][0]['official_targets']is None

def test_no_missing_source_state_or_negative_wait_repair():
    c,s=fixture();c['state_certified']=False;assert transfer(c,s)['status']=='UNKNOWN_SOURCE_STATE'
    c['state_certified']=True;c['wait']['seconds']=-1;assert transfer(c,s)['status']=='UNKNOWN_NEXT_ACTION_WAIT'

def test_touchdown_at_deadline_requires_proven_untimed_try():
    c,s=fixture();s['remaining']=10;c['touchdown']=True
    assert transfer(c,s)['status']=='UNKNOWN_REQUIRED_UNTIMED_TRY'
    c['endpoint'].update(phase='try',field100=15,down=None,distance=None)
    r=transfer(c,s);assert r['state']['phase']=='try'and r['state']['remaining']==0
    c,s=fixture(wait=0,phase='try');s['remaining']=0
    assert transfer(c,s)['state']['phase']=='halftime'

def test_special_phase_does_not_use_scrimmage_down_distance():
    assert physical_key(dict(field100=35,phase='kickoff',down=None,distance=0))==physical_key(dict(field100=35,phase='kickoff',down=None,distance=None))
    c,s=fixture();s['down']=3
    with pytest.raises(ValueError):transfer(c,s)

def test_missing_credits_and_score_cannot_be_fabricated():
    c,s=fixture();c['score_delta']=[3,0]
    with pytest.raises(ValueError):transfer(c,s)

@pytest.mark.parametrize('tier', ['ALL_CONTEXT','DROP_PRIORS','DROP_SCORE','EXACT_PHYSICAL_FALLBACK'])
@pytest.mark.parametrize('arm', ['contextual','control'])
def test_index_preserves_every_selection_interval_and_unknown_mass(tier,arm):
    c,s=fixture();context=dict(own_pass_share=.5,opponent_pass_share=.5)
    cycles=[]
    # Seven matches must fall back; eight qualify, including uncertified rows.
    for i in range(24):
        row=deepcopy(c);row.update(cycle_id=f'cycle:{23-i:02}',prior_bins=[1,1])
        row['start'].update(half=1,remaining=100,score_sign=0)
        if tier!='ALL_CONTEXT':row['prior_bins']=[0,0]if i>=7 else[1,1]
        if tier in('DROP_SCORE','EXACT_PHYSICAL_FALLBACK'):row['start']['score_sign']=1 if i>=7 else 0
        if tier=='EXACT_PHYSICAL_FALLBACK':row['start']['half']=2 if i>=7 else 1
        row['state_certified']=i%3!=0
        cycles.append(row)
    unrelated=deepcopy(cycles[0]);unrelated['start']['distance']=11;cycles.append(unrelated)
    library=dict(version=VERSION,cycles=cycles,boundaries=dict(own=[.3,.7],opponent=[.3,.7]),threats=[{'reason':'UNKNOWN'}])
    before=deepcopy(library);indexed=index_library(library)
    assert indexed==library and index_library(indexed)is indexed
    assert list(indexed.physical_index[physical_key(s)])==cycles[:-1]
    for u in [0.,1-2**-53]+[v/48 for v in range(48)]:
        actual=choose(indexed,s,context,arm,u)
        assert actual==scan_choose(library,s,context,arm,u)
        assert actual[1]==('EXACT_PHYSICAL_CONTROL'if arm=='control'else tier)
        assert actual[3]>0
    assert library==before

@pytest.mark.parametrize('phase', ['scrimmage','kickoff','try'])
def test_index_physical_and_context_edge_cases(phase):
    import random
    rng=random.Random(17);c,s=fixture(phase=phase);cycles=[]
    for i in range(80):
        row=deepcopy(c);row.update(cycle_id=f'{i:03}',prior_bins=['MISSING','MISSING'])
        row['start'].update(field100=rng.choice([75,35,None]),half=rng.choice([1,2]),remaining=rng.choice([None,120,121]),score_sign=rng.choice([-1,0,1,None]),down=rng.choice([1,2,None]),distance=rng.choice([10,5,None]))
        row['state_certified']=i%2==0;cycles.append(row)
    # Equal IDs retain stable source order; no deduplication is permitted.
    cycles.append(deepcopy(cycles[0]))
    library=dict(version=VERSION,cycles=cycles,boundaries=dict(own=[.3,.7],opponent=[.3,.7]))
    indexed=index_library(library);context=dict(own_pass_share=None,opponent_pass_share=None)
    for row in cycles:
        s.update(row['start'],scores=[3,7],possession_side=1,remaining=120,half=1)
        for arm in ('contextual','control'):
            u=rng.random();assert choose(indexed,s,context,arm,u)==scan_choose(library,s,context,arm,u)
    s['field100']=99
    assert choose(indexed,s,context,'control',0)==(None,'NO_EXACT_EVENT_STATE_SUPPORT',0,0)

def test_indexed_rollout_preserves_trace_totals_and_uniform_consumption(monkeypatch):
    import backend.app.product_services.event_boundary_progression as engine
    import random
    c,s=fixture(wait=1800,kind='RIGHT_CENSORED',phase='kickoff')
    c.update(cycle_id='one',prior_bins=['MISSING','MISSING'])
    c['start'].update(half=1,remaining=1800,score_sign=0)
    library=dict(version=VERSION,cycles=[c],threats=[],boundaries=dict(own=[.3,.7],opponent=[.3,.7]))
    openings=[dict(opening_id='one',certified=True,first_half=c['start'],second_half=c['start'])]
    contexts=[dict(own_pass_share=None,opponent_pass_share=None)]*2
    uniforms=[random.Random(17).random()]*3
    actual=rollout(index_library(library),openings,contexts,uniforms,'control',1,lambda:0)
    monkeypatch.setattr(engine,'choose',scan_choose)
    expected=rollout(library,openings,contexts,uniforms,'control',1,lambda:0)
    assert actual==expected and actual['status']=='COMPLETE_REGULATION'
    assert len(actual['trace'])==2

def test_reused_index_never_rescans_cycles():
    class GuardedCycles(list):
        forbid_scan=False
        def __iter__(self):
            if self.forbid_scan:raise AssertionError('Full-library scan after indexing')
            return super().__iter__()
    c,s=fixture();c.update(cycle_id='one',prior_bins=[1,1])
    c['start'].update(half=1,remaining=100,score_sign=0)
    cycles=GuardedCycles([c])
    library=index_library(dict(version=VERSION,cycles=cycles,boundaries=dict(own=[.3,.7],opponent=[.3,.7])))
    cycles.forbid_scan=True
    for u in (0.,.5,1-2**-53):
        assert choose(index_library(library),s,dict(own_pass_share=.5,opponent_pass_share=.5),'control',u)==(c,'EXACT_PHYSICAL_CONTROL',1,0)

@pytest.mark.parametrize('remaining,expected',[(29,'TRANSFERRED'),(30,'TRANSFERRED'),(31,'UNKNOWN_CENSORED_SUCCESSOR'),(1800,'UNKNOWN_CENSORED_SUCCESSOR')])
def test_censor_boundary_and_required_observations_are_explicit(remaining,expected):
    c,s=fixture(wait=30,kind='RIGHT_CENSORED');c['cycle_id']='native:one';s['remaining']=remaining
    c['production'][0]['official_targets']=None
    c['score_delta']=[3,0];c['points_by_type']=[{'field_goal':3},{}]
    before=deepcopy((c,s));out=transfer(c,s)
    assert out['status']==expected and out['state']['scores']==[3,0]
    assert out['credits'][0]['official_targets']is None and out['credits'][0]['official_carries']==1
    if expected.startswith('UNKNOWN'):
        detail=out['unknown_detail']
        assert detail['wait_lower_bound_seconds']==30 and detail['successor_observed']is False
        assert detail['unobserved_followup_seconds']==remaining-30
        assert detail['action_marks_credited_once']is True and out['state']['remaining']==remaining
    assert (c,s)==before

@pytest.mark.parametrize('wait,status',[
    ({'kind':'MISSING_CENSOR_CLASS','seconds':30},'UNKNOWN_WAIT_OBSERVATION_KIND'),
    ({'seconds':30},'UNKNOWN_WAIT_OBSERVATION_KIND'),(None,'UNKNOWN_WAIT_OBSERVATION_KIND'),
    ({'kind':'RIGHT_CENSORED'},'UNKNOWN_NEXT_ACTION_WAIT'),
    ({'kind':'EXACT_NEXT_ACTION','seconds':None},'UNKNOWN_NEXT_ACTION_WAIT'),
])
def test_unrecognized_or_missing_wait_never_becomes_an_exact_observation(wait,status):
    c,s=fixture();c['wait']=wait
    assert transfer(c,s)==dict(status=status,state=s)

def test_source_failure_reports_barriers_without_dropping_candidate():
    c,s=fixture();c.update(cycle_id='native:one',state_certified=False,barriers=['reversed_replay_unresolved'])
    out=transfer(c,s)
    assert out['status']=='UNKNOWN_SOURCE_STATE' and out['state']==s
    assert out['unknown_detail']['source_barriers']==c['barriers'] and 'credits'not in out

def test_unknown_censor_detail_survives_rollout_without_success_only_totals():
    c,s=fixture(wait=30,kind='RIGHT_CENSORED',phase='kickoff')
    c.update(cycle_id='censored',prior_bins=['MISSING','MISSING'])
    c['start'].update(half=1,remaining=30,score_sign=0)
    library=dict(version=VERSION,cycles=[c],threats=[],boundaries=dict(own=[.3,.7],opponent=[.3,.7]))
    openings=[dict(opening_id='one',certified=True,first_half=c['start'],second_half=c['start'])]
    contexts=[dict(own_pass_share=None,opponent_pass_share=None)]*2
    result=rollout(library,openings,contexts,[.5,.5],'control',1,lambda:0)
    assert result['status']=='UNKNOWN_CENSORED_SUCCESSOR' and result['full_law_known']is False
    assert result['team_stats'][0]['official_carries']==1
    assert len(result['trace'])==1 and result['trace'][0]['unknown_detail']['unobserved_followup_seconds']==1770

def test_native_transition_proof_and_unknown_channels_survive_compilation():
    from backend.app.tests.product.test_game_state_reconstruction_v3 import single_fumble_rows
    from backend.app.tests.product.test_game_state_reconstruction import build
    from backend.app.product_services.game_state_reconstruction import build_original_drive_blocks
    from backend.app.product_services.event_boundary_progression import compile_cycles
    f,nxt=single_fumble_rows();f['rushing_yards']=None
    reconstruction=build(f,nxt)
    contexts=[dict(game_id=f['game_id'],team=team,season=2023,own_pass_share=.5,opponent_pass_share=.5)for team in ('NYJ','BUF')]
    library=compile_cycles(reconstruction,build_original_drive_blocks(reconstruction),contexts)
    c=library['cycles'][0]
    assert c['state_certified'] and c['source_transition_proofs'][0]['recovery_native_id']=='00-0030001'
    assert c['production'][1]['rushing_yards']is None and c['production'][1]['official_carries']==1
    assert len(library['cycles'])==2 and not library['cycles'][1]['state_certified']
