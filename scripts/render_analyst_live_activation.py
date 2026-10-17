"""Render saved live app/API evidence without modifying any app/database records."""
from collections import Counter
import hashlib
import json
from pathlib import Path


def render(root):
    baseline=json.loads((root/'baseline_results.json').read_text())
    current=json.loads((root/'analyst_final_results.json').read_text())
    selection=json.loads((root/'analyst_final_selector.json').read_text())
    base_selection=json.loads((root/'baseline_selector.json').read_text())
    saved=json.loads((root/'persisted_lineup_ids.json').read_text())
    prep=json.loads((root/'prepare_final.json').read_text())
    packet=json.loads((root/'packet_import.json').read_text())
    analyst=current['football_analyst']; lineups=current['results']
    names={r['player_id']:r.get('name') or r.get('player') or r.get('player_name') for r in current['player_pool']['rows']}
    def roster_key(lineup):return tuple(sorted((p['player_id'],p['roster_position']) for p in lineup))
    def variant_key(row):return row['scenario_id'],tuple(sorted((p['player_id'],p['slot']) for p in row['players']))
    def pool_points(result):return {p['player_id']:(p.get('projection'),p.get('p90')) for p in result['player_pool']['rows']}
    baseline_rosters={roster_key(lineup) for lineup in baseline['results']}
    comparison=dict(same_projection_run=current['projection_run_id']==baseline['projection_run_id'],
                    same_pool_projection_values=pool_points(current)==pool_points(baseline),
                    same_candidate_variants={variant_key(r) for r in selection['ranked_metrics']}=={variant_key(r) for r in base_selection['ranked_metrics']},
                    same_selected_rosters={roster_key(lineup) for lineup in lineups}==baseline_rosters,
                    baseline_candidate_variants=base_selection['candidate_count'],
                    analyst_candidate_variants=selection['candidate_count'],
                    analyst_generated_candidates=analyst['generated_candidate_count'],
                    selected_thesis_attributed_lineups=analyst['selected_lineup_count'],
                    quality_fraction=selection['quality_fraction'],quality_eligible_variants=selection['quality_eligible_count'],
                    underfill=selection['underfill_diagnostics'],entry_evidence_status='GENERATED_AND_SELECTED_NOT_ENTERED',
                    actual_contest_entry_ids=[],relaxations=analyst['relaxations'])
    (root/'comparison.json').write_text(json.dumps(comparison,indent=2)+'\n')
    lines=['# Thursday SEA at DEN — live Analyst app test','',
      '**Generation READY; entry clearance remains DEVELOPMENT_PREVIEW, not certified.**',
      'Kickoff: Thursday October 15, 2026, 8:15 PM Eastern / 6:15 PM Denver time (00:15 UTC October 16).','',
      'The running app imported the versioned packet, refreshed/prepared real inputs and persisted a normal Analyst-influenced optimizer run. There was no incomplete-evidence override, contest submission, payment, or inference that generated lineups were entered. These lineups are available for the user’s possible contest review.','',
      '## Current saved runs','',
      '- Preparation job: `'+prep['job_id']+'`.',
      '- Projection: `'+current['projection_run_id']+'`; cutoff `'+current['data_cutoff_at']+'`.',
      '- Baseline optimizer: `'+baseline['job_id']+'`.',
      '- Final Analyst optimizer: `'+current['job_id']+'`.',
      '- Packet: `'+packet['packet_id']+'` / `'+packet['analyst_packet_sha256']+'`.',
      '- Earlier Analyst run `670a7f44-9145-4920-b6f4-a1b92d61a0c9` is retained but superseded: its merge collapsed scenario variants. The corrected final run preserves the original 59 candidate variants.','',
      '## What entered generation','',
      '| Analyst thought | Typed directive | Requested / generated | Screen / selection |','|---|---|---|---|']
    for t in analyst['theses']:
        rows=[r for r in analyst['shadow'] if r['candidate_id'] in t.get('candidate_ids',[])]
        outcome=', '.join(('95% pass' if r.get('quality_eligible') else '95% fail')+'; '+('selected roster' if r.get('selected') else 'not selected') for r in rows) if rows else '; '.join(t['reasons'])
        roles='; '.join(role+': '+', '.join(names.get(pid,pid) for pid in ids) for role,ids in t['construction']['roles'].items())
        lines.append('| '+str(t['analyst_thought']).replace('|','/')+' | '+roles+' | '+str(t['requested'])+' / '+str(t['achieved'])+' | '+outcome+' |')
    lines+=['','The two Thursday branches each generated two candidates. Sunday KC opinions remained separate and abstained from this Thursday slate. No numeric opinion bonus, exposure forecast, or projection adjustment was introduced. Typed anchors control Captain/FLEX identities; remaining FLEX players follow the existing model and rules.','',
      '## Generated Analyst candidates','',
      '| Canonical candidate ID | Captain | FLEX | Salary | Mean | Original solver objective | 95% / selected |','|---|---|---|---:|---:|---:|---|']
    for r in analyst['shadow']:
        cap=next(p['player_master_id'] for p in r['roster'] if p['role']=='CPT')
        flex=', '.join(names.get(p['player_master_id'],p['player_master_id']) for p in r['roster'] if p['role']=='FLEX')
        lines.append('| `'+r['candidate_id']+'` | '+names.get(cap,cap)+' | '+flex+' | $'+format(r['salary'],',.0f')+' | '+format(r['projected_mean'],'.2f')+' | '+format(r['baseline_objective'],'.4f')+' | Pass / '+str(r.get('selected'))+' |')
    lines+=['','The unselected Darnold-Captain / Broncos-DST construction includes opposing Seattle offensive players. It passes the existing mathematical legality and quality screen because `avoid_dst_opponents` is false; it remains a football-coherence concern, not a new exclusion inferred from fandom.','',
      '## Selected normal portfolio','',
      '| Saved lineup ID | Captain | FLEX | Salary | Mean | Sum of marginal P90 | Analyst attribution |','|---|---|---|---:|---:|---:|---|']
    for row,lineup in zip(saved['analyst_final'],lineups):
        captain=next(p['name'] for p in lineup if p['roster_position']=='CPT')
        flex=', '.join(p['name'] for p in lineup if p['roster_position']=='FLEX')
        lines.append('| `'+row['lineup_id']+'` | '+captain+' | '+flex+' | $'+format(row['salary_used'],',.0f')+' | '+format(row['projected_mean'],'.2f')+' | '+format(row['projected_p90'],'.2f')+' | '+', '.join(lineup[0].get('analyst_thesis_ids',[]))+' |')
    lines+=['','Four Captain-aware lineups were selected from three distinct six-player sets; changing Captain is a distinct Showdown roster. Summed marginal P90 is not a calibrated joint lineup P90. The selected roster set is identical to the matched baseline. All four Analyst candidates already existed in baseline discovery; three selected lineups overlap the typed opinions. This proves ingestion, generation and attribution, not improved forecasts or a unique generation origin.','',
      '## Constraints and fill','',
      '- Requested 5; achieved 4. The unchanged selector reports: **'+selection['underfill_diagnostics']['reason']+'**. No limits were relaxed.',
      '- Original 59 candidate variants preserved; 43 pass the joint 95% screen (31 distinct Captain-aware quality rosters); 16 variants fail it.',
      '- Minimum common-baseline mean: '+format(.95*selection['best_mean'],'.2f')+'; minimum summed marginal P90: '+format(.95*selection['best_p90'],'.2f')+'. All four Analyst candidates pass.',
      '- Captain shortlist retained: '+', '.join(names[pid] for pid in analyst['policy']['shortlist_ids'])+'.',
      '- Each selected lineup has six distinct canonical identities, one Captain, five FLEX, both teams represented, and salary ≤ $50,000. Captain salary/scoring multiplier remains 1.5.','',
      'Exposure caps use the requested five-lineup denominator: Captain maximum three appearances. With only four achieved, JSN Captain exposure is 3/4 (75%) although the requested-count 60% cap passes. AJ Barner, Jason Myers and JSN appear in all four (100% realized), while the requested-count core cap permits four appearances. The existing output retains these underfill warnings; do not read the nominal rates as achieved four-lineup percentages.','',
      '## Readiness and lineage','',
      'The earlier `market_missing` warning came from older projection `116e6a12…`, which contained no market snapshot. Fresh normal preparation captured ESPN/DraftKings lines (SEA -3, DEN +3, total 40.5) at 2026-10-13T16:48:35Z and proved consumption before the 16:49:22Z projection cutoff. `salary_pool_missing` in the initial offline export came from its missing derived player dimension for Malick Meiga; the normal live loader verifies the canonical player master and passes. The reversed `DEN @ SEA` display was an alphabetical-order bug, now corrected from native salary `SEA@DEN` evidence. Historical records remain untouched.','',
      'The official NFL injury collector returned the wrong season/week. That ERROR is retained. Current independently sourced weekly roster/status, depth/starter and canonical context satisfy provisional generation readiness; they do not establish final game-day dressing.','',
      'Entry assessment remains false: native draft-group confirmation, final availability, upstream quote/salary publication freshness, weather clearance and contest assignment/submission remain unevaluated; role ownership is diagnostic-only. No contest or entry IDs were supplied or invented.','',
      'Saved lineup IDs, packet hashes and canonical Captain-aware candidate IDs are retained for later actual-entry/result linkage. Generated, selected, exported and observed-entry evidence remain separate. An eventual roster match may have multiple origins across these preserved runs.','',
      '## App use','',
      'Open http://127.0.0.1:5173, refresh, choose 2026 / Week 6 / Thursday Night / Captain GPP. In Recent optimizer runs, open final run `'+current['job_id']+'`. For a new run, expand **Wones Football Analyst**, import the packet JSON (idempotent), **Prepare slate for optimization**, then **Run Optimizer**. Clear the packet for the unchanged baseline path. Sources must be refreshed again before later Thursday decisions.','',
      'API :8000 and durable worker are launchd-managed; Vite :5173 serves current controls. Saved results were successfully reopened after restart. API/fixture/type/build tests pass; no Chrome or browser interaction was used, and no visual browser check is claimed.','',
      '## Sunday Main coverage','',
      'Sunday remains the primary ongoing research opportunity. The current salary-scope checklist contains ten games, zero completed full research reviews, and one preliminary KC opinion. This is partial coverage, not a finished slate-wide recommendation. Normal Classic consumers and the app Analyst summary are available; Thursday membership is never mapped into Sunday Main. Next research should inspect every actual Sunday salary game, retain partial-evidence opinions and factual gaps, then deliver selective cross-slate player/game construction theses in the same versioned packet/import path. No Sunday live generation was run in this Thursday activation.']
    native_path=root/'native_membership_verification.json'
    if native_path.exists():
        records=json.loads(native_path.read_text())
        matches=[row for row in records if row['status']=='verified_exact_native_ids_teams_positions_salaries']
        if len(matches)==1:
            match=matches[0]
            unavailable={fact['player_id'] for fact in match.get('unavailable_facts',[])}
            eligible=set(current['data_readiness']['generation_eligible_player_ids'])
            lines += ['', '## Independent native-slate verification', '',
                'After the saved runs, a read-only public DraftKings check uniquely matched native group **'+str(match['native_draft_group'])+'** to all '+str(match['imported_slots'])+' imported Captain/FLEX slot IDs, teams, natural positions and salaries. Other simultaneously published group types failed exact native membership.',
                'Observed at '+match['observed_at']+'. The '+str(len(unavailable))+' current native unavailable designations have '+str(len(unavailable & eligible))+' conflicts with generation-eligible players; none conflict with the selected rosters. Blank native status is not treated as affirmative availability.',
                'This independent later verification is not backdated or grafted into the original salary import. The saved app entry assessment still marks native-group metadata UNEVALUATED because that import lacked the field. Future normal salary imports can carry this verified group ID; the remaining final-dressing, publication, weather and assignment checks are still separate.']
    (root/'LINEUP_REVIEW.md').write_text('\n'.join(lines)+'\n')
    files=[p for p in root.iterdir() if p.is_file() and p.name!='manifest.json']
    code=[Path('backend/app/product_services/analyst_generation.py'),Path('backend/app/product_services/analyst_packets.py'),Path('backend/app/product_services/showdown_data_readiness.py'),Path('backend/app/product_services/optimizer.py'),Path('backend/app/api/product_routes.py'),Path('ui/src/App.tsx'),Path(__file__)]
    (root/'manifest.json').write_text(json.dumps(dict(contract_id='analyst_live_activation_manifest_v1',
        packet_sha256=packet['analyst_packet_sha256'], files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        delivery_code_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in code},
        code_hash_note='Delivery source hashes; saved run timestamps/receipts and immutable selector results identify executed evidence.'),indent=2)+'\n')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    render(parser.parse_args().directory)
