"""Observed native venue classification, independent of market or weather guesses."""
import csv,json
from pathlib import Path
from .evaluation_record import digest
from .factual_designation import clock as record_clock
from .market_snapshots import canonical_team,utc_time
from .espn_markets import scoreboard_url
from backend.app.services.source_capture import verify_snapshot_artifact

VERSION='native_venue_schedule_features_v1'


def extract_venue_schedule_features(snapshot,games,*,cutoff):
    """Native ESPN event + exact canonical home/away/kickoff, no name joins.

    `venue.indoor` is the provider's venue classification, not observed roof
    position or an assertion about game-time weather. Unsupported fields stay
    explicit rather than importing realized PBP conditions as pregame forecasts.
    """
    cutoff=utc_time(cutoff)
    if (snapshot.source_system,snapshot.dataset)!=('espn','schedule_market_snapshot') or snapshot.source_uri!=scoreboard_url(snapshot.season,snapshot.week):raise ValueError('Canonical indexed scoreboard source required')
    verify_snapshot_artifact(snapshot)
    if snapshot.byte_count>4*1024*1024:raise ValueError('Bounded venue source required')
    if not record_clock(snapshot.observed_at)<=record_clock(snapshot.captured_at)<=cutoff:raise ValueError('Venue source unavailable at cutoff')
    limit=csv.field_size_limit()
    try:
        csv.field_size_limit(4*1024*1024)
        with Path(snapshot.artifact_path).open() as f:envelopes=list(csv.DictReader(f))
    finally:csv.field_size_limit(limit)
    if len(envelopes)!=1:raise ValueError('One native scoreboard envelope required')
    raw=envelopes[0];observed=utc_time(raw['capture_observed_at'])
    if observed>record_clock(snapshot.observed_at):raise ValueError('Envelope observation after indexed source')
    payload=json.loads(raw['response_json'])
    if (int(payload['season']['year']),int(payload['season']['type']),int(payload['week']['number']))!=(snapshot.season,2,snapshot.week):raise ValueError('Native REG season/week differs')
    results=[];seen=set();warnings=[]
    for game in games:
        gid=game['game_id'];native=str(game.get('source_game_id') or '')
        if not gid or gid in seen or not native:raise ValueError('Unique canonical and native game IDs required')
        seen.add(gid)
        home=canonical_team(game['home_team']);away=canonical_team(game['away_team']);kickoff=utc_time(game['kickoff_at'])
        if home==away or (game['season'],game['week'])!=(snapshot.season,snapshot.week):raise ValueError('Canonical game scope differs')
        if not observed<=record_clock(snapshot.captured_at)<kickoff:raise ValueError('Venue observation/receipt must precede kickoff')
        matches=[]
        for event in payload['events']:
            if str(event.get('id'))!=native:continue
            for competition in event.get('competitions',[]):
                teams={c['homeAway']:canonical_team(c['team']['abbreviation']) for c in competition.get('competitors',[])}
                if teams=={'home':home,'away':away} and abs((utc_time(competition['date'])-kickoff).total_seconds())<=60 and competition.get('status',{}).get('type',{}).get('state')=='pre':matches.append(competition)
        if len(matches)!=1:raise ValueError('Missing/ambiguous native pregame venue event')
        venue=matches[0].get('venue') or {};indoor=venue.get('indoor')
        classification=('indoor' if indoor else 'outdoor') if venue.get('id') and type(indoor) is bool else None
        for team,opponent,is_home in ((home,away,True),(away,home,False)):
            results.append(dict(game_id=gid,source_game_id=native,team=team,opponent=opponent,
                venue_id=str(venue['id']) if venue.get('id') else None,
                metrics={'G20-M01':dict(value='home' if is_home else 'away',unit='categorical_home_away',forecast=False),
                    'G20-M02':dict(value=classification,unit='provider_venue_indoor_classification',forecast=False,
                        missing_reason=None if classification else 'native_venue_id_and_typed_indoor_flag_required')},
                venue_name=venue.get('fullName'),source_address=venue.get('address')))
    semantic=dict(version=VERSION,season=snapshot.season,week=snapshot.week,games=sorted(results,key=lambda r:(r['game_id'],r['team'])),
        definition='Venue indoor classification is not retractable-roof position or a game-time weather forecast',
        source_gaps={'G20-M03':'No explicit roof-position observation','G20-M04':'No authenticated game-time temperature forecast',
            'G20-M05':'No authenticated sustained-wind forecast','G20-M06':'No authenticated gust forecast','G20-M07':'No authenticated precipitation forecast',
            'G20-M08':'Playing-surface material not supplied','G20-M09':'Last actually played game chronology not supplied',
            'G20-M10':'No source-backed travel itinerary or origin timezone'})
    return {**semantic,'semantic_sha256':digest(semantic),'forecast':None,
        'provenance':dict(source_snapshot_id=str(snapshot.snapshot_id),source_sha256=snapshot.content_sha256,
            native_observed_at=observed.isoformat(),source_received_at=str(snapshot.captured_at),decision_cutoff_at=cutoff.isoformat(),
            original_publication_at=None,warnings=warnings)}
