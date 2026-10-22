"""One bounded cached TRAIN reconstruction + 2026 count refresh. No MC."""
from pathlib import Path
from collections import Counter
from copy import deepcopy
from datetime import datetime,UTC
import json,signal,time,gc
from research.game_progression_pilot_20261020.v1.prepare_integrated import load,ref,publish,target_context,ROOT
from backend.app.product_services.game_state_reconstruction import reconstruct_game_transitions,build_original_drive_blocks,opening_state_evidence,state_before,_event,event_count_label_proof,COUNT_LABEL_FIELDS
from backend.app.product_services.game_progression_source_adapter import prior_contexts
from backend.app.product_services.event_boundary_progression import compile_cycles,VERSION

D=Path(__file__).resolve().parent

def main():
    destination=D/'MANIFEST.json'
    if destination.exists():raise ValueError('No overwrite or automatic retry')
    start=time.monotonic();started_at=datetime.now(UTC).isoformat()
    def cap(*_):raise TimeoutError('60second whole cached preparation cap')
    signal.signal(signal.SIGALRM,cap);signal.setitimer(signal.ITIMER_REAL,60)
    source_receipt=ROOT/'research/game_state_reconstruction_20261020/v1/COHERENT_CACHED_RECEIPT_v2b.json'
    sources={o['season']:o for o in json.loads(source_receipt.read_text())['outputs']}
    prior=json.loads((ROOT/'research/game_progression_pilot_20261020/v1/INTEGRATED_MANIFEST_v2.json').read_text())
    context_rows=load(prior['input_refs']['prior_contexts'])['team_contexts'];train_context=prior_contexts(context_rows)
    source=sources[2023];projection=load(source['projection_ref']);columns=projection['columns']
    raws=[dict(zip(columns,v))for v in projection['rows']]
    reconstruction=reconstruct_game_transitions(raws,source_lineage=projection['source_lineage']);del raws,projection;gc.collect()
    blocks=build_original_drive_blocks(reconstruction)
    assert sum(b['source_row_count']for b in blocks['blocks'])+len(blocks['deterministic_admin_markers'])+len(blocks['explicit_overtime_rows'])+len(reconstruction['quarantine'])==source['input_rows']
    library=compile_cycles(reconstruction,blocks,train_context);library['source_projection_ref']=source['projection_ref']
    library_ref=publish(library,'TRAIN_EVENT_RENEWAL_V3')
    openings=opening_state_evidence(reconstruction);pairs={}
    for o in openings:pairs.setdefault(o['game_id'],{})[o['source_half']]=o
    opening_pairs=[]
    from backend.app.product_services.event_boundary_progression import state
    for gid,pair in sorted(pairs.items()):
        opening_pairs.append(dict(opening_id=gid,source_season=2023,certified=set(pair)=={1,2}and all(o['certified']for o in pair.values()),first_half=state(pair[1]['start_state'])if pair.get(1,{}).get('start_state')else None,second_half=state(pair[2]['start_state'])if pair.get(2,{}).get('start_state')else None))
    openings_ref=publish(opening_pairs,'TRAIN_OPENINGS_V3')
    summary=dict(cycles=len(library['cycles']),state_certified_cycles=sum(c['state_certified']for c in library['cycles']),unscopable_threats=len(library['threats']),source_blocks=len(blocks['blocks']),certified_source_blocks=sum(b['certified']for b in blocks['blocks']),certified_openings=sum(o['certified']for o in opening_pairs),source_all_row_partition_verified=True)
    repaired_block_ref=publish([dict(game_id=b['game_id'],block_ordinal=b['block_ordinal'],certified=b['certified'],barriers=b['barriers'])for b in blocks['blocks']],'SOURCE_BLOCK_TERMINAL_REPAIR_SUMMARY_V3')
    del reconstruction,blocks,library;gc.collect()
    # Evaluation labels are never part of the TRAIN library or target contexts.
    old_count_receipt=ROOT/'research/game_state_reconstruction_20261020/v1/COUNT_LABEL_ACTUAL_RECEIPT.json'
    old_source=next(o for o in json.loads(old_count_receipt.read_text())['outputs']if o['season']==2026)
    projection=load(sources[2026]['projection_ref']);index=load(sources[2026]['reconstruction_ref']);truth=load(old_source['regulation_truth_ref'])
    lookup=json.loads((ROOT/'research/game_progression_pilot_20261020/v1/EXACT20_FTN_LOOKUP.json').read_text());charting={}
    for f in lookup['rows']:
        if f['matches']==1:
            raw=f['FTN_rows'][0];charting[f['game_id'],f['play_id']]=dict(game_id=f['game_id'],play_id=f['play_id'],unique_native_key=True,raw_is_throw_away=raw['is_throw_away'],raw_is_drop=raw['is_drop'],source_sha256=lookup['source_ref']['content_sha256'],snapshot_id=lookup['source_ref']['snapshot_id'],captured_at=lookup['source_ref']['captured_at'])
    selected=json.loads((ROOT/'research/game_progression_pilot_20261020/v1/SMOKE_GAME_SELECTION.json').read_text());selected_ids={g['game_id']for g in selected['selected']}
    fields=(*COUNT_LABEL_FIELDS.values(),'physical_plays');mapping={r['source_ordinal']:(g['game_id'],g['sides'],r)for g in index['games']for r in g['rows']if g['game_id']in selected_ids}
    aggregates={gid:dict(sums=[dict.fromkeys(fields,0)for _ in (0,1)],unknown=[{f:[]for f in fields}for _ in (0,1)],proofs=[])for gid in selected_ids}
    for ordinal,values in enumerate(projection['rows']):
        if ordinal not in mapping:continue
        gid,sides,step=mapping[ordinal]
        if step['regulation_scope']=='EXPLICIT_OT':continue
        raw=dict(zip(projection['columns'],values));s=state_before(raw,sides);marker=step.get('typed_admin_marker');p=charting.get((gid,step['play_id']))
        e=_event(raw,s,sides,charting_proof=p)
        proven=event_count_label_proof(raw,s,e,typed_marker=marker)['production_by_side'] if step['regulation_scope']=='REGULATION' else [dict.fromkeys(fields)for _ in (0,1)]
        if e.get('charting_target_zero_proof'):aggregates[gid]['proofs'].append(dict(play_id=step['play_id'],proof=e['charting_target_zero_proof']))
        for side in (0,1):
            for field,value in proven[side].items():
                if value is None:aggregates[gid]['unknown'][side][field].append(step['play_id'])
                else:aggregates[gid]['sums'][side][field]+=value
    labels=[]
    for g in truth['games']:
        if g['game_id']not in selected_ids:continue
        row=deepcopy(g);a=aggregates[g['game_id']]
        for side in (0,1):
            for f in fields:
                row['production_by_side'][side][f]=a['sums'][side][f]if not a['unknown'][side][f]and g['metrics_admitted']else None
                row['unknown_production_play_ids_by_side'][side][f]=a['unknown'][side][f]
                row['known_production_sums_by_side'][side][f]=a['sums'][side][f]
        row['new_charting_count_proofs']=a['proofs'];labels.append(row)
    labels_ref=publish(dict(version='FIXED5_EVALUATION_ONLY_COUNT_REPAIR_V3',games=labels,previous_truth_ref=old_source['regulation_truth_ref'],FTN_lookup_ref=ref(ROOT/'research/game_progression_pilot_20261020/v1/EXACT20_FTN_LOOKUP.json'),never_generation_input=True),'EVALUATION_ONLY_LABELS_V3')
    lookup_context={(r['game_id'],r['team']):r for r in context_rows if r['period']//100==2026}
    games=load(prior['games_ref'])
    for game in games:
        # Identical frozen pregame inputs, not current observed roles/counts.
        assert game['context_by_side']==[target_context(lookup_context[game['game_id'],team])for team in game['sides']]
    games_ref=publish(games,'FIXED_PRIOR_TARGET_INPUTS_V3')
    m=dict(version=VERSION,started_at=started_at,completed_at=datetime.now(UTC).isoformat(),elapsed_seconds=time.monotonic()-start,library_ref=library_ref,openings_ref=openings_ref,games_ref=games_ref,evaluation_only_labels_ref=labels_ref,source_block_summary_ref=repaired_block_ref,source_receipt_ref=ref(source_receipt),prior_manifest_ref=ref(ROOT/'research/game_progression_pilot_20261020/v1/INTEGRATED_MANIFEST_v2.json'),source_projection_refs=[sources[y]['projection_ref']for y in (2023,2026)],summary=summary,known_selected_label_side_counts={f:sum(g['production_by_side'][s][f]is not None for g in labels for s in (0,1))for f in fields},runtime_refs=[ref(ROOT/p)for p in ('backend/app/product_services/game_state_reconstruction.py','backend/app/product_services/event_boundary_progression.py')],prep_runner_ref=ref(__file__),source_rule='ONLY_FIXED20FTN_LOOKUP;OTHER_UNKNOWN_RECIPIENTS_UNCHANGED',MC_paths=0,fits=0,activation=False)
    signal.setitimer(signal.ITIMER_REAL,0);destination.write_text(json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(seconds=m['elapsed_seconds'],support=summary,known_label_sides=m['known_selected_label_side_counts'])))

if __name__=='__main__':main()
