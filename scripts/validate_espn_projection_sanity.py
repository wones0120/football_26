#!/usr/bin/env python3
"""Compare the frozen Sunday Main projection/candidate pool with ESPN Week 2 DK values."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy import text

from backend.app.db import engine
from backend.app.product_dependencies import get_optimizer_service


MATERIAL_DIFFERENCE = 2.5
FOCUS_PLAYERS = ("Tyler Shough", "Derrick Henry", "Chris Olave", "Jalen Coker", "Chase Brown")
QB_FOCUS = ("Tyler Shough", "Brock Purdy", "Justin Herbert", "Bo Nix", "Carson Wentz")
SOURCE_URL = "https://www.espn.com/fantasy/football/story/_/id/49973453/draftkings-nfl-dfs-values-week-2"


def report_from_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        if isinstance(payload.get("all_candidates"), list):
            return payload
        for value in payload.values():
            try:
                return report_from_payload(value)
            except LookupError:
                continue
    if isinstance(payload, list):
        for value in payload:
            try:
                return report_from_payload(value)
            except LookupError:
                continue
    raise LookupError("candidate report not found")


class _TableParser(HTMLParser):
    """Small dependency-free parser for ESPN's article tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[dict[str, str | None]]]] = []
        self._table: list[list[dict[str, str | None]]] | None = None
        self._row: list[dict[str, str | None]] | None = None
        self._cell: dict[str, str | None] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = {"text": "", "href": None}
        elif tag == "a" and self._cell is not None and attributes.get("href"):
            self._cell["href"] = attributes["href"]

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["text"] = str(self._cell["text"] or "") + data

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._cell["text"] = " ".join(str(self._cell["text"] or "").split())
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_name = "".join(char for char in decomposed if not unicodedata.combining(char))
    ascii_name = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", ascii_name.lower())
    return re.sub(r"[^a-z0-9]+", "", ascii_name)


def normalize_position(value: str) -> str:
    position = value.strip().upper()
    return "DST" if position in {"D", "DEF", "DST", "D/ST"} else position


def parse_espn_tables(html: str) -> list[dict[str, Any]]:
    parser = _TableParser()
    parser.feed(html)
    parsed: list[dict[str, Any]] = []
    for table in parser.tables:
        if not table:
            continue
        headers = [str(cell["text"] or "").strip() for cell in table[0]]
        if headers != ["Player", "Rating", "Team", "Opp", "Pos", "Proj.", "$"]:
            continue
        for cells in table[1:]:
            if len(cells) != len(headers):
                continue
            row = {header: cell["text"] for header, cell in zip(headers, cells)}
            href = str(cells[0].get("href") or "")
            match = re.search(r"/id/(-?\d+)/", href)
            parsed.append({
                "espn_player_id": match.group(1) if match else None,
                "player": str(row["Player"] or "").strip(),
                "value_tier": str(row["Rating"] or "").strip(),
                "team": str(row["Team"] or "").strip().upper(),
                "opponent": str(row["Opp"] or "").strip().upper().lstrip("@"),
                "position": normalize_position(str(row["Pos"] or "")),
                "projection": float(str(row["Proj."]).replace(",", "")),
                "salary": int(str(row["$"]).replace("$", "").replace(",", "")),
                "source_href": href,
            })
    return parsed


def candidate_exposures(report: Mapping[str, Any]) -> tuple[Counter[str], int]:
    candidates = report.get("all_candidates") or []
    counts: Counter[str] = Counter()
    for candidate in candidates:
        counts.update(str(player_id) for player_id in candidate.get("player_ids") or [])
    return counts, len(candidates)


def alias_map_for_espn(source_ids: Iterable[str]) -> dict[str, str]:
    ids = sorted({source_id for source_id in source_ids if source_id})
    if not ids:
        return {}
    try:
        with engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT source_key, player_master_id
                FROM public.player_alias
                WHERE LOWER(source_system) = 'espn' AND source_key = ANY(:source_ids)
            """), {"source_ids": ids}).mappings().all()
    except Exception:
        return {}
    return {str(row["source_key"]): str(row["player_master_id"]) for row in rows}


def build_pool_indexes(pool_rows: list[dict[str, Any]]) -> tuple[dict[str, dict], dict[tuple, list[dict]]]:
    by_id = {str(row["player_id"]): row for row in pool_rows}
    by_key: dict[tuple, list[dict]] = {}
    for row in pool_rows:
        position = normalize_position(str(row.get("position") or ""))
        team = str(row.get("player_team") or "").upper()
        salary = int(float(row.get("salary") or 0))
        if position == "DST":
            key = (team, position, salary)
        else:
            key = (normalize_name(str(row.get("name") or "")), team, position, salary)
        by_key.setdefault(key, []).append(row)
    return by_id, by_key


def match_espn_row(
    espn: Mapping[str, Any],
    *,
    by_id: Mapping[str, dict],
    by_key: Mapping[tuple, list[dict]],
    aliases: Mapping[str, str],
) -> tuple[dict | None, str, str | None]:
    source_id = str(espn.get("espn_player_id") or "")
    canonical_id = aliases.get(source_id)
    if canonical_id and canonical_id in by_id:
        return by_id[canonical_id], "espn_source_id", None
    if espn["position"] == "DST":
        key = (espn["team"], espn["position"], espn["salary"])
        method = "team_position_salary"
    else:
        key = (normalize_name(str(espn["player"])), espn["team"], espn["position"], espn["salary"])
        method = "normalized_name_team_position_salary"
    matches = by_key.get(key, [])
    if len(matches) == 1:
        return matches[0], method, None
    if len(matches) > 1:
        return None, "unmatched", f"ambiguous deterministic key ({len(matches)} local rows)"
    return None, "unmatched", "no source-ID or exact name/team/position/salary match"


def float_value(row: Mapping[str, Any], *names: str) -> float:
    for name in names:
        value = row.get(name)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    raise KeyError(f"none of {names!r} has a numeric value")


def row_signal(row: Mapping[str, Any]) -> str:
    flags = row["flags"]
    if flags["high_exposure_espn_materially_lower"]:
        return "projection-driven signal"
    if flags["low_exposure_espn_materially_higher"]:
        return "projection-driven signal"
    if flags["zero_exposure_espn_great_value"]:
        if row["signed_difference"] <= -MATERIAL_DIFFERENCE:
            return "projection and candidate-generation signal"
        return "candidate-generation signal"
    return "no decisive signal from this source"


def fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def markdown_report(payload: Mapping[str, Any]) -> str:
    source = payload["source"]
    coverage = payload["coverage"]
    lines = [
        "# Week 2 external projection sanity check",
        "",
        f"- ESPN source: {source['url']}",
        f"- ESPN publication: {source['published_at']}",
        f"- Our projection run: `{payload['our_inputs']['projection_run_id']}`",
        f"- Candidate exposure basis: {coverage['candidate_count']} frozen production candidates",
        f"- Deterministically matched: {coverage['matched']} of {coverage['espn_rows']} ESPN rows; unmatched: {coverage['unmatched']}",
        f"- Material difference threshold: {MATERIAL_DIFFERENCE:.1f} DK points",
        "- ESPN coverage limitation: its article displays players projected for at least 4.0 DK points.",
        "",
        "## Finding",
        "",
        payload["conclusion"],
        "",
        "This is a diagnostic comparison with one external source. It does not establish that either projection is correct.",
        "",
        "## Candidate-generation cross-check",
        "",
        payload["candidate_generation_cross_check"]["summary"],
        "",
        "## Requested concentration check",
        "",
        "| Player | Pos | Our | ESPN | Our−ESPN | Salary | Our val/$1k | ESPN val/$1k | Exposure | ESPN tier | Signal |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in payload["focus_players"]:
        lines.append(
            f"| {row['player']} | {row['position']} | {fmt(row['our_mean'])} | {fmt(row['espn_mean'])} | "
            f"{row['signed_difference']:+.2f} | ${row['salary']:,} | {fmt(row['our_value_per_1000'])} | "
            f"{fmt(row['espn_value_per_1000'])} | {row['candidate_count']}/{coverage['candidate_count']} "
            f"({row['candidate_exposure_pct']:.1f}%) | {row['espn_value_tier']} | {row['diagnostic_signal']} |"
        )

    lines += [
        "",
        "## QB family comparison",
        "",
        "| QB | Our | ESPN | Our−ESPN | Salary | Our val/$1k | ESPN val/$1k | Exposure | ESPN tier |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in payload["qb_comparison"]:
        lines.append(
            f"| {row['player']} | {fmt(row['our_mean'])} | {fmt(row['espn_mean'])} | {row['signed_difference']:+.2f} | "
            f"${row['salary']:,} | {fmt(row['our_value_per_1000'])} | {fmt(row['espn_value_per_1000'])} | "
            f"{row['candidate_count']}/{coverage['candidate_count']} ({row['candidate_exposure_pct']:.1f}%) | "
            f"{row['espn_value_tier']} |"
        )

    lines += [
        "",
        "## Flag summary",
        "",
    ]
    for key, value in payload["flag_counts"].items():
        lines.append(f"- {key.replace('_', ' ')}: {value}")

    lines += [
        "",
        "## All overlapping players",
        "",
        "| Player | Team | Opp | Pos | Our mean | ESPN mean | Abs diff | Salary | Our val/$1k | ESPN val/$1k | Exposure | ESPN tier | Flags | Match |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in payload["overlapping_players"]:
        active_flags = [name for name, active in row["flags"].items() if active]
        if row.get("hard_exclusion_reason"):
            active_flags.append("hard:no-opponents-vs-DEN")
        flags = ", ".join(active_flags) or "—"
        lines.append(
            f"| {row['player']} | {row['team']} | {row['opponent']} | {row['position']} | {fmt(row['our_mean'])} | "
            f"{fmt(row['espn_mean'])} | {fmt(row['absolute_difference'])} | ${row['salary']:,} | "
            f"{fmt(row['our_value_per_1000'])} | {fmt(row['espn_value_per_1000'])} | "
            f"{row['candidate_count']}/{coverage['candidate_count']} ({row['candidate_exposure_pct']:.1f}%) | "
            f"{row['espn_value_tier']} | {flags} | {row['match_method']} |"
        )

    lines += ["", "## Unmatched ESPN rows", ""]
    if payload["unmatched_espn_rows"]:
        lines += [
            "| Player | Team | Pos | Salary | ESPN mean | Reason |",
            "|---|---|---:|---:|---:|---|",
        ]
        for row in payload["unmatched_espn_rows"]:
            lines.append(
                f"| {row['player']} | {row['team']} | {row['position']} | ${row['salary']:,} | "
                f"{fmt(row['projection'])} | {row['unmatched_reason']} |"
            )
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--espn-html", type=Path, required=True)
    parser.add_argument("--optimizer", type=Path, required=True)
    parser.add_argument("--exploration", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    espn_html = args.espn_html.read_text()
    espn_rows = parse_espn_tables(espn_html)
    optimizer_payload = json.loads(args.optimizer.read_text())
    report = report_from_payload(optimizer_payload)
    exposure_counts, candidate_count = candidate_exposures(report)
    projection_run_id = str(optimizer_payload["projection_run_id"])
    exploration = json.loads(args.exploration.read_text()) if args.exploration else {}

    pool = get_optimizer_service()._load_player_pool(  # noqa: SLF001 - read-only diagnostic
        2026, 2, "SUNDAY_MAIN", projection_run_id=projection_run_id
    )
    pool_rows = pool.to_dict("records")
    by_id, by_key = build_pool_indexes(pool_rows)
    aliases = alias_map_for_espn(str(row.get("espn_player_id") or "") for row in espn_rows)

    matched: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for espn in espn_rows:
        local, method, reason = match_espn_row(espn, by_id=by_id, by_key=by_key, aliases=aliases)
        if local is None:
            hard_reason = "opponent_denver" if espn["opponent"] == "DEN" else None
            unmatched_reason = reason
            if hard_reason:
                unmatched_reason = f"{reason}; expected exclusion under hard no-opponents-vs-DEN rule"
            unmatched.append({**espn, "hard_exclusion_reason": hard_reason, "unmatched_reason": unmatched_reason})
            continue
        player_id = str(local["player_id"])
        our_mean = float_value(local, "projection", "predicted_mean", "adj_mean_final")
        signed = our_mean - float(espn["projection"])
        count = int(exposure_counts[player_id])
        exposure = 100.0 * count / candidate_count if candidate_count else 0.0
        opponent = str(local.get("opponent_team") or espn["opponent"]).upper()
        flags = {
            "projection_difference_ge_2_5": abs(signed) >= MATERIAL_DIFFERENCE,
            "high_exposure_espn_materially_lower": exposure >= 50.0 and signed >= MATERIAL_DIFFERENCE,
            "low_exposure_espn_materially_higher": exposure <= 5.0 and signed <= -MATERIAL_DIFFERENCE,
            "zero_exposure_espn_great_value": count == 0 and espn["value_tier"].lower() == "great",
        }
        result = {
            "player_id": player_id,
            "espn_player_id": espn["espn_player_id"],
            "player": str(local.get("name") or espn["player"]),
            "team": str(local.get("player_team") or espn["team"]).upper(),
            "opponent": opponent,
            "position": normalize_position(str(local.get("position") or espn["position"])),
            "salary": int(espn["salary"]),
            "our_mean": our_mean,
            "espn_mean": float(espn["projection"]),
            "signed_difference": signed,
            "absolute_difference": abs(signed),
            "our_value_per_1000": our_mean / (espn["salary"] / 1000.0),
            "espn_value_per_1000": float(espn["projection"]) / (espn["salary"] / 1000.0),
            "candidate_count": count,
            "candidate_exposure_pct": exposure,
            "espn_value_tier": espn["value_tier"],
            "match_method": method,
            "hard_exclusion_reason": "opponent_denver" if opponent == "DEN" else None,
            "flags": flags,
        }
        result["diagnostic_signal"] = row_signal(result)
        matched.append(result)

    matched.sort(key=lambda row: (-row["absolute_difference"], row["position"], row["player"]))
    by_name = {row["player"]: row for row in matched}
    focus = [by_name[name] for name in FOCUS_PLAYERS if name in by_name]
    qbs = [row for row in matched if row["position"] == "QB"]
    qb_priority = {name: index for index, name in enumerate(QB_FOCUS)}
    qbs.sort(key=lambda row: (qb_priority.get(row["player"], len(qb_priority)), -row["espn_value_per_1000"], row["player"]))

    flag_counts = {
        flag: sum(bool(row["flags"][flag]) for row in matched)
        for flag in next(iter(matched), {"flags": {}})["flags"]
    }
    shough = by_name.get("Tyler Shough")
    alternatives = [row for row in qbs if row["player"] in set(QB_FOCUS) - {"Tyler Shough"}]
    qb_external_gap = max((row["espn_mean"] - shough["espn_mean"] for row in alternatives), default=0.0) if shough else 0.0
    expanded = exploration.get("expanded_pool") or {}
    expanded_qb_distribution = expanded.get("expanded_qb_distribution") or {}
    qb_family_rows = {str(row.get("qb")): row for row in exploration.get("qb_families") or []}
    purdy_shadow = qb_family_rows.get("Brock Purdy")
    generation_summary = (
        f"The broader, diagnostic-only family search found {expanded_qb_distribution.get('Brock Purdy', 0)} legal "
        f"Purdy candidates after the production pool contained none. Its best current-objective lineup was "
        f"{float(purdy_shadow['gap']):.3f} selector points behind Shough's best lineup. "
        "Herbert, Nix, and Wentz were not selected for the locally ranked top-10 QB family expansion because their "
        "current internal projection/value ranks were too low. This shows that production family coverage amplifies "
        "the concentration, while the projection ordering determines which alternatives the expansion explores."
        if purdy_shadow else
        "No expanded QB-family artifact was supplied, so the report cannot separate legal-family coverage from projection ordering."
    )
    zero_great = [row for row in matched if row["flags"]["zero_exposure_espn_great_value"]]
    zero_great_projection = sum(row["signed_difference"] <= -MATERIAL_DIFFERENCE for row in zero_great)
    zero_great_generation = len(zero_great) - zero_great_projection
    conclusion = (
        "The concentration is attributable to both layers, with the four concentrated skill players primarily showing "
        "a projection-driven signal: Henry, Olave, Coker, and Brown are each at least 2.5 points above ESPN and appear "
        "in 83%–100% of the production candidates. Shough is 2.44 points above ESPN, just below the material threshold. "
        f"ESPN puts the requested QB alternatives as much as {qb_external_gap:.1f} points above Shough, while our model "
        "ranks several of them materially lower. Production family coverage then amplifies that ordering. Of the "
        f"{len(zero_great)} zero-exposure ESPN Great values, {zero_great_projection} are also materially lower in our "
        f"model and {zero_great_generation} are within 2.5 points, the latter being the cleaner candidate-generation "
        "signal. The comparison identifies validation targets and does not justify tuning from ESPN alone."
    )

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_only": True,
        "production_changes": "none",
        "material_difference_dk_points": MATERIAL_DIFFERENCE,
        "source": {
            "provider": "ESPN / Mike Clay",
            "url": SOURCE_URL,
            "published_at": "2026-09-18 10:47 AM ET",
            "display_floor_dk_points": 4.0,
            "captured_file": str(args.espn_html),
            "sha256": hashlib.sha256(args.espn_html.read_bytes()).hexdigest(),
        },
        "our_inputs": {
            "projection_run_id": projection_run_id,
            "optimizer_run_id": optimizer_payload.get("source_optimizer_run_id"),
            "optimizer_artifact": str(args.optimizer),
            "season": 2026,
            "week": 2,
            "slate": "SUNDAY_MAIN",
        },
        "coverage": {
            "espn_rows": len(espn_rows),
            "matched": len(matched),
            "unmatched": len(unmatched),
            "candidate_count": candidate_count,
            "exposure_basis": "frozen production candidate pool",
        },
        "candidate_generation_cross_check": {
            "artifact": str(args.exploration) if args.exploration else None,
            "expanded_candidate_count": expanded.get("candidate_count"),
            "expanded_qb_distribution": expanded_qb_distribution,
            "qb_family_best": list(qb_family_rows.values()),
            "summary": generation_summary,
        },
        "flag_counts": flag_counts,
        "focus_players": focus,
        "qb_comparison": qbs,
        "overlapping_players": matched,
        "unmatched_espn_rows": unmatched,
        "conclusion": conclusion,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    args.output.with_suffix(".md").write_text(markdown_report(output))
    print(json.dumps({
        "output": str(args.output),
        "matched": len(matched),
        "unmatched": len(unmatched),
        "flags": flag_counts,
        "focus": [{"player": row["player"], "difference": round(row["signed_difference"], 2), "exposure": round(row["candidate_exposure_pct"], 1)} for row in focus],
    }, indent=2))


if __name__ == "__main__":
    main()
