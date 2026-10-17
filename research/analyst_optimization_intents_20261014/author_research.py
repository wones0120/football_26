"""New authored primary/alternate decisions; immutable predecessors remain intact."""
from copy import deepcopy
from datetime import UTC,datetime
import json
from pathlib import Path
from backend.app.product_services.analyst_packets import import_packet,packet_digest,validate
oldroot=Path('research/thursday_history_prepare_20261014');root=Path(__file__).resolve().parent
old=json.loads((oldroot/'fresh_research_packet.json').read_text());now=datetime.now(UTC).isoformat()
p=deepcopy(old);p.update(packet_id='THURSDAY_expected_contrarian_v1_'+now.replace(':','-'),decision_at=now,frozen_at=now)
p['predecessor']={'packet_sha256':packet_digest(old),'reason':'New reviewed primary assessment versus separately authorized alternate story, not a renewal of expired injury hypotheses.'}
gid=p['games'][0]['game_id'];expiry=p['games'][0]['kickoff_at'];refs=['fresh_prepared_pool','fresh_market','corrected_prior_history']
reference=deepcopy(old['hypotheses'][0]);reference.update(hypothesis_id='primary_close_game_v1',
 hypothesis='Primary game assessment: a competitive lower-total contest, Seattle a modest market favorite; optimize the current role-based upside without importing the Denver 40-point tail.',
 supporting_evidence=['Captured sportsbook quote: SEA favored by 2.5, game total 40.5, implied points SEA 21.5 / DEN 19.0.',
 'Current modeled SEA offensive opportunity includes an active Wilson role and current Darnold QB1 inference; the game remains close enough for both offenses to contribute.'],
 contrary_evidence=['A 2.5-point spread is a modest preference, not a likely blowout or a proved SEA rushing script.',
 'The saved model may favor affordable DEN players on this salary slate; a team favorite is not a Captain-team mandate.'],
 conditional_assumptions=['Use the current role/model distribution as the central reference and a modest SEA sustained-drive upside envelope.',
 'The 1.10 passing / 1.05 rushing factors and 0.6 elasticity are local research sensitivities, not fitted probabilities or projected team points.'],
 unknowns=['Final active clearance, finishing efficiency, full opponent matchup context and calibrated scenario likelihood are unavailable.',
 'Native DraftKings Q labels remain independently binding under the saved user exclusion; model assessments are not rewritten.'],
 testable_implication='Compare primary-context rosters under the frozen base moments and bounded local upside envelope; separately inspect actual game opportunities after lock.',
 expires_at=expiry)
contrarian=deepcopy(old['hypotheses'][1]);contrarian.update(hypothesis_id='alternate_den_breakout_v1',
 conditional_assumptions=['Explicit previously authorized user what-if: DEN passing success despite the 19.0 market-implied central score. Narrative target roughly 40 team points is not fitted or guaranteed.',
 'The alternate portfolio must express DEN QB plus at least two DEN receivers in Captain/FLEX combined; no Captain team or player is forced.',
 'Passing factor 1.3 / rushing 0.7 and elasticity 0.6 are declared opportunity-design assumptions, not measured future workloads.'],expires_at=expiry)
p['hypotheses']=[reference,contrarian]
def a(kind,team,factor):return {'kind':kind,'game_id':gid,'team':team,'factor':factor,'elasticity':.6}
p['scenario_assumptions']['scenarios']=[
 {'scenario_id':'expected_competitive_reference','label':'Expected competitive game · current role-based upside','hypothesis_ids':['primary_close_game_v1'],'assumptions':[a('passing_volume','DEN',1)]},
 {'scenario_id':'expected_sea_drive_upside','label':'Expected-game upside envelope · SEA sustained drives','hypothesis_ids':['primary_close_game_v1'],'assumptions':[a('passing_volume','SEA',1.1),a('rushing_volume','SEA',1.05)]},
 {'scenario_id':'contrarian_den_breakout','label':'Contrarian · user DEN passing-breakout what-if','hypothesis_ids':['alternate_den_breakout_v1'],
  'explicit_user_what_if':True,'assumptions':[a('passing_volume','DEN',1.3),a('rushing_volume','DEN',.7)]}]
p['optimization_intents']={'contract_id':'analyst_optimization_intents_v1',
 'EXPECTED_GAME':{'scenario_ids':['expected_competitive_reference','expected_sea_drive_upside'],
 'assessment':'Competitive lower-total game with SEA modestly favored; current role-based upside plus a modest SEA drive-success envelope. No DEN 40-point tail and no team forced at Captain.',
 'supporting_evidence':reference['supporting_evidence'],'counterevidence':reference['contrary_evidence'],
 'unknowns':reference['unknowns'],'source_ids':refs},
 'CONTRARIAN':{'scenario_ids':['contrarian_den_breakout'],
 'assessment':'Explicit user alternate: DEN passing success materially above its 19.0 market-implied center; roughly 40 points is a narrative tail target, not a prediction.',
 'supporting_evidence':contrarian['supporting_evidence'],'counterevidence':contrarian['contrary_evidence'],
 'unknowns':contrarian['unknowns'],'source_ids':refs,
 'story_requirements':{'script':'passing_breakout','team':'DEN','require_qb':True,'minimum_receivers':2}}}
p['revision_notes']=['New semantic decision explicitly separates the evidence-supported primary game assessment/local upside envelope from the user conditional Denver breakout.',
 'No source observation clock, baseline projection, injury truth, stored user control or old research packet is changed. Generation pools will differ and must be reported as separate generation experiments.']
p['evaluation_disclosure']='Fresh pregame primary/alternate decision based on the actual saved current prepared source/model pool and complete prior-week history; no outcome-blind retrospective or calibrated scenario probability claim.'
errors=validate(p);assert not errors,errors
(root/'packet.json').write_text(json.dumps(p,indent=2,allow_nan=False)+'\n')
receipt=import_packet(p);(root/'packet_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(receipt)
