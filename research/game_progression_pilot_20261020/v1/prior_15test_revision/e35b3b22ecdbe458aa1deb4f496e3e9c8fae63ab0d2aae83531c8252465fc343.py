from copy import deepcopy
import numpy as np
import pytest
from backend.app.product_services.game_progression_policy import fit_prior_bins,compile_policy,select_block


def context():return dict(game_id='2023_04_A_B',team='A',season=2023,own_pass_share=.6,opponent_pass_share=.5)
def block(i,sign=0):return dict(block_id=str(i),source_season=2023,context_key=['2023_04_A_B','A'],certified=True,start=dict(field100=75,phase='KICKOFF',half=1,half_seconds=1700,score_sign=sign))
def state():return dict(field100=75,phase='KICKOFF',half=1,half_seconds=1800,possession_side=0,scores=[0,0])


def test_train_terciles_once_per_unique_context_not_block_weight():
    rows=[dict(context(),game_id=f'2023_0{i}_A_B',own_pass_share=x)for i,x in enumerate([.1,.2,.8,.9],1)]
    actual=fit_prior_bins(rows)
    assert np.array_equal(actual['own'],np.quantile([.1,.2,.8,.9],[1/3,2/3],method='linear'))
    with pytest.raises(ValueError):fit_prior_bins(rows+[rows[0]])
    with pytest.raises(ValueError):fit_prior_bins([dict(context(),season=2026)])


def test_generated_score_feedback_selects_different_context_pool():
    p=compile_policy([block(i,0)for i in range(8)]+[block(i+10,1)for i in range(8)],[context()]);s=state()
    a=select_block(p,s,context(),arm='contextual',uniform=.1)
    s['scores']=[7,0];b=select_block(p,s,context(),arm='contextual',uniform=.1)
    assert a['selected']['start']['score_sign']==0 and b['selected']['start']['score_sign']==1
    assert a['fallback']==b['fallback']=='ALL_CONTEXT'


def test_exact_support_never_relaxes():
    p=compile_policy([block(1)],[context()]);s=state();s['field100']=74
    assert select_block(p,s,context(),arm='contextual',uniform=.5)['status']=='UNSUPPORTED_TRAJECTORY'
    s=state();s['phase']='PUNT'
    assert select_block(p,s,context(),arm='control',uniform=.5)['selected']is None


def test_uncertified_source_mass_stays_in_pool():
    b=block(1);b['certified']=False;p=compile_policy([b],[context()])
    result=select_block(p,state(),context(),arm='control',uniform=.5)
    assert result['status']=='UNKNOWN_UNCERTIFIED_SOURCE_BLOCK'and result['pool_size']==1


def test_unknown_support_and_context_mask_full_law():
    a=block(1);a['start']['half_seconds']=None;b=block(2);b['start']['field100']=None
    p=compile_policy([a,b],[context()]);r=select_block(p,state(),context(),arm='control',uniform=.5)
    assert not r['full_law_known']and len(r['potential_support_threats'])==2


def test_missing_prior_is_distinct_and_common_uniform_replays():
    missing=dict(context(),own_pass_share=None,opponent_pass_share=None)
    p=compile_policy([block(i)for i in range(8)],[missing]);before=deepcopy(p)
    a=select_block(p,state(),missing,arm='contextual',uniform=.25)
    b=select_block(p,state(),missing,arm='contextual',uniform=.25)
    assert a==b and a['prior_bins']==['MISSING','MISSING']and a['fallback']=='ALL_CONTEXT'and p==before
