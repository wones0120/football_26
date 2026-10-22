import json,hashlib
from pathlib import Path
from collections import Counter
from backend.app.product_services.player_role_features import build_player_role_features
R=Path('research/player_role_features_20261020/v1');p=Path('research/opportunity_component_response_20261019/v1/fullshape_retry_prepare_job.json');raw=p.read_bytes();job=json.loads(raw);source=job['result'];rows=source['source_manifest']['availability']
actors=[dict(player_master_id=r['player_master_id'],team=r['team'],position=r['position'],kickoff_at='2026-10-20T00:15:00+00:00') for r in rows];facts=[f for r in rows for f in r['evidence_json'].get('source_facts',[])]
r=build_player_role_features(actors,facts,season=2026,week=6,cutoff=source['data_cutoff_at'])
# The preserved source is a salary-scoped context, NOT a full team roster.
# Exact team personnel counts must consequently remain unknown.
known=Counter(m for a in r['players'] for m,v in a['metrics'].items() if v['value'] is not None)
team_known=Counter(m for a in r['teams'] for m,v in a['metrics'].items() if v['value'] is not None)
assert all(t['metrics'][m]['value'] is None for t in r['teams'] for m in ('G18-M03','G18-M04','G18-M05','G18-M06','G18-M07'))
summary=dict(status='actual_immutable_context_boundary_checked_not_full_feature_coverage',source_ref=dict(path=str(p.resolve()),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw)),original_source_cutoff=source['data_cutoff_at'],derived_postlock=True,players=len(r['players']),facts=len(facts),player_known=dict(known),team_known=dict(team_known),team_roster_complete=False,source_gaps={'G17-M02':'No dated practice facts in canonical source manifest','G17-M05':'No explicit scoped numeric depth_position facts in source manifest','G17-M10':'No sourced workload_restriction facts in source manifest','G18-M03_M07':'Salary scope is not a full-team roster; exact personnel counts remain unknown'},semantic_measurements_sha256=r['semantic_measurements_sha256'],model_consumed=False,optimizer_consumed=False)
(R/'actual_source_coverage.json').write_text(json.dumps(summary,indent=2));(R/'actual_feature_output.json').write_text(json.dumps(r,sort_keys=True,separators=(',',':')));print(json.dumps(summary))
