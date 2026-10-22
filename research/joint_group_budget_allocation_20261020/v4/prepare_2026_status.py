"""Freeze ALL scheduled2026 rows as coverage/status, not model performance."""
from pathlib import Path
from datetime import datetime,UTC
import hashlib,json
R=Path(__file__).resolve().parent;p=Path('research/readiness_2026_20261020/v1/MANIFEST.json');b=p.read_bytes();source=json.loads(b);rows=[]
for game in source['matchups']:
 for side in game['sides']:
  rows.append(dict(game_id=game['game_id'],week=game['week'],team=side['team'],opponent=side['opponent'],
                   prior_scheduled_games=side['prior_scheduled_games'],prior3_achieved=side['prior3_achieved'],
                   history_status='PENDING_SOURCE_LABEL_GATES'if side['prior3_achieved']else'EXPLICIT_COLDSTART_UNSUPPORTED_UNCHANGED_EXACT3_RECIPE',
                   completion_proven=game['completion_proven_by_reviewed_scoreboard'],
                   completion_status='VERIFIED_REVIEWED_SCOREBOARD'if game['completion_proven_by_reviewed_scoreboard']else'UNASSESSED_FINAL_COMPLETION_NOT_INFERRED_FROM_STATS',
                   joint_label_gate='NOT_CURRENTLY_ADMITTED;PENDING_B_NATIVE_EVENT_PROOF',
                   evaluation_completion_gate='PENDING_SOURCE_ADMISSION'if game['completion_proven_by_reviewed_scoreboard']else'DO_NOT_EVALUATE_UNTIL_PROVEN_COMPLETE',
                   role_replacement_status='UNKNOWN_PENDING_DATED_NATIVE_INJURY_PLUS_SUPPORTED_ROLE_BINDING',
                   prediction_status='NOT_EVALUATED_NO_MODEL_CALL',partial_metric_status='NOT_EVALUATED;SEPARATE_APPROVAL_AND_EXACT_AVAILABLE_LABELS_REQUIRED'))
keyset={(r['game_id'],r['team'])for r in rows};assert len(keyset)==len(rows)
plan=dict(version='2026_joint_mean_all_week_coverage_plan_v1',recorded_at=datetime.now(UTC).isoformat(),readiness_ref=dict(path=str(p.resolve()),sha256=hashlib.sha256(b).hexdigest(),bytes=len(b)),
 architecture_contract_ref='research/joint_mean_generalization_diagnosis_20261020/v1/REPAIR_CONTRACT.json',
 scope='2026priority; freezearchitecture/recipebeforemodelperformanceinspection. Readinesslabelaggregateswereinspected; nooutcome-blind2026claim.',
 policy='Keep EVERY supplied scheduled side includingW1-3 andunknownfinalstatus. No prioryearborrow/padding, current-role outcome eligibility, absentcandidate0fill or silentexclusion.',
 rolling_features='Onlysame3immediatelypriorscheduledgames andnativecapture/vintageevidence; frozen2023TRAINpreprocessors; no2026fitting orstatisticalnormalization.',
 partial_metric_policy='Budget-only/known-candidate exactavailable-label diagnostics requireseparateHighproofadmission; never substitute for jointfullpopulationpromotion or whole2026improvement.',
 prediction_rows=rows,week_coverage=[dict(week=w['week'],scheduled_games=w['scheduled_games'],verified_completed_games=w['completed_status_verified_cached_games'],coldstart_status=w['coldstart_status'],joint_label_census=w['joint_label_census'])for w in source['weeks']],
 metrics={},model_calls=0,fits=0,activation=False)
(R/'2026_EVALUATION_STATUS_PLAN.json').write_text(json.dumps(plan,indent=2)+'\n')
print(json.dumps(dict(scheduled_sides=len(rows),weeks=len(plan['week_coverage']),coldstart_sides=sum(not r['prior3_achieved']for r in rows),currently_joint_admitted=0,model_calls=0)))
