"""Capture official football evidence; resolve by team + position + canonical alias.

No live writes. Each capture is immutable. Publication and retrieval clocks
remain separate; dynamic pages are observed now, never backdated.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re

import requests
from sqlalchemy import text
from backend.app.db import engine
from scripts.run_showdown_qb_policy_experiment import read, write


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.headings = [], []
        self.heading = self.cell = self.row = self.table = None
        self.section = ""

    def handle_starttag(self, tag, attrs):
        if tag in {"h2", "h3", "h4"}:
            self.heading = []
        if tag == "table":
            self.table = {"section": self.section, "rows": []}
        if tag == "tr" and self.table is not None:
            self.row = []
        if tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.heading is not None:
            self.heading.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"h2", "h3", "h4"} and self.heading is not None:
            self.section = " ".join("".join(self.heading).split())
            self.headings.append(self.section)
            self.heading = None
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.table["rows"].append(self.row)
            self.row = None
        if tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def normalized(value):
    value = re.sub(r"[^a-z0-9 ]", "", str(value).lower())
    return " ".join(w for w in value.split() if w not in {"jr", "sr", "ii", "iii", "iv"})


def position(value):
    return str(value).split("/")[0].upper()


def resolve_identity(index, team, pos, name):
    """Only a unique team/position/canonical-alias key can resolve a UUID."""
    candidates = index.get((team, position(pos), normalized(name)), set())
    return next(iter(candidates)) if len(candidates) == 1 else None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    args = p.parse_args()
    directory = args.directory
    config = read(directory / "source_config.json")
    freeze = read(directory / "current_before.json")
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        aliases = [dict(r) for r in conn.execute(text("SELECT player_master_id::TEXT, alias_name FROM public.player_alias WHERE player_master_id IN (SELECT player_master_id FROM public.curated_salary WHERE season=:s AND week=:w AND UPPER(slate)=:slate)"),
            {"s": freeze["season"], "w": freeze["week"], "slate": freeze["slate"]}).mappings()]
    names = {}
    for r in freeze["player_pool"]:
        key = (r["player_team"], r["position"], normalized(r["name"]))
        names.setdefault(key, set()).add(r["player_id"])
    by_id = {r["player_id"]: r for r in freeze["player_pool"]}
    for alias in aliases:
        r = by_id.get(alias["player_master_id"])
        if r and alias["alias_name"]:
            names.setdefault((r["player_team"], r["position"], normalized(alias["alias_name"])), set()).add(r["player_id"])
    observations, facts, unresolved = [], {}, []
    for source in config:
        path = directory / (source["id"] + ".html")
        if path.exists():
            raise ValueError(f"Use a fresh capture directory: {path}")
        response = requests.get(source["url"], timeout=30)
        response.raise_for_status()
        observed = datetime.now(UTC).isoformat()
        path.write_text(response.text)
        parser = Tables(); parser.feed(response.text)
        observations.append(dict(**source, observed_at=observed, publication_at=None, tables=parser.tables))
        def match(name, pos):
            pid = resolve_identity(names, source["team"], pos, name)
            if pid is not None:
                item = facts.setdefault(pid, {"source_uris": [], "identity_match": "team_position_normalized_canonical_alias", "observations": []})
                item["source_uris"].append(source["url"])
                item["observations"].append(dict(source_uri=source["url"], observed_at=observed, publication_at=None))
                return item
            unresolved.append(dict(team=source["team"], name=name, position=pos, source=source["url"]))
            return None
        for table in parser.tables:
            data = table["rows"]
            if not data:
                continue
            header = data[0]
            if source["kind"] == "roster" and "Player" in header and "Pos" in header:
                section = table["section"].lower()
                status = "PS" if "practice" in section else "PUP" if "physically" in section else "NFI" if "non-football" in section else "SUSP" if "suspend" in section else "IR" if "injured" in section else "ACT" if section == "active" else None
                for row in data[1:]:
                    if len(row) != len(header): continue
                    item = match(row[0], row[header.index("Pos")])
                    if item is not None and status: item["roster_status"] = status
            elif source["kind"] == "depth" and header[0] == "Position" and len(header) > 2:
                for row in data[1:]:
                    if row[0] not in {"QB", "RB", "WR", "TE", "K"}: continue
                    for rank, name in enumerate(row[1:], 1):
                        if not name: continue
                        item = match(name, row[0])
                        if item is not None:
                            depth = "expected_starter" if rank == 1 else "expected_backup"
                            if item.get("expected_depth_role") != "expected_starter": item["expected_depth_role"] = depth
                            item["starter_evidence"] = f"Official unofficial chart: {row[0]} rank {rank}; {source['url']}"
                            if row[0] == "K": item["kicker_role"] = "primary_kicker" if rank == 1 else "backup_kicker"
            elif source["kind"] == "injury" and "Game Status" in header:
                for row in data[1:]:
                    if len(row) != len(header): continue
                    item = match(row[1], row[0])
                    if item is not None:
                        item["injury_status"] = row[header.index("Game Status")].upper()
                        item["practice_participation"] = row[-2]
                        item["practice_observed_at"] = observed
    write(directory / "official_observations.json", observations)
    write(directory / "identity_review.json", unresolved)
    write(directory / "resolved_source_facts.json", facts)
    print({"captured_sources": len(observations), "resolved_pool_players": len(facts), "unmatched_source_rows": len(unresolved)})


if __name__ == "__main__": main()
