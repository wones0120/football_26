"""Rebuild derived pilot from identified local inputs and fixed web observations."""
from pathlib import Path
from datetime import datetime, UTC
import hashlib
import json

ROOT = Path(__file__).resolve().parent
if (ROOT/'packet.json').exists():
    raise SystemExit('Existing packet is frozen; create a new version directory for a refresh.')
REPO = ROOT.parents[1]
RECOVERY = REPO / 'artifacts/projection_source_readiness_recovery'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def save(name, data):
    (ROOT/name).write_text(json.dumps(data, indent=2) + '\n')

roster = json.loads((RECOVERY/'verified_roster_preview.json').read_text())
verification = json.loads((RECOVERY/'persistence_verification.json').read_text())
run = verification['run']
capture = '2026-10-13T13:51:24Z'
decision = datetime.now(UTC).isoformat()
sea_uri = 'https://www.seahawks.com/news/week-6-injury-report-seahawks-at-broncos'
den_uri = 'https://www.denverbroncos.com/news/injury-report-cb-riley-moss-listed-as-limited-participant-on-initial-practice-report-ahead-of-week-6-game-vs-seahawks'
web = {
 'sea_injury': {'uri': sea_uri, 'observed_at': capture, 'published_display': 'Oct 12, 2026 at 02:10 PM (page timezone not established)', 'facts': ['Monday report was estimated; no practice.', 'Jaxon Smith-Njigba: ankle, limited estimate.', 'Zach Charbonnet: knee, limited estimate, still PUP; coach said return this week unlikely and subject to change.', 'George Holani: full estimate.'], 'extraction_policy': 'Manual structured paraphrase of browser-verified primary report; not raw page snapshot.'},
 'den_injury': {'uri': den_uri, 'observed_at': '2026-10-13T13:52:10Z', 'published_display': 'Oct 12, 2026 at 02:22 PM (page timezone not established)', 'facts': ['Monday report was estimated; no practice.', 'Riley Moss: ribs, limited estimate.', 'Patrick Surtain II and Talanoa Hufanga: ankle, nonparticipant estimates.', 'Tuesday report and Wednesday game statuses planned by team.'], 'extraction_policy': 'Manual structured paraphrase of browser-verified primary report; not raw page snapshot.'},
 'schedule': {'uri':'https://www.denverbroncos.com/schedule/','observed_at':capture,'published_display':None,'facts':['Week 6 SEA at DEN, Thursday October 15, 2026, 6:15 PM MDT.'],'extraction_policy':'Manual schedule observation; no Week 5 results retained.'},
}
sources=[]
for sid, record in web.items():
 save(sid+'_capture.json',record)
 sources.append({'source_id':sid,'uri':record['uri'],'coverage':'verified','published_at':None,'publication_time_note':record['published_display'],'observed_at':record['observed_at'],'available_at':record['observed_at'],'capture_sha256':digest(ROOT/(sid+'_capture.json')),'capture_kind':'structured_browser_observation'})
for sid, name, observed in [('roster','verified_roster_preview.json','2026-10-13T13:18:56.914417+00:00'),('baseline_run','persistence_verification.json','2026-10-13T13:24:50.773525+00:00')]:
 sources.append({'source_id':sid,'uri':str(RECOVERY/name),'coverage':'verified','published_at':None,'observed_at':observed,'available_at':decision,'capture_sha256':digest(RECOVERY/name),'capture_kind':'existing_local_artifact','limitation':'Snapshot observation is independently identified; file availability proven only by this research read.'})
players=[]
selected={'1838dd60-35e8-4018-b307-39cde90e1f03','651d2655-f851-43a2-8c17-28d8905c5818','2b3590c3-0eef-4d4c-a226-fd793d010103','3b32dba2-e153-4396-894e-25ac07319cb7','480d4188-7bf6-4684-b2b5-1d47f93d542a','724bd3c9-3014-4367-9ad8-490dab910139'}
for row in roster['players']:
 pid=row['player_master_id']
 if pid not in selected:continue
 match=row['matches'][0]
 # Compatible unavailable adapter, never fabricates history from current roster.
 evidence={'contract_id':'workload_evidence_v1','player_id':pid,'status':'unavailable','historical':{},'historical_coverage':{},'derived_proxies':{},'explicit_pregame':{},'availability_depth':{'roster_status':match['group']},'existing_assessment':{},'team_volume_proxies':{},'lineage':{'projection_run_id':run['projection_run_id'],'evidence_cutoff_at':'2026-10-13T13:23:47.123653Z','workload_feature_run_id':verification['feature_run_id']},'limitations':['Current feature rows not captured by this pilot; empty groups mean unavailable, not zero.', 'Projection/feature identifiers do not prove per-player workload coverage or source chronology.', 'Roster status is not game availability or expected role.']}
 players.append({'player_master_id':pid,'display_name':row['player_name'],'team':row['team'],'position':row['position'],'game_id':'2026_W06_SEA_DEN','source_native_key':match['source_keys'][0],'identity_source_ids':['roster'],'identity_linkage':'Reused persisted canonical UUID with verified team, normalized position, roster native key; no display-name-only join.','workload_evidence':evidence})
jsn='1838dd60-35e8-4018-b307-39cde90e1f03';char='651d2655-f851-43a2-8c17-28d8905c5818';wil='2b3590c3-0eef-4d4c-a226-fd793d010103';hol='3b32dba2-e153-4396-894e-25ac07319cb7';sam='480d4188-7bf6-4684-b2b5-1d47f93d542a';kupp='724bd3c9-3014-4367-9ad8-490dab910139'
def hypothesis(hid,ids,text,support,contrary,assumptions,implication,unknowns,sids,status='research_only'):
 return {'hypothesis_id':hid,'game_id':'2026_W06_SEA_DEN','formats':['SHOWDOWN'],'player_master_ids':ids,'status':status,'action':'refresh_evidence_only' if status=='actionable_monitor' else 'none','hypothesis':text,'supporting_evidence':support,'contrary_evidence':contrary,'conditional_assumptions':assumptions,'testable_implication':implication,'unknowns':unknowns,'source_ids':sids,'uncertainty':'Unquantified; no calibrated probability or confidence number is available.','numeric_effect_proposal':None,'expires_at':'2026-10-14T18:00:00Z','recheck_triggers':['Next official practice report','Wednesday game designations','Roster activation or new injury','Final inactive list','Any source correction or game/scope change']}
packet={'contract_id':'wones_football_analyst_v1','analyst_name':'Wones Football Analyst','packet_id':'20261013_SEA_DEN_preview_v1','decision_at':decision,'frozen_at':decision,'preview_only':True,'baseline_mutation':False,'user_preferences':[], 'games':[{'game_id':'2026_W06_SEA_DEN','season':2026,'week':6,'teams':['SEA','DEN'],'kickoff_at':'2026-10-16T00:15:00Z','schedule_source_ids':['schedule'],'format_membership':{'SHOWDOWN':'confirmed_in_scope','CLASSIC':'out_of_scope_sunday_main'},'scope_note':'Thursday game; excluded from Sunday Main. No Sunday salary slate membership captured.'}],'sources':sources,'players':players,'baseline_facts':[{'fact_id':'run_metadata','kind':'observed_fact','text':'Recovered local projection run completed with 37 rows; roster context is membership evidence. Per-player predictions/workload values have not been copied into this packet.','source_ids':['baseline_run','roster'],'projection_run_id':run['projection_run_id']},{'fact_id':'reported_status','kind':'observed_fact','text':'Initial Week 6 team injury reporting is an estimated Monday participation report, not final game status.','source_ids':['sea_injury','den_injury']}], 'hypotheses':[
 hypothesis('JSN_availability_watch',[jsn],'Refresh Jaxon Smith-Njigba availability before interpreting SEA receiving constructions.',['Primary Week 6 ankle listing is present.'],['Estimated participation is not an out designation or workload restriction.'],['If later reports change availability, independently obtain role evidence before changing opportunity assumptions.'],'Compare the next official designation with this frozen watch item; separately inspect routes/targets if a role limitation is reported.',['No quantified route restriction, final designation or expected targets.'],['sea_injury','roster'],'actionable_monitor'),
 hypothesis('SEA_backfield_conditional',[char,wil,hol],'Investigate continuity versus an activation-driven change in the SEA backfield.',['Current roster places Charbonnet on PUP.'],['Return remains subject to change; available backups do not prove touch allocation.'],['Only if Charbonnet remains unavailable and current role evidence confirms a lead runner could continuity be supported.'],'Freeze a role/availability branch, then compare actual carries and routes against a separately sourced or calibrated forecast, if obtained.',['No current observed carry-share window, routes, goal-line usage or supported expected-carry allocation.'],['sea_injury','roster']),
 hypothesis('SEA_pass_environment_conditional',[jsn,sam,kupp],'Research whether changed DEN coverage personnel alters the SEA passing scenario.',['Primary DEN report identifies secondary uncertainty.'],['Estimated nonparticipation does not establish absence; JSN availability is unresolved; replacements and assignments unknown.'],['Only if absences are confirmed and current coverage evidence supports the mechanism.'],'If activated as a research branch later, compare passing opportunity/coverage evidence separately from fantasy points.',['No current pressure/coverage tendencies, matchup assignment, calibrated efficiency effect or fresh spread/total.'],['den_injury','sea_injury','roster'])], 'coverage_gaps':['Sunday Main slate-wide briefing not populated; no verified Sunday salary slate captured.','Current matchup tendencies, routes/snaps/carries/targets/red-zone history absent; no old values substituted.','Primary sportsbook search was attempted; no independently timestamped live spread/total captured. Search results alone not promoted to market evidence.','No final game designations/inactives, candidate pool, ownership or salary audit in this pilot.'], 'evaluation_disclosure':'Pilot assembled before this future kickoff. Researchers know historical outcomes; no retrospective outcome-blindness claim. No Week 5 outcome statistics were used as Week 6 forecasts.'}
save('packet.json',packet)
manifest={'manifest_version':1,'contract_id':packet['contract_id'],'packet_id':packet['packet_id'],'created_at':decision,'shared_contract':'workload_evidence_v1','shared_builder_path':'backend/app/product_services/workload_evidence.py','shared_builder_sha256_at_read':digest(REPO/'backend/app/product_services/workload_evidence.py'),'adapter_status':'compatible_unavailable_fixture; no old snapshots backfilled','local_input_hashes':{str(RECOVERY/name):digest(RECOVERY/name) for name in ['verified_roster_preview.json','persistence_verification.json']},'files':{name:digest(ROOT/name) for name in ['packet.json','sea_injury_capture.json','den_injury_capture.json','schedule_capture.json']},'freeze_policy':'New observations require a new packet ID and immutable version directory; this script is a reproducibility helper, do not rerun over a delivered freeze.'}
save('manifest.json',manifest)
