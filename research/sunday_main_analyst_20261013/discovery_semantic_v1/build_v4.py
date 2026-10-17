import json,hashlib,sys,copy
from pathlib import Path
from datetime import datetime,timezone
from backend.app.product_services.analyst_packets import validate,packet_digest
P=Path(__file__).resolve().parent;root=P.parent
out=Path(sys.argv[1]) if len(sys.argv)>1 else P/'v4';out.mkdir(parents=True,exist_ok=False)
p=json.loads((root/'v3/packet.json').read_text());semantic=json.loads((P/'semantic_findings.json').read_text());now=sys.argv[2] if len(sys.argv)>2 else datetime.now(timezone.utc).isoformat();p.update(packet_id='20261013_SUNDAY_MAIN_discovery_v4',decision_at=now,frozen_at=now)
source=json.loads((P/'NE_oct13_primary.json').read_text());p['sources'].append(source)
snapshot=Path('artifacts/preliminary_optimizer_snapshots/1d4bd6796aac13a3fe2dcb0cc1262fce960cc2e47d8efc8c6e1a9a11d05daabe.json').resolve();snap=json.loads(snapshot.read_text())
p['sources'].append({'source_id':'discovery_frozen_baseline','uri':str(snapshot),'coverage':'verified','observed_at':now,'available_at':now,'published_at':None,'capture_kind':'existing_immutable_local_snapshot','capture_sha256':hashlib.sha256(snapshot.read_bytes()).hexdigest(),'limitation':'New analyst read after projection freeze; baseline remains unchanged. Snapshot declared preliminary and not entry-ready.'})
findings=[]
stev='c706298f-d5e9-441e-83fa-71b468ddc5a4';hend='39f4f0cd-846e-4690-aec5-7a0d43866fa0';kiner='206eca52-d246-4a60-81de-e8fb725b2a3e'
for f in semantic['findings']:
 supported=f['matchup']=='NYJ@NE'
 sids=[x['source_id'] for x in f['sources']]+['discovery_frozen_baseline']
 if supported:sids.append('NE_oct13_primary')
 accounting=copy.deepcopy(f['model_accounting']);accounting['rationale']='Selected skill-player historical opportunity trends are retained and used in derived opportunity context; field presence does not prove direct fitted-model inclusion; QB opportunity-context flag is false/unknown and is not claimed applied. Partial means a conditional interaction may be missing, not proven projection error.'
 if supported:
  accounting['delta_fields']=['conditional_lead_back_share_with_Henderson_absent_and_Stevenson_normal_role','conditional_eligible_NE_carry_budget_allocation']
  accounting['rationale']='Stevenson historical carry proxy10.8869, Henderson8.4678 (Qexcluded by userpolicy), Kiner4.3119; opportunity_redistributed=False. Historical trends participate in derived opportunity context; direct fitted FEATURE_COLUMNS do not include all trends. Favorite context is already applied. New conditional eligible-budget share allocation tests concentration; no Hendersonvacatedcarry reallocation or final absence asserted.'
 rec={'finding_id':f['finding_id'],'game_id':next(g['game_id'] for g in p['games'] if set(g['teams'])==set(f['matchup'].split('@'))),'player_master_ids':f['player_master_ids'],'source_ids':sids,'as_of':now,'classification':'hypothesized_model_blindspot' if accounting['status']=='partial' else 'statistical_outlier','status':f['status'],'evidence_strength':0.65 if supported else 0.35,'model_accounting':accounting,'mechanism':f['mechanism'],'counterevidence':[f['counterevidence']],'unknowns':f['unknowns']}
 if supported:
  rec['action']={'idea_id':'2026_06_NYJ_NE:NE:run_control','required_player_ids':[stev],'opportunity_share_transfer':{'channel':'carries','recipient_id':stev,'share':0.05}}
  rec['mechanism']+=' Conditional assumption: Henderson absent AND Stevenson available with normal role. The5%transfer is a bounded sensitivity within eligibleNEcarrybudget fromKiner/othereligiblepositivecarrydonors, NOT Henderson redistribution and NOT measured forecast. Evidence_strength is editorial source-support scoring, not a calibrated probability or learned scenario weight.'
 findings.append(rec)
p['discovery']={'contract_id':'analyst_discovery_v1','scan_snapshot_sha256':snap['sha256'],'scanned_game_ids':[g['game_id'] for g in p['games']],'findings':findings}
h=copy.deepcopy(next(x for x in p['hypotheses'] if x['hypothesis_id']=='NYJ_NE_primary'));h.update(hypothesis_id='NE_conditional_concentration_discovery_v4',hypothesis='Conditional NE lead-back concentration with Henderson absent and Stevenson normal role',source_ids=['NE_oct13_primary','discovery_frozen_baseline','web_NYJ','web_NE_NFL'],supporting_evidence=['New NFLOct13 report says Henderson expected to miss multipleweeks; this is an expectation, not final gamedesignation.','Preserved preliminarysnapshot shows historical carryproxies and no opportunityredistribution.'],conditional_assumptions=['Henderson actually misses this game; Qexclusion alone does not prove that.','Stevenson is available with normal role and retains meaningful work over Kiner.','A5%share shift within eligibleNEcarrybudget is exploratory sensitivity, not sourced carryforecast; donorbudget is Kiner/othereligibleplayers, not excludedHenderson.'],testable_implication='Under these conditions, test one reserved Stevenson construction in the NE run-control alternative while keeping baseline pointprojection unchanged. JetsWilson response can preserve drives but is not a mandatory bringback.',unknowns=['FinalHenderson/Stevensonavailability','ActualKinerrole/goal-line/passprotection split','NEOL/Pats drives against Jets pressure; opponent keep-pace not established']);p['hypotheses'].append(h)
scenario=copy.deepcopy(next(x for x in p['scenario_assumptions']['scenarios'] if x['scenario_id']=='NYJ_NE_primary_volume_v1'));scenario.update(scenario_id='NE_conditional_run_control_discovery_v4',label='Conditional NErun control with leadback concentration; Hendersonabsence/Stevensonnormalrole assumptions',hypothesis_ids=[h['hypothesis_id']])
p['scenario_assumptions']['scenarios'].append(scenario)
# Volume factor remains exploratory; typed discovery adds conserved allocation at runtime.
p['baseline_facts'].append({'fact_id':'new_discovery_baseline_available','kind':'observed_fact','text':'A later preliminarySundayprojection snapshot now exists, projectionrun28f764f0-6fe9-4463-b55e-c6c93804848c. Originalv3absencefact refers to its earlierDBcapture. Newdiscoverypreserves thissnapshot and itsquestionableexclusionmanifest; entry_ready=False.','source_ids':['discovery_frozen_baseline'],'projection_run_id':snap['projection_run_id']})
p['coverage_gaps']=['PreliminarySundaybaseline now bound to discovery scan; finalgameclearance/readiness still incomplete.','No new verified protection/coverageassignment or complete measured pregameroleforecast; ninefindingsremainwatchlist.','No inventedtarget/carryforecast. Conditional5%eligiblecarryshare sensitivity and0.65editorialsource-support score are not calibrated NFL quantities.']
p['evaluation_disclosure']+=' Discoveryv4 uses a NEW analystdecision after frozenprojection and new officialcapture; sourceavailability was notbackdated. Preservedv3 research and originalbaseline remain intact. Discovery transfer is eligiblecarrybudgetconserving; any lostHendersonopportunity is not automatically added. New scenario appends a conditional NE branch, preserving the original12 and bringing the library to13.'
errors=validate(p);(out/'packet.json').write_text(json.dumps(p,indent=2)+'\n');(out/'validation.json').write_text(json.dumps({'errors':errors,'valid':not errors,'packet_sha256':packet_digest(p),'source_clock':source['available_at'],'decision_at':now},indent=2)+'\n')
if errors:raise SystemExit('\n'.join(errors))
(out/'README.md').write_text('''# Sunday discovery packet v4

This new packet preserves v3 and the frozen preliminary projection. All ten games were screened. One provisional finding tests conditional New England lead-back concentration; nine findings remain watchlists. The new official NFL report was captured after the projection freeze, and the new analyst decision is later than that capture. No availability/source clock was backdated.

Conditions: Henderson actually absent and Stevenson available with normal role. User questionable-player exclusion does not prove absence. Historical target/carry/snap trends, favorite context and skill-player opportunity context are already included; those features are not a second analyst bonus.

The action requires Stevenson in one bounded reserved construction and tests a 5% share shift of the eligible NE carry budget from Kiner / other positive eligible carry donors. It does NOT redistribute Henderson carries because he is excluded from that budget. This sensitivity must pass donor conservation and support checks. It is not a measured allocation/forecast, new availability truth or baseline mutation.

Evidence strength 0.65 is an editorial source-support score; it is not calibrated probability, fitted weight or confidence in fantasy success. Volume factor 1.10 and elasticity 0.5 remain exploratory sensitivity settings. Final entry readiness remains false. Packet is validated locally and has NOT been imported live.

QBs have false/unknown opportunity-context flags. Applied-context claims here refer to skill players with attributed opportunities, not all 513 snapshot rows.
''')
(out/'manifest.json').write_text(json.dumps({'packet_sha256':packet_digest(p),'as_of':now,'files':{str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [root/'v3/packet.json',snapshot,P/'NE_oct13_primary.html',P/'NE_oct13_primary.json',P/'semantic_findings.json',P/'build_v4.py',out/'packet.json',out/'validation.json',out/'README.md']},'live_import':False,'baseline_mutation':False},indent=2)+'\n');print('VALID',packet_digest(p),out)
