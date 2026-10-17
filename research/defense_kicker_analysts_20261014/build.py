"""Frozen Wednesday specialist screen and Thursday matched legal comparisons."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from backend.app.product_services.analyst_packets import validate, packet_digest
from backend.app.product_services.analyst_shadow import digest
from backend.app.product_services.defense_kicker_analyst import DIMENSIONS, CONTRACT, scan_specialists, paired_flex_comparison

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'v2'
WED = ROOT / 'research/wones_football_analyst_20261014_wednesday/v1/packet.json'
THU = ROOT / 'research/analyst_shadow_lineups_20261013/real_capture_v4/snapshot.json'
SUN = ROOT / 'artifacts/preliminary_optimizer_snapshots/1d4bd6796aac13a3fe2dcb0cc1262fce960cc2e47d8efc8c6e1a9a11d05daabe.json'


def main():
    OUT.mkdir(exist_ok=False)
    packet = json.loads(WED.read_text()); thursday = json.loads(THU.read_text()); sunday = json.loads(SUN.read_text())
    packet['packet_id'] = 'defense_kicker_20261014_v2'
    # A new research edition, never backdated to frozen projection clocks.
    now = datetime.now(timezone.utc).isoformat(); packet['decision_at'] = now; packet['frozen_at'] = now
    packet['parent_packet_sha256'] = packet_digest(json.loads(WED.read_text()))
    source = dict(source_id='specialist_thursday_frozen', uri=str(THU), coverage='verified',
                  observed_at=thursday['available_at'], available_at=thursday['available_at'],
                  capture_sha256=__import__('hashlib').sha256(THU.read_bytes()).hexdigest(),
                  fact_assertions={}, capture_kind='preserved_exact_legal_model_and_role_snapshot')
    packet['sources'].append(source)
    gid = next(g['game_id'] for g in packet['games'] if set(g['teams'])=={'SEA','DEN'})
    for row in thursday['players']:
        if row['position'] not in DIMENSIONS: continue
        pid=row['player_master_id']
        packet['players'].append(dict(player_master_id=pid,display_name=row['name'],position=row['position'],
            game_id=gid,team=row['team'],source_native_key=row['dk_player_id'],identity_source_ids=[source['source_id']],
            workload_evidence=dict(contract_id='workload_evidence_v1',player_id=pid,historical={},derived_proxies={},explicit_pregame={})))
    packet['defense_kicker_analysis']=dict(contract_id=CONTRACT, findings=[])
    for player in packet['players']:
        pos=player['position']
        if pos not in DIMENSIONS: continue
        game=next(g for g in packet['games'] if g['game_id']==player['game_id'])
        fmt='SHOWDOWN' if game['game_id']==gid else 'CLASSIC'
        f=dict(finding_id=fmt+':'+player['player_master_id'],player_master_id=player['player_master_id'],game_id=game['game_id'],team=player['team'],
            format=fmt,status='watchlist',action='none',as_of=now,expires_at=game['kickoff_at'],
            evidence={d:dict(status='unavailable',summary='No verified specialist measurement in these preserved inputs.',source_ids=[],value=None) for d in DIMENSIONS[pos]},
            mechanism='Evaluate sustained opponent dropbacks and actual pressure before sacks/turnovers; defensive TD is a high-variance path.' if pos=='DST' else 'Evaluate sustained drives that stall in FG range versus touchdowns yielding extra points; distance and role matter.',
            contrary_evidence=['Efficient opponent can avoid sacks and erase points-allowed bands; favoritism or low total alone is insufficient.'] if pos=='DST' else ['A strong offense may finish with touchdowns; fewer FG attempts can cap a kicker despite scoring volume.'],
            uncertainty='No specialist forward scoring calibration; frozen baseline is the sole numerical forecast.',
            what_changes_view=['Confirmed role/starters and injuries','Measured protection/pressure/dropbacks'] if pos=='DST' else ['Confirmed active kicker','Measured drives/red-zone stalls','Sourced current wind/venue and fourth-down tendencies'],
            model_accounting=dict(status='unknown',rationale='Base projections retained; source fields do not establish a distinct specialist model blindspot.'),
            opportunity_cost='Classic requires one DST; compare across games and displaced skill salary.' if fmt=='CLASSIC' else 'Same-Captain included/omitted FLEX legal solve; retain displaced skills, salary and unchanged baseline score.')
        if player['team']=='ARI':
            f['mechanism']='Rams LT suspension/appeal raises a conditional protection question for ARI DST; no pressure or sack-conversion forecast follows.'
            f['contrary_evidence'].append('Appeal/replacement protection can negate the concern; measured ARI pressure and opponent dropbacks are unavailable.')
            f['what_changes_view'].append('Alaric Jackson appeal and replacement protection')
            f['supporting_source_ids']=['LAR_suspension']
        if player['team']=='DEN' and pos=='DST':
            f['contrary_evidence'].append('Preserved Tuesday estimated Surtain/Hufanga nonparticipation warrants recheck; not final absence. No automatic negative adjustment.')
            f['supporting_source_ids']=['DEN_tuesday','SEA_tuesday']
        packet['defense_kicker_analysis']['findings'].append(f)
    # These are qualitative interpretations of prior captured injury articles,
    # not fresh source facts or validated opportunity measurements.
    errors=validate(packet); assert not errors, errors
    screens={'CLASSIC':scan_specialists(packet,sunday['pool'],fmt='CLASSIC'), 'SHOWDOWN':scan_specialists(packet,thursday['players'],fmt='SHOWDOWN')}
    captains=['1838dd60-35e8-4018-b307-39cde90e1f03','480d4188-7bf6-4684-b2b5-1d47f93d542a']
    captains=[pid for pid in captains if any(r['player_master_id']==pid for r in thursday['players'])]
    pairs=[paired_flex_comparison(thursday,specialist_id=r['player_master_id'],captain_id=pid)
           for pid in captains for r in thursday['players'] if r['position'] in DIMENSIONS]
    payload=dict(contract_id='defense_kicker_research_v1',generated_at=now,packet_sha256=packet_digest(packet),screens=screens,paired_comparisons=pairs,
        source_clocks=dict(wednesday_research=json.loads(WED.read_text())['decision_at'],thursday_model=thursday['decision_at'],sunday_model=sunday['data_cutoff_at']),
        entry_ready=False,live_mutations=False,calibration_status='unvalidated specialist mechanisms; baseline legal comparison only',
        prime_time_scope='DAL–GB Sunday Night and WAS–SF Monday Night schedule verified in parent; no salary scope, no fabricated candidates.')
    (OUT/'packet.json').write_text(json.dumps(packet,indent=2)+'\n'); (OUT/'report.json').write_text(json.dumps(payload,indent=2)+'\n')
    lines=['# Defense and kicker Analyst review', '', 'Version 2 adds per-finding source linkage, preserving version 1. It uses preserved Wednesday source research and Tuesday Thursday legal model. These are preliminary frozen comparisons, not new live forecasts or entry-ready lineups. Missing pressure/protection/stall/weather measurements remain unknown. No exposure or projection changes.', '',
           'Sunday Main: all ten games / twenty DST candidates screened. ARI protection watch is conditional on the captured Jackson suspension/appeal; it does not establish sack opportunity. No DST has enough core specialist evidence to trigger an action.', '',
           'Thursday: SEA/DEN DST and Myers/Lutz are optional FLEX alternatives. Denver secondary injury estimates are a recheck item, not final absences. Last week kicker success is retrospective and creates no scoring bonus.']
    names={r['player_master_id']:r['name'] for r in thursday['players']}
    for pair in pairs:
        lines += ['', f"## {names[pair['specialist_id']]} FLEX with {names[pair['captain_id']]} Captain"]
        for branch in pair['branches']:
            roster=', '.join(names[p['player_master_id']]+(' CPT' if p['role']=='CPT' else '') for p in branch['roster'])
            lines += [f"{'Include' if branch['included'] else 'Omit'}: {branch['solver_status']}; ${branch['salary']} / baseline mean {branch['baseline_mean']}. {roster}"]
        cost=pair.get('opportunity_cost')
        if cost:lines += [f"Displaced: {', '.join(names[p] for p in cost['displaced_player_ids'])}; baseline mean delta {cost['baseline_mean_delta']:.2f}. These metrics describe frozen opportunity cost, not specialist conditional ceiling."]
    lines += ['', 'No Captain ban is inferred. This pass addresses roster inclusion, usually FLEX. Separate DST/K Captain research would need an explicit meaningful comparison. Existing avoid-DST-opponents rules remain in the captured feasible region.', '', 'SNF DAL–GB and MNF WAS–SF remain schedule-level research only; salary and canonical specialist role coverage are unavailable.']
    (OUT/'REVIEW.md').write_text('\n'.join(lines)+'\n')
    manifest=dict(created_at=now,validation_errors=errors,packet_sha256=packet_digest(packet),files={str(f.relative_to(ROOT)):__import__('hashlib').sha256(f.read_bytes()).hexdigest() for f in [WED,THU,SUN]},live_mutations=False)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f"20 Sunday DST; 4 Thursday specialists; {len(pairs)} paired comparisons; {sum(p['achieved_lineup_count'] for p in pairs)} legal branches")


if __name__=='__main__': main()
