"""Primary historical nonparticipation intake for conditional workload forecasts."""
from datetime import UTC, datetime
from io import BytesIO
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from Database.player_identity import normalize_player_name, normalize_position
from .market_snapshots import canonical_team, NFL_TEAM_NAMES
from .official_injuries import _Document, _record_identity
from ..models import SourceSnapshot
from ..services.source_capture import SourceCaptureService, verify_snapshot_artifact

CONTRACT = "official_gamebook_not_active_v1"
DATASET = "workload_gamebook_participation"


def parse_not_active(first_page, game):
    """Exact game/date/team header and both roster columns; no blank inference."""
    compact = " ".join(first_page.split())
    date = re.search(r"Date:\s*\w+,\s*(\d+/\d+/\d+)", compact)
    expected_date = str(game["gameday"])[:10]
    if not date or datetime.strptime(date[1], "%m/%d/%Y").date().isoformat() != expected_date:
        raise ValueError("Official gamebook date differs from canonical game")
    names = {team: next(name for name,code in NFL_TEAM_NAMES.items() if code == team)
             for team in (game["away_team"],game["home_team"])}
    if f"{names[game['away_team']]} at {names[game['home_team']]}" not in compact:
        raise ValueError("Official gamebook matchup differs from canonical game")
    lines = first_page.splitlines()
    markers = [(i,list(re.finditer(r"Not Active",line))) for i,line in enumerate(lines)]
    markers = [(i,m) for i,m in markers if len(m)==2]
    if len(markers) != 1:
        raise ValueError("Official gamebook lacks two explicit Not Active roster columns")
    start, positions = markers[0]
    split = (positions[0].start()+positions[1].end())//2
    end = next((i for i in range(start+1,len(lines)) if "VISITOR:" in lines[i] or "Field Goals" in lines[i]), len(lines))
    rows = []
    for team,side in ((game["away_team"],0),(game["home_team"],1)):
        block = " ".join(line[:split] if side==0 else line[split:] for line in lines[start+1:end])
        for entry in block.split(","):
            match = re.fullmatch(r"\s*(3QB|QB|RB|FB|WR|TE)\s+(\d{1,2})\s+(.+?)\s*", entry)
            if not match:
                continue
            position = normalize_position("QB" if match[1] == "3QB" else match[1])
            rows.append(dict(team=team,position=position,jersey=int(match[2]),player_name=match[3],
                season=game['season'],week=game['week'],
                source_key=f"gamebook:{game['game_id']}:{team}:{match[2]}:{position}"))
    return rows


def resolve_roster_identity(row, rosters):
    """Native roster jersey/team/position key; initials only cross-check it."""
    abbreviation = normalize_player_name(row["player_name"]).split()
    candidates = {}
    for source in rosters:
        if source.get('season')!=row.get('season') or source.get('week')!=row.get('week'):
            continue
        raw = source.get("raw_row_json") or {}
        try:
            jersey = int(float(raw.get("jersey_number",raw.get("jersey"))))
        except (TypeError,ValueError):
            continue
        if canonical_team(source["team"]) != row["team"] or normalize_position(source["position"]) != row["position"] or jersey != row["jersey"]:
            continue
        full = normalize_player_name(source.get("player_name")).split()
        if not abbreviation or not full or abbreviation[0][0] != full[0][0] or abbreviation[-1] != full[-1]:
            continue
        if source.get("player_master_id"):
            candidates.setdefault(str(source["player_master_id"]),[]).append(int(source["raw_nfl_weekly_roster_id"]))
    if len(candidates) != 1:
        return None, [], "ambiguous_native_roster" if candidates else "missing_native_roster"
    pid = next(iter(candidates))
    return pid, sorted(candidates[pid]), "native_roster_team_jersey_position_initial_crosscheck"


def gamecenter_uri(game):
    # NFL game centers use team nicknames; club web domains are unrelated.
    def slug(team):
        name=next(name for name,code in NFL_TEAM_NAMES.items() if code==canonical_team(team))
        return name.rsplit(' ',1)[-1].lower()
    return f"https://www.nfl.com/games/{slug(game['away_team'])}-at-{slug(game['home_team'])}-{game['season']}-reg-{game['week']}?tab=recap"


def capture_game(engine, game, *, target_lock_at):
    """Idempotent verified capture; JSON derivation references immutable PDF."""
    with Session(engine) as session:
        existing = list(session.scalars(select(SourceSnapshot).where(
            SourceSnapshot.dataset==DATASET,SourceSnapshot.season==game["season"],
            SourceSnapshot.week==game["week"]).order_by(SourceSnapshot.captured_at.desc())))
        for snapshot in existing:
            if (snapshot.metadata_json or {}).get("game_id") == game["game_id"] and (snapshot.metadata_json or {}).get("contract") == CONTRACT and not (snapshot.metadata_json or {}).get('unresolved'):
                verify_snapshot_artifact(snapshot)
                return {**snapshot.metadata_json,"snapshot_id":snapshot.snapshot_id}
    uri = gamecenter_uri(game)
    response = httpx.get(uri,timeout=15,follow_redirects=False);response.raise_for_status()
    links = {a.attrs.get("href") for a in _Document(response.text).root.find("a")
             if "game book" in a.content().lower() and ".pdf" in a.attrs.get("href","")}
    if len(links) != 1:
        raise ValueError("Official game page does not identify one gamebook")
    pdf_uri = next(iter(links));url = urlparse(pdf_uri)
    if url.scheme != "https" or url.hostname != "static.www.nfl.com" or not url.path.endswith(".pdf") or "/gamecenter/" not in url.path:
        raise ValueError("Gamebook URL is not an official NFL gamecenter PDF")
    pdf = httpx.get(pdf_uri,timeout=15,follow_redirects=False);pdf.raise_for_status()
    observed = datetime.now(UTC)
    first = PdfReader(BytesIO(pdf.content)).pages[0].extract_text(extraction_mode="layout")
    parsed = parse_not_active(first,game)
    def roster_rows():
        with engine.connect() as connection:
            return [dict(r) for r in connection.execute(text("""
            WITH aliases AS (SELECT source_key,MIN(player_master_id::text) AS player_master_id
              FROM player_alias WHERE source_system='nflreadpy' GROUP BY source_key HAVING COUNT(DISTINCT player_master_id)=1)
            SELECT DISTINCT ON(r.gsis_id) r.*,a.player_master_id FROM raw_nfl_weekly_roster r LEFT JOIN aliases a ON a.source_key=r.gsis_id
            WHERE r.season=:season AND r.week=:week AND r.team IN (:home,:away) AND r.created_at<=:cutoff
            ORDER BY r.gsis_id,r.created_at DESC,r.raw_nfl_weekly_roster_id DESC
        """),dict(season=game["season"],week=game["week"],home=game["home_team"],away=game["away_team"],cutoff=datetime.now(UTC).replace(tzinfo=None))).mappings()]
    rosters=roster_rows()
    if any(resolve_roster_identity(row,rosters)[0] is None for row in parsed):
        from ..schemas import NflReadPySeasonRequest
        with Session(engine) as session:
            SourceCaptureService(session).capture_and_ingest_nflreadpy_weekly_rosters(
                NflReadPySeasonRequest(season=game["season"],weeks=[game["week"]]),
                slate="GAMEBOOK",slate_lock_at=target_lock_at)
        rosters=roster_rows()
    with TemporaryDirectory() as directory,Session(engine) as session:
        path = Path(directory)/"official_gamebook.pdf";path.write_bytes(pdf.content)
        raw = SourceCaptureService(session).capture_file(path,source_system="nfl_official",dataset="official_gamebook_pdf",
            season=game["season"],week=game["week"],slate=None,source_uri=pdf_uri,
            source_license="Official NFL gamebook retained for audit",slate_lock_at=target_lock_at,
            media_type="application/pdf",metadata={"game_id":game["game_id"],"page_uri":uri,"http_headers":dict(pdf.headers)})
        raw_id = str(raw.snapshot.snapshot_id)
    verified = [];unresolved = []
    with engine.begin() as connection:
        for row in parsed:
            pid,source_ids,method = resolve_roster_identity(row,rosters)
            if not _record_identity(connection,row,pid,method,season=game["season"],week=game["week"],slate="GAMEBOOK"):
                unresolved.append(row);continue
            verified.append(dict(player_master_id=pid,team=row["team"],position=row["position"],
                period=game["season"]*100+game["week"],kind=CONTRACT,game_id=game["game_id"],
                source_uri=pdf_uri,source_snapshot_id=raw_id,source_sha256=hashlib.sha256(pdf.content).hexdigest(),
                observed_at=observed.isoformat(),identity_method=method,roster_source_ids=source_ids,
                primary_status="NOT_ACTIVE"))
    envelope=dict(contract=CONTRACT,game_id=game["game_id"],rows=verified,unresolved=unresolved,
        pdf_snapshot_id=raw_id,observed_at=observed.isoformat(),source_uri=pdf_uri)
    with TemporaryDirectory() as directory,Session(engine) as session:
        path=Path(directory)/"verified_gamebook_participation.json";path.write_text(json.dumps(envelope,sort_keys=True))
        derived=SourceCaptureService(session).capture_file(path,source_system="nfl_official",dataset=DATASET,
            season=game["season"],week=game["week"],slate=None,source_uri=pdf_uri,
            source_license="Derived canonical official NFL nonparticipation evidence",slate_lock_at=target_lock_at,
            media_type="application/json",row_count=len(verified),metadata=envelope)
        return {**envelope,"snapshot_id":str(derived.snapshot.snapshot_id)}


def refresh_slate_gaps(engine, *, season, week, slate, target_lock_at, progress=None):
    """Bounded automatic Prepare intake; only missing intervening native games."""
    from .workload_count_forecast import load_history, team_games
    now=datetime.now(UTC)
    weekly=load_history(engine,season=season,week=week,cutoff=now.replace(tzinfo=None))
    with engine.connect() as connection:
        native=[dict(r) for r in connection.execute(text("""SELECT DISTINCT player_master_id,team
            FROM curated_salary WHERE season=:season AND week=:week AND upper(slate)=upper(:slate)
            AND source_system='draftkings' """),dict(season=season,week=week,slate=slate)).mappings()]
        schedules=[dict(r) for r in connection.execute(text("""SELECT DISTINCT ON(game_id)
            season,week,game_id,home_team,away_team,raw_row_json FROM raw_nfl_schedule
            WHERE season=:season AND week<:week AND created_at<=:cutoff
            ORDER BY game_id,created_at DESC """),dict(season=season,week=week,cutoff=now.replace(tzinfo=None))).mappings()]
    history=team_games(weekly);needed=set()
    verified={(g['player_master_id'],g['team'],g['period']) for g in load_verified_gaps(engine,season=season,cutoff=now)}
    for actor in native:
        team=canonical_team(actor['team']);pid=str(actor['player_master_id'])
        rows=weekly.loc[weekly.player_master_id.eq(pid)&weekly.team.eq(team)&weekly.period.ge(season*100)].sort_values('period').tail(3)
        games=history.loc[history.team.eq(team)].sort_values('period')
        if len(rows)<2 or games.empty or int(rows.iloc[-1].period)!=int(games.iloc[-1].period):continue
        for period in games.loc[games.period.between(int(rows.iloc[0].period),int(rows.iloc[-1].period)),'period']:
            if period not in set(rows.period) and (pid,team,int(period)) not in verified:needed.add((team,int(period)%100))
    selected=[]
    for game in schedules:
        game['home_team']=canonical_team(game['home_team']);game['away_team']=canonical_team(game['away_team'])
        if not any((team,game['week']) in needed for team in (game['home_team'],game['away_team'])):continue
        game['gameday']=game['raw_row_json'].get('gameday');selected.append(game)
    return _capture_bounded_games(engine, selected, target_lock_at=target_lock_at, progress=progress)


def _capture_bounded_games(engine, selected, *, target_lock_at, progress=None):
    """Make bounded progress on large slates; pending games remain unverified."""
    ordered=sorted(selected,key=lambda g:g['game_id'])
    batch=ordered[:8]
    receipts=[]
    for index,game in enumerate(batch):
        if progress:progress('workload_participation',index,len(batch),f"Verifying official inactive evidence: {game['game_id']}")
        try:receipts.append(capture_game(engine,game,target_lock_at=target_lock_at))
        except (ValueError,httpx.HTTPError) as exc:
            receipts.append(dict(game_id=game['game_id'],status='unavailable',reason=str(exc)))
    if len(ordered)>len(batch):
        receipts.append(dict(status='partial',reason='Bounded eight-game intake; pending games have no new participation proof',
            pending_game_ids=[g['game_id'] for g in ordered[len(batch):]],
            requested_games=len(ordered),attempted_games=len(batch)))
    return receipts


def load_verified_gaps(engine, *, season, cutoff):
    """Read verified immutable JSON/PDF lineage, never inferred roster blanks."""
    result=[]
    with Session(engine) as session:
        snapshots=list(session.scalars(select(SourceSnapshot).where(SourceSnapshot.dataset==DATASET,
            SourceSnapshot.season==season,SourceSnapshot.observed_at<=cutoff,
            SourceSnapshot.captured_at<=cutoff)))
        for snapshot in snapshots:
            verify_snapshot_artifact(snapshot)
            envelope=json.loads(Path(snapshot.artifact_path).read_text())
            if envelope.get('contract')!=CONTRACT:continue
            raw=session.get(SourceSnapshot,envelope['pdf_snapshot_id'])
            if not raw or raw.observed_at>cutoff or raw.captured_at>cutoff:continue
            verify_snapshot_artifact(raw)
            for row in envelope['rows']:
                if row.get('source_sha256')!=raw.content_sha256 or row.get('kind')!=CONTRACT:continue
                result.append({**row,'derived_snapshot_id':snapshot.snapshot_id})
    from .workload_ir_participation import load_verified_ir_gaps
    return result + load_verified_ir_gaps(engine,season=season,cutoff=cutoff)
