"""Current official NFL game designations, with immutable HTTP observations."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from Database.dst import normalize_team
from Database.player_identity import normalize_player_name, normalize_position, strip_name_suffix
from .pregame_context import PregameContextService
from .showdown_player_context import PlayerContextUnresolved
from ..services.source_capture import SourceCaptureService

SOURCE = "nfl_official"
HEADERS = ["Player", "Position", "Injuries", "Practice Status", "Game Status"]
DESIGNATIONS = {"OUT", "QUESTIONABLE", "DOUBTFUL", "IR", "PUP", "SUSPENDED", "INACTIVE", "ACTIVE"}


class _Node:
    def __init__(self, tag, attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def content(self):
        return " ".join(c.content() if isinstance(c, _Node) else c for c in self.children).strip()

    def find(self, tag=None, css_class=None):
        for child in self.children:
            if isinstance(child, _Node):
                if (tag is None or child.tag == tag) and (css_class is None or css_class in (child.attrs.get("class") or "").split()):
                    yield child
                yield from child.find(tag, css_class)


class _Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = _Node("document")
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, value):
        self.stack[-1].children.append(value)


def parse_official_report(html, *, season, week, slate_teams=None):
    document = _Document(html).root
    expected = f"/injuries/league/{season}/reg{week}"
    selected = {n.attrs.get("value") for n in document.find("option")
                if "selected" in n.attrs and (n.attrs.get("value") or "").startswith("/injuries/league/")}
    if selected != {expected}:
        raise ValueError("Official injury report season/week does not match the requested slate")
    rows = []
    for unit in document.find("section", "nfl-o-injury-report__unit"):
        teams = [normalize_team(n.content()) for n in unit.find("span", "nfl-c-matchup-strip__team-abbreviation")]
        if slate_teams is not None and not set(teams).intersection(slate_teams):
            continue
        tables = list(unit.find("table"))
        if len(teams) == 2 and len(set(teams)) == 2 and not tables:
            placeholders = list(unit.find("section", "nfl-o-no-results"))
            if len(placeholders) == 2 and all(n.content() == "No Injuries Reported" for n in placeholders):
                # A future matchup may have no published tables yet. Retain
                # the missing-team coverage; this never clears any player.
                continue
        if len(teams) != 2 or len(set(teams)) != 2 or len(tables) != 2:
            raise ValueError("Official injury report matchup/table structure changed")
        for team, table in zip(teams, tables):
            if [n.content() for n in table.find("th")] != HEADERS:
                raise ValueError("Official injury report columns changed")
            for tr in table.find("tr"):
                cells = list(tr.find("td"))
                if not cells:
                    continue
                if len(cells) != len(HEADERS):
                    raise ValueError("Official injury report row is incomplete")
                links = [n.attrs.get("href") for n in cells[0].find("a")
                         if (n.attrs.get("href") or "").startswith("/players/")]
                if len(links) != 1:
                    raise ValueError("Official injury row lacks a stable player profile key")
                status = cells[4].content().upper()
                rows.append(dict(team=team, player_name=cells[0].content(), position=normalize_position(cells[1].content()),
                    source_key=links[0].rstrip("/"), injury=cells[2].content(), practice_status=cells[3].content(),
                    game_status=status if status in DESIGNATIONS else None))
    if not rows:
        raise ValueError("Official weekly injury report contains no player rows")
    return rows


def observation_clock(headers, received_at):
    """A live table observation, respecting upstream cache age; not publication."""
    received_at = received_at.astimezone(UTC)
    date = headers.get("date")
    origin = parsedate_to_datetime(date).astimezone(UTC) if date else received_at
    age = float(headers.get("age", "0"))
    if age < 0 or origin > received_at + timedelta(minutes=5):
        raise ValueError("Official report has an invalid HTTP observation clock")
    return min(origin, received_at - timedelta(seconds=age), received_at)


def resolve_official_player(row, salaries, aliases):
    candidates = {str(s["player_id"]) for s in salaries
                  if normalize_team(s["team"]) == row["team"] and normalize_position(s["position"]) == row["position"]}
    linked = {str(a["player_master_id"]) for a in aliases
              if a["source_system"] == SOURCE and a["source_key"] == row["source_key"]}
    if linked:
        return (next(iter(linked)), "source_native_id") if len(linked) == 1 and linked <= candidates else (None, "identity_conflict")
    name = strip_name_suffix(row["player_name"])
    matching = {str(s["player_id"]) for s in salaries if str(s["player_id"]) in candidates
                and name in {strip_name_suffix(s["player_name"]), strip_name_suffix(s["full_name"])}}
    matching.update(str(a["player_master_id"]) for a in aliases if str(a["player_master_id"]) in candidates
                    and strip_name_suffix(a["alias_name"]) == name)
    return (next(iter(matching)), "team_position_normalized_name") if len(matching) == 1 else (None, "ambiguous" if matching else "no_match")


def _record_identity(connection, row, player_id, reason, *, season, week, slate):
    key = f"{season}:{week}:{slate}:{row['source_key']}"
    params = dict(row, player_id=player_id, reason=reason, season=season, week=week, slate=slate,
                  normalized_name=normalize_player_name(row["player_name"]), key=key,
                  quarantine_id="official-injury:"+hashlib.sha256(key.encode()).hexdigest()[:32])
    if player_id:
        saved = connection.execute(text("""
            INSERT INTO public.player_alias
            (player_master_id,source_system,source_key,alias_name,normalized_alias,team,position,first_seen_season,first_seen_week,last_seen_at,created_at)
            VALUES (:player_id,'nfl_official',:source_key,:player_name,:normalized_name,:team,:position,:season,:week,now(),now())
            ON CONFLICT (source_system,source_key) DO UPDATE SET last_seen_at=now()
            WHERE player_alias.player_master_id=EXCLUDED.player_master_id
            RETURNING player_master_id
        """), params).scalar_one_or_none()
        if saved is None:
            return _record_identity(connection,row,None,"identity_conflict",season=season,week=week,slate=slate)
        connection.execute(text("""
            UPDATE target.identity_quarantine SET status='resolved',resolved_player_id=:player_id,
                resolution_reason=:reason,resolved_at=now(),updated_at=now()
            WHERE source_schema='public' AND source_table='official_injury_report' AND source_record_key=:key
        """), params)
    else:
        connection.execute(text("""
            INSERT INTO target.identity_quarantine
            (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,
             season,week,slate,source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
            VALUES (:quarantine_id,'player','public','official_injury_report',:key,'nfl_official',
                    :season,:week,:slate,:source_key,:player_name,:team,:position,:reason,'[]'::jsonb,'open',now(),now())
            ON CONFLICT (source_schema,source_table,source_record_key) DO UPDATE SET
                reason_code=EXCLUDED.reason_code,status='open',resolved_player_id=NULL,
                resolution_reason=NULL,resolved_at=NULL,updated_at=now()
        """), params)
    return player_id is not None


def refresh_official_injuries(engine, *, season, week, slate, games, slate_lock_at,
                              require_complete_team_coverage=True):
    uri = f"https://www.nfl.com/injuries/league/{season}/reg{week}"
    teams = {normalize_team(g[k]) for g in games for k in ("home_team", "away_team")}
    response = httpx.get(uri, timeout=30, follow_redirects=True, headers={"Cache-Control":"no-cache"})
    response.raise_for_status()
    received_at = datetime.now(UTC)
    headers = dict(response.headers)
    observed_at = observation_clock(headers, received_at)
    if received_at >= slate_lock_at:
        raise ValueError("Official report was received after slate lock")
    rows = [r for r in parse_official_report(response.text, season=season, week=week, slate_teams=teams) if r["team"] in teams]
    missing_teams = sorted(teams - {r["team"] for r in rows})
    if missing_teams and require_complete_team_coverage:
        raise ValueError("Official report does not contain all slate teams")
    # Store the actual HTTP observation, including body and cache clocks. Each
    # live response is distinct; recapturing an old article never renews it.
    envelope = dict(source_uri=uri, received_at=received_at.isoformat(), observed_at=observed_at.isoformat(),
                    headers=headers, body=response.text)
    with TemporaryDirectory() as directory, Session(engine) as session:
        path = Path(directory)/"official_injury_response.json"
        path.write_text(json.dumps(envelope, sort_keys=True))
        capture = SourceCaptureService(session).capture_file(path, source_system=SOURCE, dataset="official_injuries",
            season=season, week=week, slate=slate, source_uri=uri, slate_lock_at=slate_lock_at,
            source_license="NFL.com public weekly injury report; retained for source audit",
            effective_at=observed_at, observation_basis="http_response_clock", media_type="application/json",
            row_count=len(rows), metadata={"body_sha256":hashlib.sha256(response.content).hexdigest(),
                "publication_clock_available":False, "http_cache_age":headers.get("age"),
                "missing_slate_teams": missing_teams})
        snapshot_id = str(capture.snapshot.snapshot_id)
    with engine.connect() as connection:
        salaries = [dict(r) for r in connection.execute(text("""
            SELECT DISTINCT s.player_master_id AS player_id,s.player_name,s.team,s.position,m.full_name
            FROM public.curated_salary s JOIN public.player_master m USING(player_master_id)
            WHERE s.season=:season AND s.week=:week AND LOWER(s.slate)=LOWER(:slate) AND s.source_system='draftkings'
        """), dict(season=season,week=week,slate=slate)).mappings()]
        aliases = [dict(r) for r in connection.execute(text("""
            SELECT player_master_id,source_system,source_key,alias_name,team,position FROM public.player_alias
            WHERE player_master_id=ANY(:ids) OR source_system='nfl_official'
        """), {"ids":[s["player_id"] for s in salaries]}).mappings()]
    if not salaries:
        raise ValueError('Official injury refresh requires a nonempty native salary pool')
    players, unresolved, outside_position_domain = [], [], []
    native_positions = {normalize_position(s['position']) for s in salaries}
    with engine.begin() as connection:
        for row in rows:
            if row["position"] not in {"QB","RB","WR","TE","K"}:
                continue
            if row['position'] not in native_positions:
                # Classic has no kicker slot. Retain the raw official row and
                # report its scope; it is not an unresolved native-slate actor.
                linked = {str(a['player_master_id']) for a in aliases
                          if a['source_system']==SOURCE and a['source_key']==row['source_key']
                          and normalize_team(a.get('team'))==row['team']
                          and normalize_position(a.get('position'))==row['position']}
                if len(linked)==1:
                    _record_identity(connection,row,next(iter(linked)),
                        'source_native_id_outside_native_position_domain',season=season,week=week,slate=slate)
                outside_position_domain.append(dict(source_key=row['source_key'],team=row['team'],
                    position=row['position'],reason='Position absent from native salary pool; not a slate player context'))
                continue
            player_id, reason = resolve_official_player(row, salaries, aliases)
            recorded = _record_identity(connection, row, player_id, reason, season=season,week=week,slate=slate)
            if not recorded:
                unresolved.append(row["source_key"])
            elif row["game_status"] or row["practice_status"]:
                players.append(dict(player_id=player_id,team=row["team"],position=row["position"],injury_status=row["game_status"],
                    evidence={"source_snapshot_id":snapshot_id,"official_player_key":row["source_key"],
                        "identity_match":reason,"observation_basis":"http_response_clock",
                        "practice_report":{"practice_status":row["practice_status"],"observed_at":observed_at.isoformat()}}))
    context = PregameContextService(engine=engine).create_run(dict(season=season,week=week,slate=slate,
        source=SOURCE,source_uri=uri,observed_at=observed_at,players=players)) if players else None
    if unresolved:
        raise PlayerContextUnresolved("Official injury player identities require review: "+", ".join(unresolved))
    return dict(snapshot_id=snapshot_id,context_run_id=context["context_run_id"] if context else None,
                observed_at=observed_at.isoformat(),rows=len(rows),
                game_status_rows=sum(bool(p["injury_status"]) for p in players),
                practice_status_rows=sum(bool(p["evidence"]["practice_report"]["practice_status"]) for p in players),
                blank_status_rows=sum(r["game_status"] is None for r in rows),identity_unresolved=[],
                outside_native_position_domain=outside_position_domain,
                missing_slate_teams=missing_teams, complete_team_coverage=not missing_teams)
