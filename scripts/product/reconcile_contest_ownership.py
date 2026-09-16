"""Reconcile an archived contest manifest against canonical slate salaries.

Defaults to a dry run. --apply appends identity decisions and refreshes only the
manifest's contest ownership labels; it never changes standings or projections.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from backend.app.product_services.ownership import OwnershipService
from backend.app.product_services.contest_ownership_identity import attach_salary_identities, persist_observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--week', type=int, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    service = OwnershipService()
    destination = args.manifest.parent / 'review'
    destination.mkdir(exist_ok=True)
    summary = []
    for item in json.loads(args.manifest.read_text()):
        archive = Path(item['archive'])
        if hashlib.sha256(archive.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError(f"Archive checksum mismatch: {archive.name}")
        path, source = service._read_standings(archive)
        if service._source_file_info(path)['source_file_id'] != item['source_file_id']:
            raise ValueError(f"Source registry checksum mismatch: {archive.name}")
        rows = service._normalize_standings(source, args.season, args.week, item['slate'], path)
        observations = service._ownership_source_rows(rows)
        observations['contest_id'] = item['contest_id']
        observations['source_file_id'] = item['source_file_id']
        resolved = attach_salary_identities(service.engine, observations)
        labels = service._build_ownership(resolved)
        if args.apply:
            persist_observations(service.engine, resolved)
            with service.engine.begin() as connection:
                connection.execute(text("DELETE FROM dk_ownership WHERE contest_id=:contest_id AND source='contest_standings'"), {'contest_id':item['contest_id']})
                if not labels.empty:
                    labels.to_sql('dk_ownership', connection, if_exists='append', index=False)
        resolved.to_json(destination / f"{item['contest_id']}.json", orient='records', indent=2)
        unresolved = resolved[resolved.resolution_status != 'resolved']
        unresolved.to_json(destination / f"{item['contest_id']}_unresolved.json", orient='records', indent=2)
        summary.append({'contest_id':item['contest_id'], 'applied':args.apply,
                        **resolved.resolution_status.value_counts().to_dict()})
    (destination / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
