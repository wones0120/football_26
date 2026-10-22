from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

import pandas as pd
import pytest

from backend.app.product_services.factual_designation import (
    FINAL_REPORT, DRESSING_REPORT, NO_DESIGNATION, effective_designation, resolve_designation,
)
from backend.app.product_services.final_injury_report import parse_final_report
from backend.app.product_services.showdown_player_context import compose_player_contexts, attach_context_fields
from backend.app.product_services.canonical_projection_inputs import apply_player_availability_overrides, _questionable_snapshot_overrides
from backend.app.tests.product.test_player_pool_safety import _row, _evaluate

NOW=datetime(2026,10,19,15,tzinfo=UTC)
PID='6031d562-62b5-4ac6-a6a7-ea36ce773116'
URI='https://www.commanders.com/news/final-report'
KICK='2026-10-20T00:15:00+00:00'


def fact(value='Q',**kwargs):
    return dict(player_id=PID,team='WAS',position='WR',kind='game_status',status=value,
        source='draftkings_salary_status',source_ids=['native-id'],observed_at=(NOW-timedelta(days=3)).isoformat(),
        received_at=NOW.isoformat(),**kwargs)


def final(value=NO_DESIGNATION):
    return {**fact(value),'source':'nfl_official_final_report','source_uri':URI,'source_ids':['final-capture'],
        'report_contract':FINAL_REPORT,'report_phase':'final','scope_verified':True,
        'published_at':'2026-10-17T17:04:41+00:00','kickoff_at':KICK,
        'observed_at':NOW.isoformat(),'received_at':NOW.isoformat()}


def resolve(facts):
    return resolve_designation(facts,cutoff=NOW,player_id=PID,team='WAS',position='WR')


def test_final_no_designation_supersedes_old_native_q_preserves_raw_and_publication():
    old={**fact(),'observed_at':(NOW-timedelta(hours=23)).isoformat()}
    # Actual salary source can be older than live-fact window. Keep it in raw
    # lineage; use its original event rather than today's import receipt.
    old=fact();r=resolve([old,final()])
    assert r['status']=='resolved' and r['effective_designation']==NO_DESIGNATION
    assert r['chosen_fact']['published_at']=='2026-10-17T17:04:41+00:00'
    assert old['status']=='Q'


@pytest.mark.parametrize('change',[
    {'player_id':'wrong'}, {'team':'SF'}, {'position':'TE'}, {'scope_verified':False},
    {'observed_at':(NOW+timedelta(minutes=1)).isoformat()},
    {'received_at':(NOW+timedelta(minutes=1)).isoformat()},
    {'published_at':(NOW+timedelta(minutes=1)).isoformat()},
])
def test_invalid_scope_future_or_unverified_blank_cannot_clear_q(change):
    q={**fact(),'observed_at':(NOW-timedelta(hours=1)).isoformat()}
    assert resolve([q,{**final(),**change}])['effective_designation']=='QUESTIONABLE'


def test_later_out_wins_and_late_q_conflict_is_unknown():
    assert resolve([final(),{**fact('OUT'),'observed_at':NOW.isoformat()}])['effective_designation']=='OUT'
    r=resolve([final(),{**fact(),'observed_at':NOW.isoformat()}])
    assert r['status']=='conflict' and r['effective_designation'] is None


@pytest.mark.parametrize('initial',[final(),{**fact(),'observed_at':(NOW-timedelta(hours=1)).isoformat()}])
def test_verified_game_dressing_resolves_final_or_questionable_without_roster_shortcut(initial):
    active={**fact('ACTIVE'),'observed_at':NOW.isoformat(),'game_active':True,
        'source':'nfl_official','source_uri':'https://www.nfl.com/news/official-inactives',
        'report_contract':DRESSING_REPORT,'scope_verified':True,'season':2026,'week':6,'kickoff_at':KICK}
    assert resolve([initial,active])['effective_designation']=='ACTIVE'
    assert resolve([initial,{**active,'kind':'roster_status'}])['effective_designation']!='ACTIVE'
    assert resolve([initial,{**active,'received_at':(NOW+timedelta(seconds=1)).isoformat()}])['effective_designation']!='ACTIVE'
    assert resolve([initial,{**active,'source_ids':[]}])['effective_designation']!='ACTIVE'
    assert resolve([initial,{**active,'source_uri':'https://example.test/not-official'}])['effective_designation']!='ACTIVE'
    for changed in ({'week':5},{'kickoff_at':'2026-10-21T00:15:00Z'}):
        r=resolve_designation([initial,{**active,**changed}],cutoff=NOW,player_id=PID,team='WAS',position='WR',
            season=2026,week=6,kickoff_at=KICK)
        assert r['effective_designation']!='ACTIVE'


@pytest.mark.parametrize('value',['NFI','SUSP','RES','RESERVE','EXE'])
def test_later_adverse_designations_remain_unavailable(value):
    c=compose_player_contexts([dict(player_id=PID,team='WAS',position='WR')],
        [final(),{**fact(value),'observed_at':NOW.isoformat()}],cutoff=NOW,max_age_hours=24)[0]
    assert c['evidence_json']['availability_state']=='UNAVAILABLE'


def test_roster_act_and_generic_blank_cannot_clear_questionable():
    q={**fact(),'observed_at':(NOW-timedelta(hours=1)).isoformat()}
    assert resolve([q,{**fact('ACT'),'kind':'roster_status','observed_at':NOW.isoformat()},
        {**fact(''),'observed_at':NOW.isoformat()}])['effective_designation']=='QUESTIONABLE'
    assert effective_designation(dict(player_status='Q',availability_status='ACT'))=='QUESTIONABLE'


def parsed_context():
    salary=dict(player_id=PID,team='WAS',position='WR')
    role={**fact(None),'kind':'role','role':'expected_starter','observed_at':NOW.isoformat()}
    return compose_player_contexts([salary],[fact(),final(),role],cutoff=NOW,max_age_hours=24)[0]


def test_same_fact_composer_pool_and_both_assume_q_paths():
    c=parsed_context();assert c['injury_status']==NO_DESIGNATION
    e=c['evidence_json'];assert e['availability_state']=='AVAILABLE'
    row=_row(PID,player_team='WAS',opponent_team='SF',player_status='Q',projection=10.496)
    frame=attach_context_fields(pd.DataFrame([row]),[c])
    # Keep test helper's fixed historic as-of; factual resolution is independent
    # of its unrelated context-age warning. The Q preference must be absent.
    result=_evaluate(frame.to_dict('records'),exclude_questionable=True)
    assert 'user_excluded_questionable' not in result.audit_rows[0]['exclusion_reasons']
    assert frame.iloc[0]['projection']==10.496 and frame.iloc[0]['player_status']=='Q'
    target=pd.DataFrame([dict(player_id=PID,player_status='Q',player_display_name='Terry McLaurin')])
    context=pd.DataFrame([c])
    _,audit=apply_player_availability_overrides(target,context,[],assume_questionable_out=True)
    assert audit==[]
    injuries=pd.DataFrame([dict(player_id=PID,injury_status='Q')])
    assert _questionable_snapshot_overrides(target,context,injuries)==[]


def html(final_day='Limited',status=''):
    meta=dict(**{'@type':'NewsArticle'},datePublished='2026-10-17T17:04:41Z',url=URI,headline='Game status | Week 6',
        articleBody='Week 6 against the San Francisco 49ers, full injury report.')
    return ('<script type="application/ld+json">'+json.dumps(meta)+'</script><table><tr>'+
        ''.join('<th>'+h+'</th>' for h in ['Player','Injury','Thursday','Friday','Saturday','Status'])+
        '</tr><tr>'+''.join('<td>'+v+'</td>' for v in ['WR Terry McLaurin','Hamstring','Limited','DNP',final_day,status])+'</tr></table>')


def parse(body,**kwargs):
    return parse_final_report(body,source_uri=URI,season=2026,week=6,team='WAS',opponent='SF',
        kickoff_at=KICK,observed_at=NOW,**kwargs)


def test_parser_final_blank_is_typed_but_incomplete_generic_report_abstains():
    assert parse(html())['rows'][0]['game_status']==NO_DESIGNATION
    with pytest.raises(ValueError,match='incomplete'):parse(html(final_day=''))
    with pytest.raises(ValueError,match='week and opponent'):parse(html().replace('Week 6','Week 5'))
    with pytest.raises(ValueError,match='publication'):parse(html().replace('2026-10-17','2026-10-21'))
    with pytest.raises(ValueError,match='explicit authored'):
        parse(html().replace('Game status | Week 6','Practice update | Week 6'))


def test_real_reduced_washington_final_report_retains_exact_scope_and_marker():
    body=(Path(__file__).parent.parent/'fixtures/official_was_final_2026w6.html').read_text()
    r=parse_final_report(body,source_uri='https://www.commanders.com/news/game-status-commanders-49ers-week-6',
        season=2026,week=6,team='WAS',opponent='SF',kickoff_at=KICK,observed_at=NOW)
    assert len(r['rows'])==22 and r['final_publication_marker'].lower()=='game status'
    assert next(p for p in r['rows'] if p['player_name']=='Terry McLaurin')['game_status']==NO_DESIGNATION
    assert r['published_at'].startswith('2026-10-17T17:04:41')


def test_final_report_scope_and_retrieval_do_not_renew_publication():
    f=final();f.update(season=2026,week=6)
    assert resolve_designation([f],cutoff=NOW,player_id=PID,team='WAS',position='WR',season=2026,week=5)['status']=='unknown'
    later={**f,'observed_at':(NOW+timedelta(hours=1)).isoformat(),'received_at':(NOW+timedelta(hours=1)).isoformat()}
    r=resolve_designation([f,later],cutoff=NOW+timedelta(hours=1),player_id=PID,team='WAS',position='WR')
    assert all(x['published_at']==f['published_at'] for x in r['source_facts'])


def grouped_report():
    uri='https://www.patriots.com/news/week-7-injury-report-patriots-at-bears'
    meta={'@type':'NewsArticle','datePublished':'2026-10-21T20:00:00Z','url':uri,
          'headline':'Week 7 Injury Report: Patriots at Bears',
          'articleBody':'The New England Patriots and Chicago Bears announce the following player injuries and game statuses ahead of their Week 7 game.'}
    return uri, '<script type="application/ld+json">'+json.dumps(meta)+'''</script>
      <p>WEDNESDAY, OCTOBER 21, 2026</p><h3>NEW ENGLAND PATRIOTS</h3>
      <p>OUT OL Ben Brown - Knee (DNP)</p><p>DOUBTFUL No Players Listed.</p>
      <p>QUESTIONABLE T Morgan Moses - Foot (LP)</p>
      <p>NO GAME STATUS GIVEN: WR A.J. Brown - Ankle (FP), QB Drake Maye - Shoulder (FP)</p>
      <h3>CHICAGO BEARS</h3><p>OUT RB Kyle Monangai - Thumb (DNP)</p>
      <p>TUESDAY, OCTOBER 20, 2026</p><h3>NEW ENGLAND PATRIOTS</h3>
      <p>QUESTIONABLE WR A.J. Brown - Ankle (LP)</p>'''


def test_grouped_thursday_final_status_has_exact_team_date_and_explicit_clearance():
    uri,body=grouped_report()
    parsed=parse_final_report(body,source_uri=uri,season=2026,week=7,team='NE',opponent='CHI',
        kickoff_at='2026-10-23T00:15:00Z',observed_at='2026-10-22T01:00:00Z')
    brown=next(r for r in parsed['rows'] if r['player_name']=='A.J. Brown')
    assert brown['position']=='WR' and brown['game_status']==NO_DESIGNATION
    assert brown['practice_status']=='FULL'
    assert all(r['team']=='NE' for r in parsed['rows'])
    assert not any(r['player_name']=='Kyle Monangai' for r in parsed['rows'])


@pytest.mark.parametrize('change',[
    ('WEDNESDAY, OCTOBER 21, 2026','TUESDAY, OCTOBER 20, 2026'),
    ('NO GAME STATUS GIVEN:','PRACTICE PARTICIPATION:'),
    ('WR A.J. Brown - Ankle (FP)','WR A.J. Brown - Ankle'),
    ('<p>DOUBTFUL No Players Listed.</p>',''),
])
def test_incomplete_or_earlier_grouped_report_cannot_clear_native_q(change):
    uri,body=grouped_report()
    with pytest.raises(ValueError):
        parse_final_report(body.replace(*change),source_uri=uri,season=2026,week=7,team='NE',opponent='CHI',
            kickoff_at='2026-10-23T00:15:00Z',observed_at='2026-10-22T01:00:00Z')


def test_upload_check_uses_final_designation_without_native_q_override():
    from backend.app.tests.product.test_saved_upload_readiness import fixture, evaluate, NOW as at, PID as pid
    job,e=fixture();p=e['players'][pid]
    f={**final(),'player_id':pid,'team':'SEA','observed_at':at.isoformat(),'received_at':at.isoformat(),
        'published_at':(at-timedelta(days=2)).isoformat(),'kickoff_at':(at+timedelta(hours=9)).isoformat()}
    p['designation_resolution']=resolve_designation([f],cutoff=at,player_id=pid,team='SEA',position='WR')
    p['availability_status']=NO_DESIGNATION;p['official_practice']='Limited';job.params['questionable_eligible_player_ids']=[]
    assert evaluate(job,e)['upload_ready']
    p['designation_resolution']['status']='conflict'
    assert not evaluate(job,e)['upload_ready']


def test_readiness_exposes_conflicting_designation_even_if_state_was_wrongly_available():
    from backend.app.product_services.showdown_player_context import assess_availability
    c=parsed_context();row={**c['evidence_json'],'position':'WR'}
    row['designation_resolution']['status']='conflict'
    state,reasons=assess_availability(row,cutoff=NOW,evaluated_at=NOW,max_age_hours=24)
    assert state=='UNKNOWN' and 'player_status_conflict' in reasons


@pytest.mark.parametrize('resolved',[True,False])
def test_collector_persists_alias_or_queues_unresolved_before_context(monkeypatch,resolved):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from backend.app.product_services import final_injury_report as module
    from backend.app.product_services import slate_preparation, pregame_context
    from backend.app.services import source_capture
    class FixtureClock(datetime):
        @classmethod
        def now(cls,tz=None):return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)
    monkeypatch.setattr(module,'datetime',FixtureClock)
    monkeypatch.setattr(slate_preparation,'datetime',FixtureClock)
    engine=MagicMock();connection=engine.connect.return_value.__enter__.return_value
    salary=dict(player_id=PID,team='WAS',position='WR',player_name='Historical display',full_name='Historical display')
    alias=dict(player_master_id=PID,source_system='nfl_official',
        source_key=URI+'#WR-terry mclaurin',alias_name='Historical display')
    connection.execute.side_effect=[SimpleNamespace(mappings=lambda:[salary]),
        SimpleNamespace(mappings=lambda:[alias] if resolved else [])]
    write=engine.begin.return_value.__enter__.return_value
    write.execute.return_value.scalar_one_or_none.return_value=PID
    monkeypatch.setattr(module,'Session',MagicMock())
    monkeypatch.setattr(slate_preparation,'slate_games',lambda *a:[dict(home_team='SF',away_team='WAS',kickoff_at=KICK)])
    response=SimpleNamespace(text=html(),headers={},raise_for_status=lambda:None)
    monkeypatch.setattr(module.httpx,'get',lambda *a,**k:response)
    capture=MagicMock();capture.capture_file.return_value.snapshot.snapshot_id='capture'
    monkeypatch.setattr(source_capture,'SourceCaptureService',lambda *a:capture)
    context=MagicMock();context.create_run.return_value={'context_run_id':'context'}
    monkeypatch.setattr(pregame_context,'PregameContextService',lambda **k:context)
    if resolved:
        result=module.capture_final_report(engine,season=2026,week=6,slate='MONDAY_NIGHT',team='WAS',source_uri=URI)
        assert result['players']==1
        assert context.create_run.call_args.args[0]['players'][0]['player_id']==PID
        assert 'INSERT INTO public.player_alias' in str(write.execute.call_args_list[0].args[0])
    else:
        with pytest.raises(ValueError,match='identities require review'):
            module.capture_final_report(engine,season=2026,week=6,slate='MONDAY_NIGHT',team='WAS',source_uri=URI)
        context.create_run.assert_not_called()
        assert 'target.identity_quarantine' in str(write.execute.call_args.args[0])
    assert capture.capture_file.called
