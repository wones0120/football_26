"""Canonical pregame market features; neither historical closing-line hindsight
nor a market probability is substituted for missing source observations.
"""
from .evaluation_record import digest
from .factual_designation import clock as record_clock
from .market_snapshots import MarketSnapshot, canonical_team, utc_time
from math import isfinite

VERSION='canonical_market_environment_features_v1'
CURRENT_IDS=('G19-M01','G19-M04','G19-M07','G19-M08')


def extract_espn_market_details(snapshot,games,*,cutoff):
    """Verify actual indexed scoreboard bytes, then preserve native open/close.

    ESPN's pregame `close` means latest displayed quote, not a later final line.
    `open` is the same bookmaker's reported opening quote, known only by this
    capture; its original publication clock is not inferred.
    """
    import csv,json
    from pathlib import Path
    from .espn_markets import parse_scoreboard,scoreboard_url
    from backend.app.services.source_capture import verify_snapshot_artifact
    if snapshot.source_system!='espn' or snapshot.dataset!='schedule_market_snapshot':raise ValueError('Indexed ESPN market source required')
    if snapshot.source_uri!=scoreboard_url(snapshot.season,snapshot.week):raise ValueError('Canonical season/week scoreboard URI required')
    if snapshot.byte_count>4*1024*1024:raise ValueError('Bounded market source required')
    verify_snapshot_artifact(snapshot)
    # Indexed ORM timestamps are UTC (SQLite fixtures drop the tz marker).
    # Native/provider timestamps still use the strict timezone parser below.
    if not record_clock(snapshot.observed_at)<=record_clock(snapshot.captured_at)<=utc_time(cutoff):raise ValueError('Market source unavailable at cutoff')
    limit=csv.field_size_limit()
    try:
        csv.field_size_limit(4*1024*1024)
        with Path(snapshot.artifact_path).open() as f:rows=list(csv.DictReader(f))
    finally:csv.field_size_limit(limit)
    if len(rows)!=1:raise ValueError('One native scoreboard envelope required')
    raw=rows[0];captured=utc_time(raw['capture_observed_at'])
    if captured>record_clock(snapshot.observed_at):raise ValueError('Native envelope capture after indexed observation')
    payload=json.loads(raw['response_json'])
    parsed,rejected=parse_scoreboard(payload,schedule=games,season=snapshot.season,week=snapshot.week,captured_at=captured)
    details={}
    for market in parsed:
        event=next(e for e in payload['events'] if str(e['id'])==market.source_game_id)
        competition=next(c for c in event['competitions'] if abs((utc_time(c['date'])-market.kickoff_at).total_seconds())<=60
            and {x['homeAway']:canonical_team(x['team']['abbreviation']) for x in c['competitors']}=={'home':market.home_team,'away':market.away_team})
        quote=next(q for q in competition['odds'] if str(q.get('provider',{}).get('id'))=='100')
        item=dict(game_id=market.game_id,game_total=market.game_total,home_spread=market.home_spread,
            source_game_id=market.source_game_id,bookmaker='DraftKings',source_snapshot_id=str(snapshot.snapshot_id),
            native_capture_at=captured.isoformat(),opening_total=None,opening_home_spread=None,home_moneyline=None,away_moneyline=None)
        try:
            over=str(quote['total']['over']['open']['line']);under=str(quote['total']['under']['open']['line'])
            ot=float(over[1:])
            if over.startswith('o') and under.startswith('u') and ot==float(under[1:]) and 20<=ot<=80:item['opening_total']=ot
        except (KeyError,TypeError,ValueError):pass
        try:
            oh=float(quote['pointSpread']['home']['open']['line']);oa=float(quote['pointSpread']['away']['open']['line'])
            if isfinite(oh) and abs(oh)<=30 and oh==-oa:item['opening_home_spread']=oh
        except (KeyError,TypeError,ValueError):pass
        try:
            home=float(quote['moneyline']['home']['close']['odds']);away=float(quote['moneyline']['away']['close']['odds'])
            if all(isfinite(v) and abs(v)>=100 for v in (home,away)):
                item.update(home_moneyline=home,away_moneyline=away)
        except (KeyError,TypeError,ValueError):pass
        details[market.game_id]=item
    return dict(details=details,rejected=rejected,source_snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,
        quote_semantics='Native DraftKings open/latest displayed close in verified pregame scoreboard',opening_publication_at=None)


def _implied(odds):
    return -odds/(-odds+100) if odds<0 else 100/(odds+100)


def build_market_environment_features(games,observations,*,cutoff,max_age_hours=24):
    """Latest unambiguous canonical quote available before decision AND kickoff.

    Caller authenticates indexed source bytes/ingest status before supplying
    observations. This pure derivation additionally validates scope and clocks.
    An earliest retained quote is never relabeled the bookmaker's opening line.
    """
    cutoff=utc_time(cutoff)
    observations=list(observations)
    if type(max_age_hours) not in {int,float} or not 0<max_age_hours<=168:raise ValueError('Bounded quote age required')
    output=[];rejected=[];seen=set();provenance=[]
    for game in games:
        gid=str(game['game_id']);home=canonical_team(game['home_team']);away=canonical_team(game['away_team'])
        season=game['season'];week=game['week'];kickoff=utc_time(game['kickoff_at'])
        if not game.get('game_id') or gid in seen or home==away or type(season) is not int or type(week) is not int or not 2000<=season<=2200 or not 1<=week<=18:
            raise ValueError('Unique canonical REG game scope required')
        seen.add(gid);valid=[]
        for raw in observations:
            if str(raw.get('game_id'))!=gid:continue
            try:
                if not raw.get('source_snapshot_id') or not raw.get('market_snapshot_id') or not raw.get('source'):
                    raise ValueError('Indexed source observation identifiers required')
                if type(raw['season']) is not int or type(raw['week']) is not int or isinstance(raw['home_spread'],bool) or isinstance(raw['game_total'],bool):raise ValueError('Typed numerical market fields required')
                observed=utc_time(raw['observed_at']);received=utc_time(raw['ingested_at'])
                row=MarketSnapshot(season=raw['season'],week=raw['week'],game_id=str(raw['game_id']),
                    home_team=canonical_team(raw['home_team']),away_team=canonical_team(raw['away_team']),
                    kickoff_at=utc_time(raw['kickoff_at']),game_total=float(raw['game_total']),home_spread=float(raw['home_spread']),
                    source=raw['source'],source_game_id=raw.get('source_game_id'),observed_at=observed,ingested_at=received,
                    snapshot_id=raw['market_snapshot_id'])
                if (row.season,row.week,row.home_team,row.away_team,row.kickoff_at)!=(season,week,home,away,kickoff):raise ValueError('Quote canonical game scope differs')
                if row.sanity_errors():raise ValueError(','.join(row.sanity_errors()))
                if not observed<=received<=cutoff or observed>=kickoff or received>=kickoff:raise ValueError('Quote after cutoff/lock or clock order invalid')
                if raw.get('provider_updated_at') and utc_time(raw['provider_updated_at'])>observed:raise ValueError('Provider event clock after observation')
                if (cutoff-observed).total_seconds()>max_age_hours*3600:raise ValueError('Quote stale at feature cutoff')
                valid.append((row,raw))
            except (KeyError,TypeError,ValueError) as exc:
                rejected.append(dict(game_id=gid,market_snapshot_id=raw.get('market_snapshot_id'),reason=str(exc)))
        latest=max((r.observed_at for r,_ in valid),default=None)
        choices=[(r,raw) for r,raw in valid if r.observed_at==latest]
        conflict=len({(r.game_total,r.home_spread) for r,_ in choices})>1
        selected=choices[0][0] if choices and not conflict else None
        def consistent(field):
            values={raw.get(field) for _,raw in choices}
            return next(iter(values)) if selected and len(values)==1 else None
        # Optional details must originate from the verified same-snapshot
        # extractor; canonical current observations alone have no opening/ML.
        details_valid=selected and all(raw.get('detail_source_snapshot_id')==raw['source_snapshot_id'] and raw.get('bookmaker')=='DraftKings' for _,raw in choices)
        opening_total=consistent('opening_total') if details_valid else None
        opening_home=consistent('opening_home_spread') if details_valid else None
        home_ml=consistent('home_moneyline') if details_valid else None
        away_ml=consistent('away_moneyline') if details_valid else None
        if opening_total is not None and (type(opening_total) not in {int,float} or not isfinite(opening_total) or not 20<=opening_total<=80):opening_total=None
        if opening_home is not None and (type(opening_home) not in {int,float} or not isfinite(opening_home) or abs(opening_home)>30):opening_home=None
        if any(type(v) not in {int,float} or not isfinite(v) or abs(v)<100 for v in (home_ml,away_ml)):home_ml=away_ml=None
        quote_source=sorted({r.source for r,_ in choices}) if selected else []
        # Keeping all equivalent provenance avoids declaring a UUID ordering a
        # football preference when two captures contain the same quote.
        provenance.extend(dict(game_id=gid,market_snapshot_id=r.snapshot_id,source_snapshot_id=raw['source_snapshot_id'],
            source=r.source,source_game_id=r.source_game_id,observed_at=r.observed_at.isoformat(),ingested_at=r.ingested_at.isoformat()) for r,raw in choices)
        for team,opponent,sign in ((home,away,1),(away,home,-1)):
            spread=selected.home_spread*sign if selected else None
            total=selected.game_total if selected else None
            values={'G19-M01':total,'G19-M04':spread,
                'G19-M07':(total-spread)/2 if selected else None,
                'G19-M08':(total+spread)/2 if selected else None,
                'G19-M02':opening_total,'G19-M03':total-opening_total if total is not None and opening_total is not None else None,
                'G19-M05':opening_home*sign if opening_home is not None else None,
                'G19-M06':spread-opening_home*sign if spread is not None and opening_home is not None else None,
                'G19-M09':_implied(home_ml if sign==1 else away_ml) if home_ml is not None else None}
            output.append(dict(game_id=gid,season=season,week=week,team=team,opponent=opponent,home=sign==1,
                quote_source=quote_source,metrics={mid:dict(value=v,unit='probability' if mid=='G19-M09' else 'NFL_points',forecast=False,
                    kind='raw_moneyline_implied_break_even_not_calibrated_probability' if mid=='G19-M09' else 'market_implied_points_not_internal_forecast' if mid in {'G19-M07','G19-M08'} else 'observed_pregame_market',
                    reason=None if v is not None else 'conflicting_latest_quotes' if conflict else 'explicit_same_book_opening_or_moneyline_source_required' if mid not in CURRENT_IDS else 'no_valid_current_quote') for mid,v in values.items()},
                moneyline_pair=dict(american_odds=home_ml if sign==1 else away_ml,
                    two_sided_overround=_implied(home_ml)+_implied(away_ml)-1 if home_ml is not None else None,
                    no_vig_proportional_probability=_implied(home_ml if sign==1 else away_ml)/(_implied(home_ml)+_implied(away_ml)) if home_ml is not None else None,
                    method='Raw break-even probability retains bookmaker margin; proportional two-sided normalization separately named, not calibrated likelihood')))
    semantic=dict(version=VERSION,games=sorted(output,key=lambda r:(r['game_id'],r['team'])),
        spread_convention='Conventional team betting sign: favored team negative; implied=(total-team_spread)/2',
        missing_source_contracts={'G19-M10':'Compatible internal team-score forecast not supplied; fantasy points are not team scoring'})
    return {**semantic,'semantic_sha256':digest(semantic),'forecast':None,
        'provenance':dict(decision_cutoff_at=cutoff.isoformat(),selected_observations=provenance,rejected=rejected,
            source_verification='Caller must verify actual indexed source bytes and completed ingest; not asserted by this pure builder')}
