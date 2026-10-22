"""Conserved descriptive event taxonomy, separate from count forecasts.

Input is an explicitly supplied immutable NFL play-by-play capture, never a
mutable research file. Original source flags remain attached to every event.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from uuid import UUID

from .factual_designation import clock

VERSION = "offensive_opportunity_events_v1"
CHANNELS = ("pass_attempts", "rush_attempts", "targets")
ZONES = ("outside20", "six_to_twenty", "inside5", "unknown")


def event_capture_state():
    """Current weekly-count Prepare has no operational PBP capture contract."""
    return {"version": VERSION, "status": "unavailable",
        "reason": "No immutable operational play-by-play capture supplied to count Prepare",
        "counts": None, "zones": None, "goal_to_go": None,
        "effect": "No event-zone feature or forecast consumed; existing total-count forecasts unchanged"}


def validate_event_evidence(receipt, *, before_period, cutoff):
    """Consume only a frozen, verified capture at the same forecast boundary."""
    value = deepcopy(receipt)
    supplied = value.pop("sha256", None)
    if supplied != hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest():
        raise ValueError("Event evidence checksum mismatch")
    if value.get("version") != VERSION or value.get("status") != "derived_descriptive_only":
        raise ValueError("Unsupported event evidence contract")
    source = value.get("source") or {}
    if source.get("verification") != "snapshot_artifact_sha256_verified":
        raise ValueError("Event capture requires verified source artifact")
    if any(not source.get(k) for k in ("snapshot_id", "content_sha256", "captured_at", "received_at")):
        raise ValueError("Event source identity/hash/capture/receipt missing")
    if cutoff is None:
        raise ValueError("Event receipt requires forecast decision cutoff")
    decision = clock(cutoff)
    if clock(value["decision_cutoff_at"]) > decision:
        raise ValueError("Event derivation after forecast cutoff")
    for key in ("captured_at", "received_at", "published_at"):
        if source.get(key) and clock(source[key]) > decision:
            raise ValueError("Event source clock after forecast cutoff")
    if clock(source["captured_at"]) > clock(source["received_at"]):
        raise ValueError("Event source capture is after receipt")
    if any(e.get("season_type") != "REG" or not 1 <= e["week"] <= 18
           or not 1920 <= e["season"] <= decision.year for e in value["events"]):
        raise ValueError("Event receipt has invalid regular-season scope")
    if any(e["season"] * 100 + e["week"] >= before_period for e in value["events"]):
        raise ValueError("Event source includes forecast-period or future game")
    return {**value, "sha256": supplied}


def _flag(value):
    if value is True or value == 1:
        return True
    if value is False or value == 0:
        return False
    return None


def _clock_replay_control(raw):
    """Exact provider administrative message, never evidence of a football play."""
    return (raw.get('play_type') is None
        and raw.get('desc')=='The status of the game clock was assisted by replay.'
        and not any(raw.get(k) for k in ('passer_player_id','rusher_player_id','receiver_player_id'))
        and all(raw.get(k) is None or _flag(raw.get(k)) is False for k in
            ('pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble',
             'two_point_attempt','touchdown','rush_touchdown','pass_touchdown')))


def _zone(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if not math.isfinite(value) or not 0 <= value <= 100:
        return "unknown"
    return "inside5" if value <= 5 else "six_to_twenty" if value <= 20 else "outside20"


def build_event_evidence(events, *, canonical_ids, source_receipt, cutoff, official_components=()):
    """Derive official-stat opportunity counts, with explicit unknown eligibility.

    ``official_components`` contains optional independent game/team/native-player
    count rows. It verifies a denominator; it never patches source events.
    """
    source = deepcopy(source_receipt)
    if not source.get("snapshot_id") or not source.get("content_sha256"):
        raise ValueError("Event source requires immutable snapshot identity/hash")
    decision = clock(cutoff)
    for key in ("captured_at", "received_at"):
        if not source.get(key) or clock(source[key]) > decision:
            raise ValueError("Event source capture/receipt missing or after decision cutoff")
    if source.get("published_at") and clock(source["published_at"]) > decision:
        raise ValueError("Event source publication after decision cutoff")
    if clock(source["captured_at"]) > clock(source["received_at"]):
        raise ValueError("Event source capture is after receipt")
    events = list(events)
    seen = set(); normalized = []; requests = []; teams = {}; players = {}; canonical_actors = {}
    unknown = {}

    def aggregate(store, key, channel, zone, gtg):
        item = store.setdefault(key, {"counts": dict.fromkeys(CHANNELS, 0),
            "zones": {c: dict.fromkeys(ZONES, 0) for c in CHANNELS},
            "goal_to_go": dict.fromkeys(CHANNELS, 0),
            "goal_to_go_unknown": dict.fromkeys(CHANNELS, 0)})
        item["counts"][channel] += 1
        item["zones"][channel][zone] += 1
        if gtg is True:
            item["goal_to_go"][channel] += 1
        elif gtg is None:
            item["goal_to_go_unknown"][channel] += 1

    for original in events:
        raw = deepcopy(original)
        if any(raw.get(k) is None for k in ("game_id", "play_id", "season", "week", "posteam")):
            raise ValueError("Event lacks native game/play/period/team scope")
        key = (str(raw["game_id"]), str(raw["play_id"]))
        if key in seen:
            raise ValueError("Duplicate native play event")
        seen.add(key)
        season = int(raw["season"]); week = int(raw["week"])
        if (float(raw["season"]) != season or float(raw["week"]) != week
                or not 1920 <= season <= decision.year or not 1 <= week <= 18):
            raise ValueError("Invalid regular-season event period")
        if raw.get("season_type") != "REG":
            raise ValueError("Event season_type must be explicit REG; PRE/POST/unknown not combined")
        event = {"game_id": key[0], "play_id": key[1], "season": int(raw["season"]),
            "week": int(raw["week"]), "season_type": "REG", "team": raw["posteam"], "raw_flags": raw,
            "zone": _zone(raw.get("yardline_100")), "goal_to_go": _flag(raw.get("goal_to_go")),
            "reported_dropback": _flag(raw.get("qb_dropback")),
            "status": "counted", "opportunities": [], "unknown_channels": [], "reasons": []}
        kind = raw.get("play_type")
        no_play = kind == "no_play" or _flag(raw.get("no_play")) is True
        two_point = _flag(raw.get("two_point_attempt"))
        if no_play or two_point is True:
            event.update(status="excluded", reasons=["no_play" if no_play else "two_point_try_separate_from_official_counts"])
        elif _clock_replay_control(raw):
            event.update(status='not_applicable',reasons=['administrative_clock_replay_control'])
        elif kind in {"field_goal", "extra_point", "punt", "kickoff"}:
            event.update(status="not_applicable", reasons=["non-offensive-count play type"])
        elif kind not in {"pass", "run", "qb_spike", "qb_kneel"}:
            event.update(status="unknown", reasons=["unproven offensive/non-offensive play type"])
            event["unknown_channels"] = list(CHANNELS)
        elif two_point is None:
            event.update(status="unknown", reasons=["two_point_attempt missing; official-count eligibility unknown"])
            event["unknown_channels"] = list(CHANNELS)
        else:
            passing = _flag(raw.get("pass_attempt")); rushing = _flag(raw.get("rush_attempt"))
            sack = _flag(raw.get("sack"))
            if passing is None or rushing is None or (passing and sack is None):
                event.update(status="unknown", reasons=["required official-count flag missing"])
                # All channels declined by this ambiguous event need coverage,
                # including a positive flag withheld due to another conflict.
                if passing is not False:
                    event["unknown_channels"].extend(["pass_attempts", "targets"])
                if rushing is not False:
                    event["unknown_channels"].append("rush_attempts")
            elif (passing and rushing) or (rushing and sack is True):
                event.update(status="unknown", reasons=["conflicting pass/rush opportunity flags"])
                event["unknown_channels"] = list(CHANNELS)
            else:
                channels = []
                if passing and not sack:
                    spike = _flag(raw.get("qb_spike")) is True
                    channels.append(("pass_attempts", "passer_player_id", "spike" if spike else "pass"))
                    if raw.get("receiver_player_id") and not spike:
                        channels.append(("targets", "receiver_player_id", "target"))
                    elif not spike or raw.get("receiver_player_id"):
                        event["status"] = "partial"
                        event["unknown_channels"].append("targets")
                        event["reasons"].append("receiver attribution absent or conflicts with spike; no-target pass not established")
                if rushing:
                    kneel = _flag(raw.get("qb_kneel")); scramble = _flag(raw.get("qb_scramble"))
                    subtype = "kneel" if kneel is True else "scramble" if scramble is True else "designed_or_other_rush" if kneel is False and scramble is False else "rush_subtype_unknown"
                    channels.append(("rush_attempts", "rusher_player_id", subtype))
                if sack:
                    event["reasons"].append("sack is a dropback, not an official pass attempt")
                for channel, id_field, subtype in channels:
                    native = raw.get(id_field)
                    canonical = canonical_ids.get(str(native)) if native is not None else None
                    if canonical is not None:
                        try:
                            canonical = str(UUID(str(canonical)))
                        except (TypeError, ValueError, AttributeError) as exc:
                            raise ValueError("Canonical player identity must be UUID") from exc
                        identity = (str(native), raw["posteam"])
                        if canonical_actors.setdefault((key[0], canonical), identity) != identity:
                            raise ValueError("Ambiguous canonical actor/native/team cardinality in game")
                    opportunity = {"channel": channel, "subtype": subtype,
                        "source_player_id": str(native) if native is not None else None,
                        "player_master_id": str(canonical) if canonical is not None else None}
                    event["opportunities"].append(opportunity)
                    team_key = (key[0], raw["posteam"])
                    aggregate(teams, team_key, channel, event["zone"], event["goal_to_go"])
                    player_key = (*team_key, opportunity["source_player_id"], opportunity["player_master_id"])
                    aggregate(players, player_key, channel, event["zone"], event["goal_to_go"])
                    if canonical is None:
                        requests.append({"game_id": key[0], "play_id": key[1], "team": raw["posteam"],
                            "source_player_id": opportunity["source_player_id"], "channel": channel,
                            "reason": "canonical identity unresolved; retain in team universe"})
        if event["unknown_channels"]:
            missing = unknown.setdefault((key[0], raw["posteam"]), dict.fromkeys(CHANNELS, 0))
            for channel in event["unknown_channels"]:
                missing[channel] += 1
        normalized.append(event)
    team_rows = [{"game_id": g, "team": t, **value} for (g, t), value in sorted(teams.items())]
    player_rows = [{"game_id": g, "team": t, "source_player_id": n, "player_master_id": p, **value}
                   for (g, t, n, p), value in sorted(players.items(), key=lambda pair: str(pair[0]))]
    for key, incomplete in unknown.items():
        if key not in teams:
            team_rows.append({"game_id": key[0], "team": key[1],
                "counts": dict.fromkeys(CHANNELS, 0),
                "zones": {c: dict.fromkeys(ZONES, 0) for c in CHANNELS},
                "goal_to_go": dict.fromkeys(CHANNELS, 0), "goal_to_go_unknown": dict.fromkeys(CHANNELS, 0)})
    for row in team_rows + player_rows:
        missing = unknown.get((row["game_id"], row["team"]), dict.fromkeys(CHANNELS, 0))
        row["unknown_eligibility_events"] = dict(missing)
        row["counted_lower_bound"] = dict(row["counts"])
        # Conservative player coverage inherits team event gaps: no false exact
        # zero or official denominator when the source eligibility is incomplete.
        row["counts"] = {c: None if missing[c] else row["counts"][c] for c in CHANNELS}
        row["channel_coverage"] = {c: "complete" if not missing[c] else
            "partial" if row["counted_lower_bound"][c] else "unknown" for c in CHANNELS}
        row["zone_partition_scope"] = "counted_lower_bound; exact only when channel eligibility is complete"
    reconciliation = []
    for official in official_components:
        key = (str(official["game_id"]), official["team"], str(official["source_player_id"]))
        matches = [p for p in player_rows if (p["game_id"], p["team"], p["source_player_id"]) == key]
        for channel in CHANNELS:
            if channel not in official or official[channel] is None:
                continue
            observed = matches[0]["counts"][channel] if len(matches) == 1 else None
            reconciliation.append({"game_id": key[0], "team": key[1], "source_player_id": key[2],
                "channel": channel, "official": official[channel], "derived": observed,
                "official_source_id": official.get("source_id"),
                "official_imported_at": official.get("imported_at"),
                "status": "matched" if observed == official[channel] else "unverified_or_mismatch"})
    result = {"version": VERSION, "status": "derived_descriptive_only", "source": source,
        "producer_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "decision_cutoff_at": decision.isoformat(),
        "event_rows_sha256": hashlib.sha256(json.dumps(events, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        "events": normalized, "teams": team_rows, "players": player_rows,
        "identity_review_requests": requests, "official_reconciliation": reconciliation,
        "coverage": {status: sum(e["status"] == status for e in normalized)
                     for status in ("counted", "partial", "unknown", "excluded", "not_applicable")},
        "semantics": "Zone counts partition each channel; goal-to-go overlaps. Pass and target are linked perspectives, never additive offense budgets.",
        "limitations": ["descriptive counts, not forecasts; unknown eligibility is not zero",
            "source receive cutoff is not original historical pregame availability",
            "source verification marker is caller assertion at pure boundary; operational intake must verify SourceSnapshot artifact bytes",
            "caller persists returned unresolved identity requests through existing review queue before ingest completion"]}
    result["sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return result
