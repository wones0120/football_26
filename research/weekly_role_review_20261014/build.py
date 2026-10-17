"""Build a new sourced research edition; never revise earlier frozen decisions."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

from backend.app.product_services.analyst_packets import validate,packet_digest
from backend.app.product_services.analyst_shadow import digest
from backend.app.product_services.weekly_role_review import CONTRACT,scan_weekly_review

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent/'v1'
def load(p):return json.loads(Path(p).read_text())
def save(name,data):
    with (OUT/name).open('x') as f:json.dump(data,f,indent=2,allow_nan=False)


def main():
    parent=ROOT/'research/defense_kicker_analysts_20261014/v2/packet.json';packet=load(parent)
    now=datetime.now(timezone.utc).isoformat();packet.update(packet_id='weekly_role_review_20261014_v1',decision_at=now,frozen_at=now,parent_packet_sha256=packet_digest(packet))
    # Distinct later edition preserves the parent and its source clocks.
    sources={}
    for path in sorted(OUT.glob('*.json')):
        data=load(path)
        if 'source_id' in data:sources[data['source_id']]=data
    raw=load(OUT/'raw_capture.json');prior=load(OUT/'raw_prior_capture.json');aliases=load(OUT/'aliases_capture.json')
    for name in ['raw','raw_prior','stats','participation','schedule','aliases']:
        path=OUT/(name+'_capture.json');capture=load(path);sid='weekly_'+name
        sources[sid]=dict(source_id=sid,uri=str(path),coverage='verified',observed_at=capture['observed_at'],available_at=capture['observed_at'],capture_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),fact_assertions={},capture_kind='immutable_read_only_capture')
    sources['weekly_BUF_warning']['fact_assertions']={'conditional_warning':'Brady warned continued ball-security problems could reduce carries, while expressing confidence and noting he returned Cook to play.'}
    sources['weekly_BUF_coach']['fact_assertions']={'press_topics':'Official October 13 press-conference description includes Cook running well but committing turnovers; it does not publish a revised carry allocation.'}
    sources['weekly_NE_backup']['fact_assertions']={'backup_context':'The official Patriots review identifies Kyle Williams as a prepared backup filling in with Brown and Hollins unavailable, and records his deep-route success.',
        'reaction':'Williams described renewed personal confidence; Maye credited practice execution. Neither statement promises Williams a larger next-week target share.'}
    packet['sources'].extend(sources.values());players={p['player_master_id']:p for p in packet['players']}
    crosswalk={}
    for a in aliases['rows']:crosswalk.setdefault(a['source_key'],set()).add(a['player_master_id'])
    old={r['player_id']:r['raw_row_json'] for r in prior['rows']};observations=[];unresolved=[]
    for r in raw['rows']:
        canonical=set(crosswalk.get(r['player_id'],set())) & set(players)
        if len(canonical)!=1:
            unresolved.append(dict(source_native_player_id=r['player_id'],source_native_row_id=r['raw_nfl_weekly_stat_id'],candidate_player_master_ids=sorted(canonical),reason='no unique current packet native alias'));continue
        pid=next(iter(canonical));p=players[pid]
        # Require source-native player mapping PLUS game team; never display name.
        from Database.dst import normalize_team
        if normalize_team(r['team'])!=normalize_team(p['team']):
            unresolved.append(dict(source_native_player_id=r['player_id'],reason='native alias/current team conflict'));continue
        stats=r['raw_row_json']
        keep=['carries','targets','receptions','receiving_yards','receiving_tds','rushing_fumbles','rushing_fumbles_lost','receiving_fumbles','receiving_fumbles_lost','sack_fumbles','sack_fumbles_lost','fumbles_total','fumbles_lost_total']
        observations.append(dict(observation_id='raw:'+str(r['raw_nfl_weekly_stat_id']),player_master_id=pid,source_native_player_id=r['player_id'],source_native_row_id=str(r['raw_nfl_weekly_stat_id']),source_id='weekly_raw',previous_game_id=r['game_id'],season=2026,week=5,team=p['team'],available_at=raw['observed_at'],original_source_row_created_at=r['created_at'],
            identity_evidence=dict(kind='native_alias_and_team',alias_source_id='weekly_aliases',source_system=r['source_system']),completion_status='prior_week_final_stats_chronology_incomplete',stats={k:stats.get(k) for k in keep},prior_stats={k:old.get(r['player_id'],{}).get(k) for k in keep},events=[]))
    cook='87afab41-5db5-42d1-85b2-736edfcd712f';kyle='d1c586e0-ff33-43b7-bced-e22b4e88f876'
    espn=load(OUT/'BUF_espn.data.json');plays={str(p['id']):p for d in espn['drives']['previous'] for p in d['plays']}
    obs=next(o for o in observations if o['player_master_id']==cook)
    obs.update(completion_status='verified_complete',completion_evidence_source_id='weekly_BUF_espn',source_native_event_id='401872994',
        event_identity_crosswalk=dict(review_method='human_review_native_roster_and_boxscore',canonical_player_id=cook,gsis_id='00-0037248',espn_athlete_id='4379399',team='BUF',position='RB',jersey='4',source_ids=['weekly_raw','weekly_aliases','weekly_BUF_espn','weekly_Cook_stats']))
    for event_id,kind,summary in [('4018729942750','ball_security','Third-quarter fumble recovered by Buffalo; it did not change possession.'),('4018729944604','ball_security','Overtime fumble recovered by Rams, changing possession.'),('4018729944869','post_event_usage','Cook carried after the overtime loss of possession, at 4:11.'),('4018729944940','post_event_usage','Cook received another overtime carry at 2:45.')]:
        play=plays[event_id];obs['events'].append(dict(event_id=event_id,kind=kind,player_master_id=cook,identity_evidence='reviewed_native_roster_crosswalk',sequence=int(play['sequenceNumber']),period=play['period']['number'],clock=play['clock']['displayValue'],source_id='weekly_BUF_espn',summary=summary))
    ne=next(o for o in observations if o['player_master_id']==kyle);ne.update(completion_status='verified_complete',completion_evidence_source_id='weekly_NE_espn',source_native_event_id='401872986')
    def base(pid):
        p=players[pid];g=next(g for g in packet['games'] if g['game_id']==p['game_id']);o=next(o for o in observations if o['player_master_id']==pid)
        return dict(finding_id='weekly:'+pid,player_master_id=pid,game_id=p['game_id'],formats=['CLASSIC'],observation_ids=[o['observation_id']],status='watchlist',as_of=now,expires_at=g['kickoff_at'],forecast_basis='coach_conditional',unknowns=['No confirmed next-week workload allocation; no calibrated trust response.'],model_accounting=dict(status='partial',delta_fields=['event_sequence','current_coach_reaction'],rationale='Existing rolling box-score/opportunity fields represent recent output; sequence and new statements are separate research evidence, not a second fumble penalty.'),next_checks=['Current practice/depth and workload statement','Final availability of competing teammates'],discovery_action=None)
    f=base(cook);f.update(what_happened='Week 5: two fumbles, one lost; 25 carries. Third-quarter recovery stayed with Buffalo; overtime recovery went to Rams.',actual_reaction='Native ESPN sequence shows two more Cook rushes after the overtime turnover. Brady later expressed confidence and warned further security failures could reduce carries.',alternative_interpretations=['Continuity: returning Cook shows the normal role survives the error.','Discipline: a later error or explicit coaching restriction could redistribute work.','Personal bounceback motivation is plausible narrative, unmeasured and not a projection input.'],contrary_evidence=['Return-to-play and productive rushing argue against assuming immediate benching.','The warning is conditional; no announced Week 6 share cut or designated recipient was captured.'],role_mechanism='Conditional carry restriction would move work only after a real coaching decision; ordinary-role branch remains credible.',conditions=['Cook active','Role decision/source verified before changing workload'],roster_implication='Keep Cook eligible under normal user controls; compare BUF run-control presence with alternate construction, never apply a generic fumble penalty.',factual_premises=[dict(source_id='weekly_BUF_warning',fact_key='conditional_warning',text=sources['weekly_BUF_warning']['fact_assertions']['conditional_warning']),dict(source_id='weekly_BUF_coach',fact_key='press_topics',text=sources['weekly_BUF_coach']['fact_assertions']['press_topics'])],branches=[dict(branch_id='ordinary_role',conditions=['No verified Week 6 restriction'],role_implication='Retain baseline Cook role; consider ordinary BUF rushing constructions.'),dict(branch_id='discipline',conditions=['Further fumble or sourced actual role restriction and identified replacement'],role_implication='Recheck measured carry budget; do not invent a reduction or assign it automatically to Davis/Johnson.'),dict(branch_id='bounceback_story',conditions=['No measured role change'],role_implication='Motivation narrative only; identical baseline forecast and no selection bonus.')])
    w=base(kyle);w.update(forecast_basis='analyst_hypothesis',what_happened='Backup Kyle Williams caught all three targets for 91 yards and one touchdown against Las Vegas.',actual_reaction='Official review credits prepared backups; Williams discussed personal confidence and Maye credited practice execution. No promotion was promised.',alternative_interpretations=['Route execution could sustain an expanded role if veterans remain unavailable.','Two deep completions can inflate yardage on low volume without promotion.'],contrary_evidence=['Only three targets, not a high-volume monopoly.','Brown/Hollins returns or other receivers retaining routes may reverse opportunity.'],role_mechanism='Availability plus demonstrated deep-route execution supports a conditional cheap support watch; confirmation requires current routes/depth evidence.',conditions=['Williams active with meaningful routes','Current Brown/Hollins availability verified','Jets matchup capability reviewed independently'],roster_implication='Compare Williams as a cheaper Maye support against higher-volume receivers; retain salary opportunity cost and competing receivers.',factual_premises=[dict(source_id='weekly_NE_backup',fact_key=key,text=sources['weekly_NE_backup']['fact_assertions'][key]) for key in ['backup_context','reaction']],branches=[dict(branch_id='retained_backup_opportunity',conditions=['Veterans unavailable and Williams routes retained'],role_implication='Explore Maye/Williams cheap-support candidate; no target bonus from yardage alone.'),dict(branch_id='role_normalizes',conditions=['Veterans return or deeper targets remain spread'],role_implication='Baseline limited-volume role remains; do not force Williams in lineups.')])
    packet['weekly_role_review']=dict(contract_id=CONTRACT,observations=observations,findings=[f,w],unresolved_identity_records=unresolved,
        scope_note='All current Sunday/Main+Thursday packet players screened by prior-week native identity and team. Missing/ambiguous mappings are retained explicitly. Other prime-time salary scope remains unavailable.')
    errors=validate(packet);assert not errors,errors
    sun=load(ROOT/'artifacts/preliminary_optimizer_snapshots/1d4bd6796aac13a3fe2dcb0cc1262fce960cc2e47d8efc8c6e1a9a11d05daabe.json');thu=load(ROOT/'research/analyst_shadow_lineups_20261013/real_capture_v4/snapshot.json')
    report=dict(contract_id=CONTRACT,generated_at=now,packet_sha256=packet_digest(packet),entry_ready=False,live_mutation=False,
        screens={'CLASSIC':scan_weekly_review(packet,sun['pool'],fmt='CLASSIC'),'SHOWDOWN':scan_weekly_review(packet,thu['players'],fmt='SHOWDOWN')},
        findings=[f,w],input_snapshot_clocks=dict(sunday=sun['data_cutoff_at'],thursday=thu['decision_at'],review=now),unresolved_identity_count=len(unresolved),
        calibration_status='qualitative competing role mechanisms; not calibrated probabilities or new numerical player forecasts')
    save('packet.json',packet);save('report.json',report);save('manifest.json',dict(created_at=now,parent_sha256=hashlib.sha256(parent.read_bytes()).hexdigest(),packet_sha256=packet_digest(packet),validation_errors=errors,capture_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.iterdir()) if p.name.endswith(('.json','.html'))},live_mutation=False))
    lines=['# Last week → this week role review','',f"Version 1 · 2026 Week 6 · captured/reviewed {now}",'','This edition adds actual last-game events and reactions to the ordinary statistical screen. It preserves earlier frozen packets and distinguishes current research from original cutoff knowledge. Sunday/Main and Thursday are screened; SNF/MNF lack current salary scope. No forecast, user preference or final readiness is changed.','',
        '## James Cook: ball security warning, continued role evidence','',f['what_happened'],f['actual_reaction'],'','The useful new evidence is the order of events and the conditional coaching warning, not another penalty for box-score fumbles. Keep the ordinary-role branch; retain a discipline watch if a real restriction emerges. “Something to prove” remains an unmeasured psychological story. No lost-carry amount or successor is assumed.','',
        '[Official coach press conference](https://www.buffalobills.com/video/joe-brady-talks-clock-management-ball-security-staying-out-west-and-more) · [NFL coach report](https://www.nfl.com/news/joe-brady-bills-could-decrease-james-cook-s-carries-if-ball-security-doesn-t-improve) · [ESPN native event](https://www.espn.com/nfl/game/_/gameId/401872994/bills-rams)','',
        '## Kyle Williams: backup execution, conditional opportunity','',w['what_happened'],w['actual_reaction'],'','The upside branch requires retained routes and continued veteran absences. Three targets plus deep-play efficiency does not establish promotion. Compare cheaper Maye support against higher-volume alternatives; do not boost targets for confidence alone.','',
        '[Official Patriots game review](https://www.patriots.com/news/game-observations-8-takeaways-from-the-patriots-dominant-win-over-the-raiders-in-week-5)','',
        '## Complete game screen','', '| Format | Game | Pool players | Prior-week matched players | Event candidates |','|---|---|---:|---:|---:|']
    for fmt,screen in report['screens'].items():
        for game in screen['games']:lines.append(f"| {fmt} | {game['game_id']} | {game['scanned_player_count']} | {game['previous_week_observed_players']} | {len(game['reviewed_candidate_ids'])} |")
    lines+=['',f"{len(observations)} prior-week observations matched through native alias plus current team; {len(unresolved)} raw rows lack a unique in-scope mapping, including many out-of-scope players. They are preserved in the packet, not silently assigned by names.",'','Aggregate-only candidates remain statistical watchlists. Full native play sequences and coach/QB reaction evidence were reviewed for Cook and Williams; most other candidate sequences, drops, assignment responsibility and next-week role decisions remain unavailable. Final game chronology for uncaptured event feeds is explicit.','',
        '## Future briefing protocol','','Scan the previous completed game by canonical/native identity, then investigate fumbles versus lost, drops/errors, post-event return/benching, crucial-down usage, backup execution, QB/coaching changes and protection changes. Recheck current primary coach/QB statements, practice/depth and transactions. Record what the model already represents, contradictory branches and what changes the view. Reserve bounded constructions only for sourced distinct measured role changes through existing discovery controls; uncertain motivation never creates a numerical boost.']
    with (OUT/'REVIEW.md').open('x') as handle:handle.write('\n'.join(lines)+'\n')
    print('observations',len(observations),'candidates',sum(len(s['candidates']) for s in report['screens'].values()),'games',sum(len(s['games']) for s in report['screens'].values()))


if __name__=='__main__':main()
