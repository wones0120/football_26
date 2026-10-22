from copy import deepcopy
import pytest
from backend.app.product_services.market_environment_features import build_market_environment_features

GAME=dict(game_id='2026_06_WAS_SF',season=2026,week=6,home_team='SF',away_team='WAS',kickoff_at='2026-10-20T00:15:00Z')
CUTOFF='2026-10-19T23:00:00Z'


def quote(**kwargs):
    return dict(GAME,game_total=52.5,home_spread=-7.5,source='provider',source_game_id='native',
        observed_at='2026-10-19T22:00:00Z',ingested_at='2026-10-19T22:01:00Z',
        market_snapshot_id='quote1',source_snapshot_id='source1',**kwargs)


def run(observations):
    return build_market_environment_features([GAME],observations,cutoff=CUTOFF)


def test_conventional_spread_implied_points_and_no_fake_opening():
    result=run([quote()]);teams={r['team']:r for r in result['games']}
    assert teams['SF']['metrics']['G19-M04']['value']==-7.5
    assert teams['WAS']['metrics']['G19-M04']['value']==7.5
    assert teams['SF']['metrics']['G19-M07']['value']==30
    assert teams['WAS']['metrics']['G19-M07']['value']==22.5
    assert sum(t['metrics']['G19-M07']['value'] for t in teams.values())==52.5
    assert teams['SF']['metrics']['G19-M02']['value'] is None


def test_latest_valid_quote_and_rejected_future_not_renewing_clock():
    a=quote();b=deepcopy(a);b.update(game_total=51.5,observed_at='2026-10-19T22:50:00Z',ingested_at='2026-10-19T22:51:00Z',market_snapshot_id='new')
    future=deepcopy(b);future.update(game_total=60,ingested_at='2026-10-19T23:01:00Z')
    result=run([future,a,b])
    assert result['games'][0]['metrics']['G19-M01']['value']==51.5
    assert len(result['provenance']['rejected'])==1


def test_same_latest_conflicting_values_abstain_not_uuid_pick():
    a=quote();b=deepcopy(a);b['game_total']=53.5;b['market_snapshot_id']='z'
    result=run([a,b]);assert result['games'][0]['metrics']['G19-M01']['value'] is None
    assert result['games'][0]['metrics']['G19-M01']['reason']=='conflicting_latest_quotes'


def test_equivalent_envelope_ids_clocks_do_not_change_measured_semantics():
    a=quote();b=deepcopy(a);b.update(market_snapshot_id='second',source_snapshot_id='secondsource',ingested_at='2026-10-19T22:02:00Z')
    assert run([a])['semantic_sha256']==run([b])['semantic_sha256']
    assert run([a,b])['semantic_sha256']==run([b,a])['semantic_sha256']


@pytest.mark.parametrize('field,value',[
    ('observed_at','2026-10-20T00:15:00Z'),('ingested_at','2026-10-19T21:59:00Z'),
    ('provider_updated_at','2026-10-19T22:01:00Z'),('week',7),('home_team','DAL'),
    ('home_spread',True),('source_snapshot_id',None),('game_total',float('nan')),
    ('observed_at','2026-10-17T22:00:00Z'),('observed_at','2026-10-19T22:00:00')])
def test_invalid_scoped_clocks_identity_and_numbers_abstain(field,value):
    a=quote();a[field]=value
    assert run([a])['games'][0]['metrics']['G19-M01']['value'] is None


def test_two_source_teams_not_inferred_from_player_pool_and_duplicate_game_rejects():
    assert len(run([quote()])['games'])==2
    with pytest.raises(ValueError,match='Unique canonical'):
        build_market_environment_features([GAME,GAME],[],cutoff=CUTOFF)


def test_same_book_native_open_and_moneyline_have_named_probability_semantics():
    a=quote();a.update(detail_source_snapshot_id='source1',bookmaker='DraftKings',opening_total=50.5,
        opening_home_spread=-5.5,home_moneyline=-395.,away_moneyline=310.)
    result=run([a]);teams={r['team']:r for r in result['games']}
    assert teams['SF']['metrics']['G19-M03']['value']==2
    assert teams['SF']['metrics']['G19-M06']['value']==-2
    assert teams['WAS']['metrics']['G19-M06']['value']==2
    assert teams['SF']['metrics']['G19-M09']['value']==pytest.approx(395/495)
    assert sum(t['moneyline_pair']['no_vig_proportional_probability'] for t in teams.values())==pytest.approx(1)
    assert sum(t['metrics']['G19-M09']['value'] for t in teams.values())>1
    a['detail_source_snapshot_id']='other'
    assert run([a])['games'][0]['metrics']['G19-M02']['value'] is None


def test_real_indexed_source_extraction_preserves_opening_not_earliest_capture(tmp_path):
    import csv,json
    from datetime import UTC,datetime
    from backend.app.tests.product.test_espn_markets import payload,GAME as E_GAME,NOW
    from backend.app.product_services.espn_markets import scoreboard_url
    from backend.app.tests.test_source_capture import _session
    from backend.app.services.source_capture import SourceCaptureService,SnapshotIntegrityError
    from backend.app.product_services.market_environment_features import extract_espn_market_details
    p=payload();q=p['events'][0]['competitions'][0]['odds'][0]
    q['pointSpread']['away']['open']={'line':'+3'}
    q['total']['over']['open']={'line':'o44.5'};q['total']['under']['open']={'line':'u44.5'}
    q['moneyline']={'home':{'close':{'odds':'-120'}},'away':{'close':{'odds':'+110'}}}
    path=tmp_path/'native.csv'
    with path.open('w') as f:
        w=csv.DictWriter(f,fieldnames=['response_json','capture_observed_at']);w.writeheader();w.writerow(dict(response_json=json.dumps(p),capture_observed_at=NOW.isoformat()))
    session=_session()
    try:
        service=SourceCaptureService(session,snapshot_root=tmp_path/'snapshots',clock=lambda:NOW)
        snapshot=service.capture_file(path,source_system='espn',dataset='schedule_market_snapshot',season=2026,week=5,slate='test',source_uri=scoreboard_url(2026,5),source_license='fixture').snapshot
        result=extract_espn_market_details(snapshot,[E_GAME],cutoff=NOW)
        detail=result['details'][E_GAME['game_id']]
        assert detail['opening_total']==44.5 and detail['game_total']==46.5
        assert detail['opening_home_spread']==-3
        assert detail['home_moneyline']==-120
        assert result['opening_publication_at'] is None
        snapshot.content_sha256='0'*64
        with pytest.raises(SnapshotIntegrityError):extract_espn_market_details(snapshot,[E_GAME],cutoff=NOW)
    finally:session.close()
