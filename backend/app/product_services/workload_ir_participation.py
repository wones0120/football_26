"""Verified closed IR intervals from immutable official club transaction prose.

This narrow parser accepts a dated activation with an explicit prior IR date in
the same paragraph. It never infers absence from missing stats or roster blanks.
"""
from datetime import datetime
from pathlib import Path
import re
from urllib.parse import urlparse

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from Database.player_identity import normalize_player_name, normalize_position
from ..models import SourceSnapshot
from ..services.source_capture import verify_snapshot_artifact
from .official_injuries import _Document
from .market_snapshots import NFL_TEAM_NAMES

CONTRACT = 'official_ir_interval_v1'
DATASET = 'workload_ir_return_transaction'


def parse_ir_return(html, actor):
    document = _Document(html).root
    dates = {n.content() for n in document.find(css_class='nfl-c-article__dates')}
    if len(dates) != 1:
        raise ValueError('IR transaction requires one explicit article date')
    returned = datetime.strptime(next(iter(dates)), '%b %d, %Y at %I:%M %p').date()
    pattern = re.compile(r'The (.+?) announced today that (QB|RB|WR|TE) (.+?) has been activated to the 53-man roster\. '
                         r'He was placed on injured reserve on ([A-Za-z]+ \d{1,2})\b')
    matches = [m for node in document.find('p') if (m := pattern.search(' '.join(node.content().split())))]
    if len(matches) != 1:
        raise ValueError('IR transaction lacks one explicit activation/placement paragraph')
    team_name, position, name, placed = matches[0].groups()
    if (NFL_TEAM_NAMES.get(team_name) != actor['team']
            or normalize_position(position) != normalize_position(actor['position'])
            or normalize_player_name(name) != normalize_player_name(actor['player_name'])):
        raise ValueError('IR transaction team/position/name differs from canonical native roster')
    entered = datetime.strptime(f'{placed} {returned.year}', '%B %d %Y').date()
    if entered >= returned:
        raise ValueError('IR interval must close after placement within the same season')
    return dict(entered_at=entered.isoformat(), returned_at=returned.isoformat())


def load_verified_ir_gaps(engine, *, season, cutoff):
    """Reverify raw bytes, native roster identity and dated schedule on every read."""
    from .factual_designation import clock
    rows = []
    with Session(engine) as session:
        snapshots = list(session.scalars(select(SourceSnapshot).where(
            SourceSnapshot.dataset == DATASET, SourceSnapshot.source_system == 'nfl_official',
            SourceSnapshot.season == season, SourceSnapshot.observed_at <= cutoff,
            SourceSnapshot.captured_at <= cutoff)))
        for snapshot in snapshots:
            verify_snapshot_artifact(snapshot)
            metadata = snapshot.metadata_json or {}
            if metadata.get('contract') != CONTRACT:
                continue
            actor = metadata['actor']
            host = urlparse(snapshot.source_uri or '').hostname
            if (urlparse(snapshot.source_uri or '').scheme != 'https'
                    or host != urlparse(actor['role_source_uri']).hostname
                    or not actor['role_source_uri'].startswith('https://')
                    or not actor.get('role_source_ids')):
                raise ValueError('IR source must match verified official current-role club host')
            roster = session.execute(text("""SELECT r.player_name,r.position,r.team,r.gsis_id
                FROM raw_nfl_weekly_roster r JOIN player_alias a
                ON a.source_system='nflreadpy' AND a.source_key=r.gsis_id
                WHERE r.raw_nfl_weekly_roster_id=:row AND a.player_master_id=:pid
                AND r.season=:season AND r.created_at<=:cutoff"""),
                dict(row=actor['roster_source_id'], pid=actor['player_master_id'], season=season,
                     cutoff=clock(cutoff).replace(tzinfo=None))).mappings().all()
            if (len(roster) != 1 or roster[0]['gsis_id'] != actor['native_player_id']
                    or roster[0]['team'] != actor['team']
                    or normalize_position(roster[0]['position']) != actor['position']
                    or normalize_player_name(roster[0]['player_name']) != normalize_player_name(actor['player_name'])):
                raise ValueError('IR source native roster identity is missing or ambiguous')
            interval = parse_ir_return(Path(snapshot.artifact_path).read_text(), actor)
            if interval['returned_at'] >= clock(cutoff).date().isoformat():
                raise ValueError('IR return is not prior to the decision day')
            games = session.execute(text("""SELECT DISTINCT ON(game_id) game_id,week,raw_row_json
                FROM raw_nfl_schedule WHERE season=:season AND (home_team=:team OR away_team=:team)
                AND created_at<=:cutoff ORDER BY game_id,created_at DESC"""),
                dict(season=season, team=actor['team'], cutoff=clock(cutoff).replace(tzinfo=None))).mappings()
            for game in games:
                day = game['raw_row_json'].get('gameday')
                # Strict bounds avoid inventing same-day placement/activation clocks.
                if day and interval['entered_at'] < str(day)[:10] < interval['returned_at']:
                    rows.append(dict(kind=CONTRACT, player_master_id=actor['player_master_id'],
                        team=actor['team'], position=actor['position'], period=season*100+game['week'],
                        game_id=game['game_id'], primary_status='INJURED_RESERVE', interval=interval,
                        source_uri=snapshot.source_uri, source_snapshot_id=snapshot.snapshot_id,
                        source_sha256=snapshot.content_sha256, observed_at=snapshot.observed_at.isoformat(),
                        received_at=snapshot.captured_at.isoformat(), roster_source_ids=[actor['roster_source_id']],
                        identity_method='native_GSIS_alias_and_dated_team_position_name_crosscheck',
                        historical_pregame_capture_proven=False))
    return rows
