"""Read-only capture of the requested historical optimizer, never regeneration.

Existing files must match byte-for-byte; no frozen evidence is overwritten.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path

from scripts import audit_showdown_selection_diversity as audit


def persist_same(path, value):
    encoded = json.dumps(value, default=str, indent=2) + "\n"
    if path.exists():
        if path.read_text() != encoded:
            raise ValueError(f"Existing frozen export differs: {path}; preserve it and investigate")
    else:
        path.write_text(encoded)


def main():
    from backend.app.db import engine
    from backend.app.product_services.ai_showdown_packet import build_retrospective_packet
    from sqlalchemy import text
    audit.OUT.mkdir(parents=True, exist_ok=True)
    with engine.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        run_id = audit.RUNS[2]
        r = c.execute(text("""SELECT optimizer_run_id,season,week,slate_id,strategy,status,contest_format,
            created_at,data_cutoff_at,projection_run_id,constraint_config_json
            FROM target.optimizer_run WHERE optimizer_run_id=:id"""), {"id": run_id}).mappings().one()
        source = dict(r)
        source["params"] = source.pop("constraint_config_json")
        source["job_id"] = str(source.pop("optimizer_run_id"))
        source["slate"] = source.pop("slate_id")
        lids = c.execute(text("SELECT lineup_id FROM target.lineup WHERE optimizer_run_id=:id ORDER BY lineup_number"), {"id":run_id}).scalars().all()
        source["results"] = []
        for lid in lids:
            players = c.execute(text("SELECT slot_index,roster_position,player_json FROM target.lineup_player WHERE lineup_id=:id ORDER BY slot_index"), {"id":lid}).mappings().all()
            source["results"].append([{**p["player_json"], "lineup_slot_index":p["slot_index"], "roster_position":p["roster_position"]} for p in players])
        source["player_pool"] = source["params"].get("strategy_runtime",{}).get("player_pool")
        source_path = audit.OUT / f"{run_id}-source.json"
        persist_same(source_path,source)
        packet_path = audit.OUT / "week5_packet.json"
        if not packet_path.exists():
            packet = build_retrospective_packet(audit.read(source_path),ai_requested_entries=2)
            audit.write(packet_path,packet)
        chronology = [dict(r) for r in c.execute(text("""SELECT optimizer_run_id,min(created_at) AS first_lineup_saved_at,
            max(created_at) AS last_lineup_saved_at FROM target.lineup WHERE optimizer_run_id=ANY(:ids) GROUP BY optimizer_run_id"""), {"ids":audit.RUNS}).mappings()]
        # Query ordering is immaterial; existing evidence retains its original order.
        chron_path = audit.OUT / "saved_lineup_chronology.json"
        if chron_path.exists():
            current = json.loads(json.dumps(chronology,default=str))
            if sorted(current,key=lambda x:x["optimizer_run_id"]) != sorted(audit.read(chron_path),key=lambda x:x["optimizer_run_id"]):
                raise ValueError("Saved lineup chronology changed")
        else:
            persist_same(chron_path,chronology)
    print(json.dumps({"source_sha256":audit.file_hash(source_path),"packet_sha256":audit.file_hash(packet_path),"read_only":True}))


if __name__ == "__main__":
    main()
