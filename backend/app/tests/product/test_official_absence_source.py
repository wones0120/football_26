from copy import deepcopy
import pytest
from backend.app.product_services.official_absence_source import parse_absence_layout,resolve_absence_roster,absence_layout
from backend.app.product_services.weekly_effectiveness_catalog_features import VERSION

SHA='a'*64;P='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';Q='bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';NOW='2026-10-20T09:00:00Z'
G=dict(game_id='2025_03_DEN_LAC',game_type='REG',season=2025,week=3,game_date='2025-09-21',away_team='DEN',home_team='LAC')


def layout():
    def cols(a,b):return a.ljust(96)+b
    return '\n'.join(['National Football League Game Summary','Date: Sunday, 9/21/2025',
        cols('VISITOR: Denver Broncos 0','HOME: Los Angeles Chargers 0'),
        cols('Did Not Play'.center(96),'Did Not Play'.center(96)),cols('QB 8 J.Stidham','QB 5 T.Lance'),
        cols('Not Active'.center(96),'Not Active'.center(96)),cols('TE 1 E.Engram, 3QB 4 S.Ehlinger, T','TE 89 W.Dissly'),
        cols('73 F.Crum',''), 'Field Goals (made ( ) & missed)'])


def parsed():return parse_absence_layout(layout(),G,source_sha256=SHA)


def roster():
    return [dict(season=2025,week=3,game_type='REG',team='DEN',position='TE',gsis_id='00-0031234',source_id=1,
        imported_at='2026-10-19T00:00:00Z',ingest_run_id='run',player_name='Evan Engram',raw_row_json=dict(jersey_number=1,position='TE',gsis_id='00-0031234'))]


def weekly():return dict(version=VERSION,pregame_serving_eligible=False,provenance=dict(actual_derived_at='2026-10-19T00:00:00Z'),rows=[dict(source_player_id='00-0031234',player_master_id=P)])


def run(rows=None,w=None):return resolve_absence_roster(parsed(),rows or roster(),w or weekly(),cutoff=NOW)


def test_wrap_and_distinct_official_status_domains_without_weather_requirement():
    p=parsed();assert len(p['rows'])==6
    assert sum(r['ordinary_absence_anchor'] for r in p['rows'])==3
    emergency=next(r for r in p['rows'] if r['source_position']=='3QB')
    assert emergency['source_status']=='EMERGENCY_THIRD_QB_EXCEPTION' and not emergency['ordinary_absence_anchor']
    assert next(r for r in p['rows'] if r['source_jersey_number']==73)['source_abbreviated_name']=='F.Crum'
    assert sum(r['source_status']=='DID_NOT_PLAY' for r in p['rows'])==2


def test_native_tuple_unique_before_name_corroboration():
    x=run();r=next(r for r in x['rows'] if r['source_jersey_number']==1)
    assert r['player_master_id']==P and r['source_native_gsis_id']=='00-0031234'
    assert len(x['identity_review_requests'])==5


def test_ambiguous_native_tuple_not_resolved_by_one_matching_name():
    rows=roster();other=deepcopy(rows[0]);other.update(source_id=2,gsis_id='00-0039999',player_name='Different Person');other['raw_row_json']['gsis_id']='00-0039999';rows.append(other)
    r=next(r for r in run(rows)['rows'] if r['source_jersey_number']==1)
    assert r['player_master_id'] is None and len(r['native_candidate_gsis_ids'])==2


def test_unknown_jersey_candidate_masks_unique_proof():
    rows=roster();other=deepcopy(rows[0]);other.update(source_id=2,gsis_id='00-0039999');other['raw_row_json'].update(gsis_id='00-0039999',jersey_number=None);rows.append(other)
    r=next(r for r in run(rows)['rows'] if r['source_jersey_number']==1)
    assert r['player_master_id'] is None and r['uncertain_roster_source_ids']==[2]


@pytest.mark.parametrize('change',['name','canonical','rawnative','rawteam','rawperiod','future','wrongweek'])
def test_native_identity_and_clock_failures(change):
    rows=roster();w=weekly()
    if change=='name':rows[0]['player_name']='Different Person'
    if change=='canonical':w['rows'].append(dict(source_player_id='00-0031234',player_master_id=Q))
    if change=='rawnative':rows[0]['raw_row_json']['gsis_id']='00-0099999'
    if change=='rawteam':rows[0]['raw_row_json']['team']='SF'
    if change=='rawperiod':rows[0]['raw_row_json']['week']=4
    if change=='future':rows[0]['imported_at']='2026-10-21T00:00:00Z'
    if change=='wrongweek':rows[0]['week']=4
    if change in {'name','canonical'}:
        assert next(r for r in run(rows,w)['rows'] if r['source_jersey_number']==1)['player_master_id'] is None
    else:
        with pytest.raises(ValueError):run(rows,w)


@pytest.mark.parametrize('change',['date','teams','marker','boundary','fragment'])
def test_layout_scope_or_unparsed_fragment_rejects(change):
    s=layout()
    if change=='date':s=s.replace('9/21/2025','9/22/2025')
    if change=='teams':s=s.replace('Denver Broncos','Seattle Seahawks')
    if change=='marker':s=s.replace('Not Active','Unknown',1)
    if change=='boundary':s=s.replace('Field Goals','Other Section')
    if change=='fragment':s=s.replace('TE 1 E.Engram','not a roster entry')
    with pytest.raises(ValueError):parse_absence_layout(s,G,source_sha256=SHA)


def test_pdf_input_is_bounded_and_not_synthetic_text_pdf():
    with pytest.raises(ValueError):absence_layout(b'Not Active')
    with pytest.raises(ValueError):absence_layout(b'')


def test_source_position_family_only_corroborates_identity_not_alignment():
    p=parsed();p['rows']=[dict(p['rows'][0],team='LAC',source_position='DB',source_jersey_number=2,source_abbreviated_name='E.Molden')]
    r=roster();r[0].update(team='LAC',position='S',player_name='Elijah Molden');r[0]['raw_row_json'].update(position='S',jersey_number=2)
    x=resolve_absence_roster(p,r,weekly(),cutoff=NOW)
    assert x['rows'][0]['player_master_id']==P and x['rows'][0]['source_position']=='DB'


def test_queue_is_evidence_specific_append_only_not_current_alias_claim():
    from backend.app.product_services.official_absence_source import persist_absence_identity_incidents
    class Fake:
        def __init__(self):self.calls=[]
        def execute(self,sql,params):self.calls.append((str(sql),params))
    x=run();c=Fake();refs={'pdf_sha256':SHA,'roster_sha256':'b'*64,'weekly_sha256':'c'*64}
    a=persist_absence_identity_incidents(c,x,source_refs=refs)
    b=persist_absence_identity_incidents(Fake(),x,source_refs=refs)
    assert a==b and len(c.calls)==5
    assert all('DO NOTHING' in sql and 'UPDATE' not in sql for sql,_ in c.calls)
    assert all(not r['current_alias_missing_claim'] for r in a['records'])
    assert not a['aliases_mutated'] and not a['resolved_cases_reopened']


def test_roster_unknown_or_postseason_phase_cannot_prove_regular_identity():
    r=roster();r[0]['game_type']=None
    assert next(x for x in run(r)['rows'] if x['source_jersey_number']==1)['player_master_id'] is None
    r[0]['game_type']='POST'
    assert next(x for x in run(r)['rows'] if x['source_jersey_number']==1)['player_master_id'] is None


def test_primary_native_generic_DB_position_is_not_a_canonical_unknown():
    x=parse_absence_layout(layout().replace('TE 89 W.Dissly','DB 2 E.Molden'),G,source_sha256=SHA)
    assert any(r['source_position']=='DB' and r['source_jersey_number']==2 for r in x['rows'])
