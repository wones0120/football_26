"""Author a new conditional research decision from the corrected prepared evidence.

This is a new version, not an expiry extension of the old injury hypotheses.
No model, availability truth, user constraint or calibrated probability is changed.
"""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from backend.app.product_services.analyst_packets import import_packet, validate
from backend.app.product_services.analyst_preparation import prepare_handoff
from backend.app.product_services.slate_preparation import SlatePreparationRequest

ROOT=Path(__file__).resolve().parent
rows=json.loads((ROOT/'fresh_pool.json').read_text())
prepared=json.loads((ROOT/'preparation.json').read_text())
now=datetime.now(UTC).isoformat()
game=prepared['source_manifest']['games'][0];gid=game['game_id'];lock=game['kickoff_at']
market=prepared['source_manifest']['markets'][0]
by_name={r['name']:r for r in rows} # display lookup selects audited UUIDs; no cross-source join
nix=by_name['Bo Nix']['player_id'];wilson=by_name['Emanuel Wilson']['player_id']
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
source_clock=datetime.fromtimestamp((ROOT/'fresh_pool.json').stat().st_mtime,UTC).isoformat()
sources=[dict(source_id='fresh_prepared_pool',uri=str(ROOT/'fresh_pool.json'),coverage='verified',
    observed_at=source_clock,available_at=source_clock,capture_sha256=sha(ROOT/'fresh_pool.json'),
    capture_kind='frozen_read_only_prepared_database_query',
    limitation='Original row source clocks retained in the captured file. Model workload and P90 are estimates, not observed future workload or final availability.'),
 dict(source_id='fresh_market',uri=market['source_uri'],coverage='verified',
    observed_at=datetime.fromisoformat(market['observed_at']).astimezone(UTC).isoformat(),
    available_at=datetime.fromisoformat(market['ingested_at']).astimezone(UTC).isoformat(),capture_sha256=market['content_sha256'],
    capture_kind='immutable_espn_draftkings_market_snapshot',
    limitation='Sportsbook update clock unavailable; this is the actual capture clock. DEN implied 19.0, SEA 21.5, total 40.5.'),
 dict(source_id='corrected_prior_history',uri=str(ROOT/'source_capture_and_ingest.json'),coverage='verified',
    observed_at=now,available_at=now,capture_sha256=sha(ROOT/'source_capture_and_ingest.json'),
    capture_kind='read_of_versioned_capture_and_ingest_receipt',
    limitation='Original nflverse Week 5 capture clock and raw artifact checksum are retained in the receipt; new read does not change them.')]
players=[]
for r in rows:
 players.append(dict(player_master_id=r['player_id'],position=r['position'],team=r['player_team'],game_id=gid,
    source_native_key=r['dk_player_id'],identity_source_ids=['fresh_prepared_pool'],
    workload_evidence=dict(contract_id='workload_evidence_v1',player_id=r['player_id'],
        historical={},derived_proxies={},explicit_pregame={},lineage={'snapshot':str(ROOT/'fresh_pool.json')},
        limitation='Volume-only sensitivity uses current prepared moments; no invented measured workload transfer or concentration.'),
    baseline_model_assessment={k:r.get(k) for k in ['projection','salary','game_total_line','team_spread_line','team_implied_total']}))

def hypothesis(hid,pid,text,support,contrary,condition,implication):
 return dict(hypothesis_id=hid,game_id=gid,formats=['SHOWDOWN'],player_master_ids=[pid],
    required_active_player_ids=[pid],status='research_only',action='none',hypothesis=text,
    supporting_evidence=support,contrary_evidence=contrary,conditional_assumptions=condition,
    testable_implication=implication,unknowns=['No calibrated scenario likelihood, finishing efficiency or final inactive clearance.',
        'No fresh coverage/personnel advantage or quantified injury redistribution is asserted.'],
    source_ids=['fresh_prepared_pool','fresh_market','corrected_prior_history'],
    uncertainty='Unquantified conditional sensitivity; design factors and equal scenario weights are research choices, not probabilities.',
    numeric_effect_proposal=None,expires_at=lock,
    recheck_triggers=['Any new inactive/role evidence for linked canonical player','Market or roster correction','New prepared build','Kickoff'])
hypotheses=[
 hypothesis('current_prepared_reference',nix,'Use the corrected current prepared pool as a reference scenario, conditional on its current role evidence remaining valid.',
 ['The complete prior-week participation checks pass and the new prepared source/model lineage is frozen.', 'Current modeled market total is 40.5; DEN implied total is 19.0.'],
 ['Readiness is generation readiness, not final entry clearance; QB evidence tier is inferred.'],
 ['Current verified model/source inputs remain the reference; no opportunity factor change in this branch.'],
 'Compare conditional portfolios to the exact current base moments without changing those moments.'),
 hypothesis('den_breakout_user_what_if_v2',nix,'Explicit user what-if: Denver offense clicks, with roughly 40 team points as a narrative tail target, not a fitted prediction.',
 ['The user authorized this conditional Denver breakout research branch.', 'Bo Nix is the current canonical DEN QB1 in the prepared pool, with inferred starting-QB evidence.'],
 ['Current market-implied DEN points are 19.0, far below the narrative 40-point tail.', 'No sourced new protection/coverage change establishes a breakout; source-backed efficiency probabilities are unavailable.'],
 ['Only in the hypothetical passing-success branch, increase DEN passing opportunity and reduce its rushing opportunity using explicitly declared research design factors.', 'This response model cannot fit or guarantee 40 team points; no unrelated SEA injury claim is required.'],
 'Inspect whether a DEN passing-opportunity portfolio differs from the current reference; evaluate actual drives/opportunities separately after lock.'),
 hypothesis('sea_run_control_conditional_v2',wilson,'Conditional alternative: Seattle controls more rushing opportunities if its currently supported active RB role and favorable game state persist.',
 ['Current market snapshot favors SEA by 2.5 with 21.5 implied points.', 'Emanuel Wilson is in the current canonical active/expected-starter research pool; his 8.90 modeled carries are an estimate, not observed future touches.'],
 ['A small spread does not establish a rushing script or actual touch concentration.', 'No supported new absence-driven workload transfer or exact carry allocation is declared.'],
 ['If Seattle earns favorable game state, test a higher team rushing / lower passing mix; do not change player availability or invent redistributed touches.'],
 'Compare team rushing opportunity against the declared reference; avoid treating fitted P90 or scenario inclusion as a probability.')]

def a(kind,team,factor):return dict(kind=kind,game_id=gid,team=team,factor=factor,elasticity=.6)
p=dict(contract_id='wones_football_analyst_v1',analyst_name='Wones Football Analyst',
 packet_id='THURSDAY_fresh_history_conditional_research_'+now.replace(':','-'),decision_at=now,frozen_at=now,
 preview_only=True,baseline_mutation=False,user_preferences=[],
 games=[dict(game_id=gid,season=2026,week=6,teams=[game['away_team'],game['home_team']],kickoff_at=lock,
    schedule_source_ids=['fresh_market'],format_membership={'SHOWDOWN':'confirmed_in_scope','CLASSIC':'out_of_scope_sunday_main'})],
 sources=sources,players=players,
 baseline_facts=[dict(kind='observed_fact',text='The captured sportsbook quote has SEA favored by 2.5 and total 40.5; this is a quote, not an outcome forecast.',source_ids=['fresh_market']),
    dict(kind='observed_fact',text='The history collector now verifies stats and snap team coverage through Week 5; canonical unresolved/conflicting rows remain explicit.',source_ids=['corrected_prior_history'])],
 hypotheses=hypotheses,analyst_assessments=[],
 coverage_gaps=['Final injury/active clearance is separate. No observed future workload, fresh matchup advantage, calibrated scenario probability or ownership edge is asserted.'],
 evaluation_disclosure='Fresh pregame research decision made after inspecting corrected Week 5 history and the current prepared Week 6 model. Historical outcomes were previously known; no outcome-blind historical validation claim.',
 predecessor={'original_authored_packet_sha256':prepared['analyst_handoff']['source_packet_sha256'],'supersession':'New independently authored conditional decision; original expired injury hypotheses and source clocks are preserved, not renewed.'},
 revision_notes=['Re-reviewed current market, canonical roles and repaired history. Denver user what-if is no longer mechanically dependent on unrelated expired SEA injury hypotheses.',
   'Regular mixed research: current reference, DEN passing breakout sensitivity and SEA run-control sensitivity. Factors/elasticity/equal weights are explicit design assumptions.'],
 scenario_assumptions=dict(contract_id='analyst_scenarios_v1',scenarios=[
    dict(scenario_id='current_prepared_reference',label='Current prepared reference; no volume change',hypothesis_ids=['current_prepared_reference'],assumptions=[a('passing_volume','DEN',1)]),
    dict(scenario_id='den_breakout_conditional',label='User what-if: DEN passing breakout; 40-point narrative not fitted',hypothesis_ids=['den_breakout_user_what_if_v2'],assumptions=[a('passing_volume','DEN',1.3),a('rushing_volume','DEN',.7)]),
    dict(scenario_id='sea_run_control_conditional',label='Conditional SEA run-control alternative',hypothesis_ids=['sea_run_control_conditional_v2'],assumptions=[a('rushing_volume','SEA',1.2),a('passing_volume','SEA',.8)])]))
errors=validate(p);assert not errors,errors
(ROOT/'fresh_research_packet.json').write_text(json.dumps(p,indent=2,allow_nan=False)+'\n')
receipt=import_packet(p)
(ROOT/'fresh_research_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(receipt)
# Check the exact automatic-selection contract before another expensive rebuild.
checked=prepare_handoff(request=SlatePreparationRequest(season=2026,week=6,slate='THURSDAY_NIGHT',action='prepare',contest_format='showdown'),
 result=prepared,rows=rows,checked_at=datetime.now(UTC).isoformat(),packets={receipt['analyst_packet_sha256']:p})
assert checked['checked_packet_sha256'] and 'scenario_assumptions' in checked['active_features'],checked
(ROOT/'fresh_research_precheck.json').write_text(json.dumps(checked,indent=2)+'\n')
print('automatic-compatible',checked['checked_packet_sha256'])
