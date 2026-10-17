"""Offline Wednesday delta, preserving original packets and preliminary model snapshot."""
from pathlib import Path
from datetime import datetime,timezone
import json,hashlib,copy
from backend.app.product_services.analyst_packets import validate
P=Path(__file__).resolve().parent; O=P/'v1'; R=Path('research/sunday_main_analyst_20261013')
load=lambda p:json.loads(Path(p).read_text())
prior=R/'v3/packet.json'; packet=copy.deepcopy(load(prior));now=datetime.now(timezone.utc).isoformat()
snapshot_path=Path('artifacts/preliminary_optimizer_snapshots/1d4bd6796aac13a3fe2dcb0cc1262fce960cc2e47d8efc8c6e1a9a11d05daabe.json');snap=load(snapshot_path)
packet.update(packet_id='20261014_WEDNESDAY_v1',decision_at=now,frozen_at=now)
packet.pop('scenario_assumptions',None)
packet['predecessors']=[{'path':str(prior),'sha256':hashlib.sha256(prior.read_bytes()).hexdigest()},{'path':str(R/'discovery_semantic_v1/v4_final/packet.json'),'sha256':hashlib.sha256((R/'discovery_semantic_v1/v4_final/packet.json').read_bytes()).hexdigest()}]
packet['baseline_binding']={'snapshot_path':str(snapshot_path),'snapshot_sha256':hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),'snapshot_contract_sha256':snap['sha256'],'projection_run_id':snap['projection_run_id'],'data_cutoff_at':snap['data_cutoff_at'],'entry_ready':snap['entry_ready'],'classification':snap['classification'],'new_model_run':False}
for n in ['salary','schedule','projection_runs','injury_counts','aliases']:
 f=O/(n+'_capture.json');r=load(f);packet['sources'].append({'source_id':'wed_'+n,'uri':str(f.resolve()),'coverage':'verified','observed_at':r['observed_at'],'available_at':r['observed_at'],'published_at':None,'capture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'capture_kind':'read_only_database_capture'})
packet['sources'].append({'source_id':'preserved_baseline','uri':str(snapshot_path.resolve()),'coverage':'verified','observed_at':now,'available_at':now,'published_at':None,'capture_sha256':hashlib.sha256(snapshot_path.read_bytes()).hexdigest(),'capture_kind':'preserved_preliminary_snapshot','limitation':'Capture time proves present read; original model cutoff and snapshot lineage retained separately.'})
for f in sorted(O.glob('*.json')):
 r=load(f)
 if 'source_id' in r:packet['sources'].append(r)
salary=load(O/'salary_capture.json')['rows']; sunday=[r for r in salary if r['slate']=='SUNDAY_MAIN'];scheduled=load(O/'schedule_capture.json')['rows']
packet['baseline_facts']=[{'fact_id':'wed_scope','kind':'observed_fact','text':'Fresh read-only scope: 513 Sunday Main rows / ten games; 112 Thursday Night rows. No Sunday Night or Monday Night salary rows in this capture.','source_ids':['wed_salary','wed_schedule']},{'fact_id':'wed_model','kind':'observed_fact','text':'Sunday completed preliminary projection run 28f764f0-6fe9-4463-b55e-c6c93804848c exists with 288 rows. Exact preserved snapshot remains entry_ready=false; no Week6 curated injury records. This corrects the earlier v3 no-Sunday-run statement.','source_ids':['wed_projection_runs','wed_injury_counts','preserved_baseline']}]
sem=load(R/'discovery_semantic_v1/semantic_findings.json')['findings']
bygame={x['game_id']:x for x in sem}
for p in packet['players']:
 match=next((r for r in snap['pool'] if r['player_id']==p['player_master_id']),None)
 if match:
  p['baseline_model_assessment']={k:match.get(k) for k in ['projection','projected_targets','projected_carries','pregame_opportunity_context_applied','opportunity_redistributed','official_availability_status','snap_share_trend']}
  p['baseline_model_assessment']['source_id']='preserved_baseline'
for h in packet['hypotheses']:
 h['source_ids']+=['preserved_baseline','wed_salary'];h['unknowns']=[x for x in h['unknowns'] if 'No Sunday projection' not in x];h['unknowns']+=['Preliminary baseline is available; its existence does not establish final readiness, confirmed availability or measured current role.'];h['uncertainty']='Qualitative provisional opinion, unquantified; no scenario factors, probabilities or model changes in this refresh.'
 if h['game_id'] in bygame:h['model_accounting']={'disposition':bygame[h['game_id']]['model_accounting']['status'],'mechanism':bygame[h['game_id']]['mechanism'],'scope_note':'Preserved semantic screen; skill-player opportunity context is derived/applied, not all direct fitted predictors; QBs differ.'}
for a in packet['analyst_assessments']:
 a['source_ids']+=['preserved_baseline','wed_salary'];a['supporting_reasoning']=a['supporting_reasoning'].replace('the missing Sunday baseline prevents measuring disagreement','the preserved preliminary baseline permits a comparison but does not establish a new projection error')
ari=next(h for h in packet['hypotheses'] if h['game_id']=='2026_06_ARI_LA');ari['source_ids'].append('LAR_suspension');ari['contrary_evidence'].append('Jackson suspended; appeal pending. Protection risk weakens full-stack conviction; no sack/efficiency forecast follows.');ari['recheck_triggers'].append('Alaric Jackson appeal / replacement protection')
ne=next(h for h in packet['hypotheses'] if h['game_id']=='2026_06_NYJ_NE');ne['source_ids'].append('NE_roundup');ne['conditional_assumptions']+=['Henderson actually unavailable; Stevenson active and retains his normal role; Kiner does not absorb all additional work.'];ne['unknowns'].append('No verified Week6 Stevenson designation or measured revised carry split. Questionable-user exclusion is not absence.');ne['hypothesis']='Conditional Stevenson concentration remains leading availability-driven watch; no unconditional monopoly'
for a in packet['analyst_assessments']:
 if a['game_id']==ari['game_id']:a['source_ids'].append('LAR_suspension');a['contrary_evidence'].append(ari['contrary_evidence'][-1]);a['revision']='weakened conviction, retained first passing research priority'
 if a['game_id']==ne['game_id']:a['source_ids'].append('NE_roundup');a['conditions']+=ne['conditional_assumptions'][-1:];a['revision']='retained conditional finding; no new Stevenson clearance'
# Thursday inherits canonical roster linkage from the prior evidence-only preview.
oldthu=load('research/pregame_ai_packet_20261013/packet.json');tg=next(g for g in scheduled if g['away_team']=='SEA');gid=tg['game_id']
oldsrc={s['source_id']:s for s in oldthu['sources']}
existing={s['source_id'] for s in packet['sources']}
for s in oldthu['sources']:
 if s['source_id'] not in existing:packet['sources'].append(s);existing.add(s['source_id'])
packet['games'].append({'game_id':gid,'season':2026,'week':6,'teams':['SEA','DEN'],'kickoff_at':'2026-10-16T00:15:00Z','schedule_source_ids':['wed_schedule','DEN_schedule','wed_salary'],'format_membership':{'CLASSIC':'out_of_scope_sunday_main','SHOWDOWN':'confirmed_in_scope'},'scope_note':'Thursday salary scope verified; standalone, never Sunday Main.'})
thuplayers=[]
for p in oldthu['players']:
 if p['game_id']==oldthu['games'][0]['game_id']:
  p=copy.deepcopy(p);p['game_id']=gid;packet['players'].append(p);thuplayers.append(p)
ids={p['display_name']:p['player_master_id'] for p in thuplayers};h=copy.deepcopy(ne)
h.update(hypothesis_id='SEA_DEN_wednesday_receiving',game_id=gid,formats=['SHOWDOWN'],player_master_ids=[ids['Jaxon Smith-Njigba'],ids['Sam Darnold']],hypothesis='Conditional JSN receiving Captain with Darnold FLEX',supporting_evidence=['Tuesday official estimated reports retain JSN limited and Surtain/Hufanga nonparticipation; Charbonnet remains PUP with return unlikely, not ruled out.'],contrary_evidence=['Denver coverage starters may return; JSN restriction or SEA protection failure would cancel receiving concentration story. Estimated participation is not an actual workload restriction.'],conditional_assumptions=['JSN active with normal receiving role','Denver coverage personnel absences confirmed; replacement quality unknown'],unknowns=['Current routes, expected workload, final designations, fresh observed market and candidate legality unavailable'],testable_implication='Compare receiver Captain versus QB Captain only if the concentrated passing branch survives final reports.',source_ids=['SEA_tuesday','DEN_tuesday','wed_salary','wed_schedule','roster'],uncertainty='Low, unquantified conviction; receiving branch research preference only.',expires_at='2026-10-14T18:00:00Z',recheck_triggers=['Wednesday game statuses','SEA activation transactions','JSN role clarification','Final inactives']);h.pop('model_accounting',None);packet['hypotheses'].append(h)
a=copy.deepcopy(packet['analyst_assessments'][0]);a.update(assessment_id='SEA_DEN_wednesday_judgment',game_id=gid,formats=['SHOWDOWN'],player_master_ids=h['player_master_ids'],source_ids=h['source_ids'],source_hypothesis_ids=[h['hypothesis_id']],lean=h['hypothesis'],supporting_reasoning=h['testable_implication'],contrary_evidence=h['contrary_evidence'],conditions=h['conditional_assumptions'],strongest_alternative='Darnold Captain with SEA receiving FLEX if scoring spreads; balanced Denver response if coverage returns.',construction_implications=[{'action':'shadow_comparison_only','format':'SHOWDOWN','type':'explicit_roles','roles':{'CPT':[ids['Jaxon Smith-Njigba']],'FLEX':[ids['Sam Darnold']]}}],what_changes_view=h['recheck_triggers'],expires_at=h['expires_at'],revision='Tuesday report supports continuity; final decision remains pending');packet['analyst_assessments'].append(a)
packet['prime_time_previews']=[{'game_id':'2026_06_DAL_GB','kickoff_at':'2026-10-19T00:20:00Z','source_ids':['wed_schedule','GB_preview','GB_schedule'],'salary_scope':'unavailable','canonical_player_scope':'not resolved in this edition; no typed player directive','lean':'Begin with two-team passing alternatives; do not extrapolate last season 40-40 tie or Love head-to-head success into a current high-total forecast.','counterevidence':'Current pass protection, receiver roles, health and affordable supports missing.','revision':'new preliminary game overview; no complete player evaluation'}, {'game_id':'2026_06_WAS_SF','kickoff_at':'2026-10-20T00:15:00Z','source_ids':['wed_schedule','SF_preview','SF_schedule'],'salary_scope':'unavailable','canonical_player_scope':'not resolved in this edition; no typed player directive','lean':'San Francisco offensive continuity is first research branch; compare sustained Washington response against 49ers control. Mike Evans rib discussion is dated Week5 evidence, not Monday restriction.','counterevidence':'Washington QB availability and current protection/coverage personnel unverified; 5-0 is descriptive, not win probability.','revision':'new preliminary game overview; no complete player evaluation'}]
packet['coverage_gaps']=['All ten Sunday games have preliminary opinions; final practice/designations, provider markets/weather, protection and coverage interaction evidence incomplete.','Current Sunday baseline exists but entry_ready=false; no new model generation, import or live activation here.','Thursday has actual salary scope and canonical preview identities, but current workload and final statuses incomplete.','SundayNight/MondayNight schedule verified, salary/current canonical role review unavailable; game-level preliminary previews only.','Exactly one Week6 Monday game; HOU@JAX international early game is outside imported Sunday Main.']
packet['evaluation_disclosure']='Prior observed Week1–5 outcomes and known Monday winner review are retrospective inputs, not blind validation. No calibrated scenarios, probabilities, numerical boosts or new selection directives. Original numeric exploratory scenarios remain in their prior packet; this briefing emits no scenario_assumptions.'
packet['slate_synthesis']['scope_source_ids']=['wed_salary','wed_schedule'];packet['slate_synthesis']['coverage_gap']=packet['coverage_gaps'][0]
packet['slate_synthesis']['slate_id']='SUNDAY_MAIN'
packet['revision_records']=[{'game_id':ari['game_id'],'change':'weakened','reason':'Fresh suspension with appeal pending adds protection risk.'},{'game_id':ne['game_id'],'change':'unchanged_conditional','reason':'Expected Henderson absence rechecked; no Stevenson clearance obtained.'},{'game_id':gid,'change':'strengthened_evidence_continuity','reason':'Tuesday estimated secondary/JSN reports retain prior premises; not final designations.'},{'change':'corrected','reason':'Sunday preliminary baseline now bound; earlier no-run wording superseded.'}]
support={
 '7268c13c-3496-4345-9a86-29bf92bdb987':('Juwan supports NO passing alternative','Protection and current role unconfirmed'),
 'd7c91815-1405-4106-a101-1ab68d24dad6':('Affordable TEN response to IND','Drive sustainability unconfirmed'),
 'afd9d1ba-bcc7-4baa-9b6e-55975c700003':('Replacement-role support could preserve strong core','Routes and Smith status unconfirmed; no transfer'),
 '0f02cff8-43aa-44f2-9b5b-678410b352f3':('Large salary saving, modest current target proxy','Snap rise already represented; no breakout claim')}
freshby={r['player_master_id']:r for r in sunday}
packet['cheap_support_review']=[]
for pid,(reason,counter) in support.items():
 row=next(r for r in snap['pool'] if r['player_id']==pid);fresh=freshby[pid];assert row['salary']==fresh['salary']
 packet['cheap_support_review'].append({'player_master_id':pid,'game_id':row['game_id'],'format':'CLASSIC','salary':fresh['salary'],'salary_row_id':fresh['curated_salary_id'],'source_native_key':fresh['source_player_key'],'baseline_points':row['projection'],'baseline_target_proxy':row['projected_targets'],'baseline_source_id':'preserved_baseline','salary_source_id':'wed_salary','subjective_reason':reason,'contrary_evidence':counter,'status':'research_only','action':'none','numeric_effect_proposal':None})
packet['scheduled_context']={'scheduled_wakeup':'2026-10-14T10:06:00Z','actual_decision_at':now,'note':'Actual capture/decision clocks retained; no backdating to scheduled wakeup.'}
(O/'packet.json').write_text(json.dumps(packet,indent=2)+'\n');errors=validate(packet);(O/'validation.json').write_text(json.dumps({'valid':not errors,'errors':errors,'validator':'backend.app.product_services.analyst_packets.validate','checked_at':now},indent=2)+'\n');print('validation',errors)
assert not errors
