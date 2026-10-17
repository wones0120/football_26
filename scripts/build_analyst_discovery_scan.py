"""Freeze an all-game discovery investigation input from saved sources, without solves."""
import argparse,json
from pathlib import Path
from backend.app.product_services.analyst_discovery import scan
from backend.app.product_services.analyst_packets import validate
from backend.app.product_services.analyst_shadow import digest

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--packet',type=Path,required=True);parser.add_argument('--snapshot',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    packet=json.loads(args.packet.read_text());errors=validate(packet)
    if errors:raise ValueError('; '.join(errors))
    snapshot=json.loads(args.snapshot.read_text());report=scan(packet,snapshot['pool']);report.update(scan_snapshot_sha256=snapshot['sha256'],projection_run_id=snapshot['projection_run_id'],source_packet_sha256=digest(packet),assumption_manifest_sha256=snapshot['assumption_manifest_sha256'],semantic_handoff='Investigate every game; distinguish these already-present projection/context features from sourced conditional model gaps. Use analyst_discovery_v1 for supported/watchlist/rejected findings. No automatic statistical boost.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.output.exists():
        if json.loads(args.output.read_text())!=report:raise ValueError('Immutable scan output already exists with different content')
    else:args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(f"Scanned {len(report['scanned_games'])} games / {sum(g['scanned_player_count'] for g in report['scanned_games'])} player rows; {len(report['candidate_edges'])} candidate edges; automatic actions none")
if __name__=='__main__':main()
