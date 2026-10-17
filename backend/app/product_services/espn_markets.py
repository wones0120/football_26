"""Current DraftKings lines distributed by ESPN; capture time is not quote time."""

from __future__ import annotations

import json
from math import isclose
from urllib.request import Request, urlopen

from .market_snapshots import MarketSnapshot, canonical_team, utc_time


def scoreboard_url(season: int, week: int) -> str:
    return ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
            f"?dates={season}&seasontype=2&week={week}")


def fetch_scoreboard(season: int, week: int) -> dict:
    request = Request(scoreboard_url(season, week), headers={"Accept": "application/json",
                                                           "Cache-Control": "no-cache"})
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise ValueError("ESPN returned an invalid NFL scoreboard")
    return payload


def parse_scoreboard(payload, *, schedule, season, week, captured_at):
    """Require exact home/away/kickoff identity and complete current two-sided lines."""
    captured_at = utc_time(captured_at)
    if (int(payload["season"]["year"]) != season or int(payload["season"]["type"]) != 2
            or int(payload["week"]["number"]) != week):
        raise ValueError("ESPN season/week does not match the requested regular-season slate")
    valid, rejected = [], []
    for game in schedule:
        try:
            home, away = canonical_team(game["home_team"]), canonical_team(game["away_team"])
            kickoff = utc_time(game["kickoff_at"])
            if kickoff <= captured_at:
                raise ValueError("Game is at or after kickoff")
            matches = []
            for event in payload["events"]:
                for competition in event.get("competitions", []):
                    teams = {c["homeAway"]: canonical_team(c["team"]["abbreviation"])
                             for c in competition.get("competitors", [])}
                    if (teams.get("home"), teams.get("away")) == (home, away):
                        matches.append((event, competition))
            if len(matches) != 1:
                raise ValueError("Missing or ambiguous ESPN game")
            event, competition = matches[0]
            if not event.get("id") or abs((utc_time(competition["date"]) - kickoff).total_seconds()) > 60:
                raise ValueError("ESPN game identity/kickoff mismatch")
            if competition["status"]["type"]["state"] != "pre":
                raise ValueError("ESPN game is not pregame")
            quotes = [q for q in competition.get("odds", [])
                      if str(q.get("provider", {}).get("id")) == "100"
                      and q["provider"].get("name") in {"DraftKings", "Draft Kings"}]
            if len(quotes) != 1:
                raise ValueError("Missing or ambiguous DraftKings lines on ESPN")
            quote = quotes[0]
            # ESPN calls the latest line 'close', even for scheduled games.
            # Never substitute the opening line or infer spread sign from 'details'.
            spread = float(quote["pointSpread"]["home"]["close"]["line"])
            away_spread = float(quote["pointSpread"]["away"]["close"]["line"])
            over = quote["total"]["over"]["close"]["line"]
            under = quote["total"]["under"]["close"]["line"]
            if not str(over).startswith("o") or not str(under).startswith("u"):
                raise ValueError("Invalid ESPN total sides")
            total = float(over[1:])
            if not (isclose(spread, -away_spread) and isclose(total, float(under[1:]))
                    and isclose(total, float(quote["overUnder"]))):
                raise ValueError("Inconsistent ESPN spread/total sides")
            row = MarketSnapshot(season=season, week=week, game_id=str(game["game_id"]),
                home_team=home, away_team=away, kickoff_at=kickoff,
                game_total=total, home_spread=spread, source="espn_draftkings",
                source_game_id=str(event["id"]), observed_at=captured_at, ingested_at=captured_at)
            if row.sanity_errors():
                raise ValueError(", ".join(row.sanity_errors()))
            valid.append(row)
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append({"game_id": game["game_id"], "reason": str(exc)})
    return valid, rejected
