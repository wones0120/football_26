from copy import deepcopy

import pytest

from backend.app.product_services.analyst_personal_context import evaluate, validate_current
from backend.app.tests.product.test_analyst_preparation import inputs
from backend.app.product_services.analyst_packets import packet_digest, load_packet
from backend.app.product_services.analyst_preparation import prepare_handoff, bind_handoff
from backend.app.tests.product.test_belief_impacts import _ImpactEngine, _TestImpactService

NOW='2099-09-01T14:00:00Z'
SCOPE=dict(season=2099,week=1,slate='SYNTHETIC',contest_format='classic',objective='gpp')


def belief():
    return dict(belief_id='belief',belief_version_id='version1',belief_version=1,status='active',source='user_hypothesis',thought_text='My exact hypothesis.',
        **SCOPE,expires_at='2099-09-02T14:00:00Z',decision='approved',decision_id='decision1',preview_id='preview1',
        decided_at='2099-09-01T13:59:00Z',approval_season=2099,approval_week=1,approval_slate='SYNTHETIC',approval_contest_format='classic',approval_objective='gpp',
        modifier_json=dict(modifier_type='analyst_context_review',team='BUF',conditional_mechanism='If protection fails, efficiency may fall; adaptation may offset it.'))


def test_approved_current_scope_review_preserves_packet_and_freezes_lineage(tmp_path):
    p,rows,request,result=inputs(); b=belief(); before=deepcopy((p,rows,b))
    handoff=prepare_handoff(request=request,result=result,rows=rows,checked_at=NOW,packets={packet_digest(p):p},directory=tmp_path,personal_context_inputs=[b])
    context=handoff['personal_context']; item=context['considered'][0]
    assert item['belief_version_id']=='version1' and item['decision_id']=='decision1'
    assert item['thought_text']==b['thought_text'] and item['resolved_scope']['team']=='BUF'
    assert item['related_scenario_ids'] and item['applied_scenario_ids']==[]
    assert item['evidence_assessment']=='unverified_user_hypothesis'
    assert not context['affected_construction'] and not context['changed_selected_rosters']
    checked=load_packet(handoff['checked_packet_sha256'],directory=tmp_path)
    assert checked['baseline_facts']==p['baseline_facts']
    payload=dict(**SCOPE,params={})
    bind_handoff(payload,{'analyst_handoff':handoff})
    assert payload['params']['analyst_handoff_applied']['personal_context']==context
    assert (p,rows,b)==before


@pytest.mark.parametrize('changes,reason',[
    ({'decision':None},'no_current_version_context_approval'),
    ({'expires_at':NOW},'expired'),({'week':2},'wrong_week'),({'slate':'OTHER'},'wrong_slate'),
    ({'status':'inactive'},'inactive'),({'approval_week':2},'approval_wrong_week'),
    ({'contest_format':'showdown'},'wrong_contest_format'),({'decided_at':'2099-09-02T00:00:00Z'},'future_approval'),
    ({'is_retrospective':True},'retrospective_not_forward_evidence'),
    ({'metadata_json':{'resolved_team':'PHI'}},'wrong_resolved_team'),
    ({'metadata_json':{'canonical_game_id':'not-in-slate'}},'wrong_canonical_game')])
def test_draft_expired_wrong_scope_and_future_never_enter_analyst_input(changes,reason):
    p,_,_,result=inputs(); b={**belief(),**changes}
    report=evaluate([b],scope=SCOPE,games=result['source_manifest']['games'],checked_at=NOW,packet=p)
    assert report['considered']==[] and reason in report['rejected'][0]['reasons']


def test_revision_revocation_expiry_after_prepare_require_reprepare():
    p,_,_,result=inputs(); b=belief(); report=evaluate([b],scope=SCOPE,games=result['source_manifest']['games'],checked_at=NOW,packet=p)
    validate_current(report,[b],checked_at=NOW)
    for changed in ({**b,'belief_version_id':'version2'}, {**b,'decision':'rejected'}, {**b,'expires_at':NOW}):
        with pytest.raises(ValueError,match='changed or expired'):validate_current(report,[changed],checked_at=NOW)


def test_context_preview_is_idempotent_version_bound_and_approval_reused():
    b={**belief(),'source':'user_hypothesis'}
    class Beliefs:
        def get_current(self,_):return b
    service=_TestImpactService(engine=_ImpactEngine(),belief_service=Beliefs(),predictions_service=object(),ownership_service=object(),simulation_service=object())
    payload=dict(**SCOPE,usage='analyst_context',target_team='BUF',conditional_mechanism='If protection fails, efficiency could fall; adaptation could offset it.')
    preview=service.create_preview('belief',payload)
    assert preview['adjustment_pct']==0 and preview['modifier']['numerical_effect'] is None
    assert preview['target_player_id']=='team:BUF'
    assert service.create_preview('belief',payload)['preview_id']==preview['preview_id']
    approved=service.decide(preview['preview_id'],'approved','Explicit qualitative test authorization')
    assert approved['approved_modifier']['construction_effect']=='none'
    assert service.create_preview('belief',payload)['status']=='approved'
    b['belief_version_id']='version2'
    assert service.create_preview('belief',payload)['preview_id']!=preview['preview_id']
    with pytest.raises(ValueError,match='outside belief'):service.create_preview('belief',{**payload,'slate':'OTHER'})


def test_context_preview_api_retains_typed_usage_and_rejects_scope_override():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.api.product_routes import router
    from backend.app.product_dependencies import get_belief_impact_service
    b=belief()
    class Beliefs:
        def get_current(self,_):return b
    service=_TestImpactService(engine=_ImpactEngine(),belief_service=Beliefs(),predictions_service=object(),ownership_service=object(),simulation_service=object())
    app=FastAPI();app.include_router(router);app.dependency_overrides[get_belief_impact_service]=lambda:service
    client=TestClient(app)
    payload=dict(**SCOPE,usage='analyst_context',target_team='BUF',conditional_mechanism='Conditional concern, not a forecast.')
    first=client.post('/api/digital-twin/beliefs/belief/impact-previews',json=payload)
    assert first.status_code==200,first.text
    assert first.json()['modifier']['modifier_type']=='analyst_context_review'
    again=client.post('/api/digital-twin/beliefs/belief/impact-previews',json={**payload,'slate':'synthetic'})
    assert first.json()['preview_id']==again.json()['preview_id']
    wrong=client.post('/api/digital-twin/beliefs/belief/impact-previews',json={**payload,'slate':'OTHER'})
    assert wrong.status_code==422 and 'outside belief slate' in wrong.json()['detail']
