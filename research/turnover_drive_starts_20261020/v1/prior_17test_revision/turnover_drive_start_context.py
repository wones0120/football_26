"""Observed opponent original-drive start position after typed acquisitions.

The reported ORIGINAL drive start is not the first physical line of scrimmage.
Native order establishes an acquisition before that snap; intervening ambiguous
live actions are barriers rather than permission to reuse an older turnover.
"""
from collections import defaultdict, Counter
from copy import deepcopy
from decimal import Decimal
from .evaluation_record import digest
from .fumble_event_components import _eligibility, _flag
from .original_drive_field_context import VERSION as DRIVE_VERSION, _integer
from .market_snapshots import canonical_team

VERSION='turnover_drive_start_context_v1'
NORMAL={'KICKOFF','PUNT','DOWNS','MISSED_FG','BLOCKED_PUNT,_DOWNS','BLOCKED_FG,_DOWNS'}


def _physical(raw):
    live,_=_eligibility(raw)
    if live is False:return False
    if _quiet(raw):return False
    if raw.get('play_type') in {'kickoff','punt','field_goal','extra_point'}:return False
    p,r,s,sc=(_flag(raw.get(k)) for k in ('pass_attempt','rush_attempt','sack','qb_scramble'))
    if p is True and r is True or r is True and s is True or sc is True and (r is not True or p is True or s is True):return None
    if live is not True:return None
    if p is None or r is None or s is None:return None
    return p or r or s


def _order(value):
    try:n=Decimal(str(value))
    except Exception:return None
    return n if n.is_finite() else None


def _quiet(raw):
    """Only explicit no-play/admin actions with no positive live evidence skip."""
    if any(_flag(raw.get(k)) is True for k in ('pass_attempt','rush_attempt','sack','interception','fumble','kickoff_attempt','punt_attempt','field_goal_attempt','touchdown')):return False
    if _flag(raw.get('no_play')) is True or raw.get('play_type')=='no_play':return True
    return raw.get('play_type_nfl') in {'TIMEOUT','END_QUARTER'} or raw.get('play_type') in {'time_out','quarter_end'}


def _origin(raw, basis, ledger, pair):
    """Return a nearest-boundary proof; None means a safe admin row to skip."""
    pid=str(_integer(raw.get('play_id')))
    proof=dict(play_id=pid,kind=None,classification=None,winner=None,loser=None,reason=None)
    live,_=_eligibility(raw)
    if _quiet(raw):return None
    if live is False:
        return proof|dict(reason='unclassified_excluded_or_reset')
    if live is not True or basis is None or basis['eligible'] is not True:
        return proof|dict(reason='unknown_live_eligibility_or_missing_fumble_basis')
    td=_flag(raw.get('touchdown'));ret_td=_flag(raw.get('return_touchdown'))
    def complete(value):
        if td is True or ret_td is True:
            return value|dict(typed_classification=value['classification'],classification=None,reason='touchdown_requires_new_possession_reset')
        if td is None or ret_td is None:
            return value|dict(typed_classification=value['classification'],classification=None,reason='unknown_touchdown_or_return_touchdown')
        return value
    intercept=_flag(raw.get('interception'));fumble=basis['fumble_play']
    if intercept is None or fumble is None:return proof|dict(reason='unknown_turnover_or_conflicting_fumble_evidence')
    off=canonical_team(raw['posteam']) if raw.get('posteam') else None
    defense=canonical_team(raw['defteam']) if raw.get('defteam') else None
    if intercept and fumble:return proof|dict(reason='same_play_interception_fumble_chain_unproven')
    if fumble:
        if ledger is None or ledger.get('lost_from_fumbler_team') is not True:
            return proof|dict(reason='fumble_final_possession_not_proven_lost')
        fs=ledger['reported_fumblers'];rs=ledger['reported_recoveries']
        if len(fs)!=1 or len(rs)!=1 or not fs[0]['native_id'] or not rs[0]['native_id'] or {fs[0]['team'],rs[0]['team']}!=pair:
            return proof|dict(reason='ambiguous_native_fumbler_recoverer')
        return complete(proof|dict(kind='FUMBLE',classification='giveaway',winner=rs[0]['team'],loser=fs[0]['team'],reason='sole_reported_lost_recovery',native_fumbler=deepcopy(fs[0]),native_recoverer=deepcopy(rs[0])))
    if intercept:
        p,r,s,sp=(_flag(raw.get(k)) for k in ('pass_attempt','rush_attempt','sack','qb_spike'))
        if (p,r,s,sp)!=(True,False,False,False) or _physical(raw) is not True or {off,defense}!=pair:
            return proof|dict(reason='interception_official_attempt_or_side_unproven')
        return complete(proof|dict(kind='INTERCEPTION',classification='giveaway',winner=defense,loser=off,reason='official_interception_without_fumble'))
    kind=None
    if raw.get('play_type')=='kickoff' and _flag(raw.get('kickoff_attempt')) is True:kind='KICKOFF'
    elif raw.get('play_type')=='punt' and _flag(raw.get('punt_attempt')) is True:
        blocked=_flag(raw.get('punt_blocked'))
        if blocked is False:kind='PUNT'
        elif blocked is True and _flag(raw.get('fourth_down_failed')) is True:kind='BLOCKED_PUNT,_DOWNS'
    elif raw.get('play_type')=='field_goal' and _flag(raw.get('field_goal_attempt')) is True:
        if raw.get('field_goal_result')=='missed':kind='MISSED_FG'
        elif raw.get('field_goal_result')=='blocked' and _flag(raw.get('fourth_down_failed')) is True:kind='BLOCKED_FG,_DOWNS'
    elif _physical(raw) is True and _flag(raw.get('fourth_down_failed')) is True:kind='DOWNS'
    if kind and {off,defense}==pair:
        winner=defense
        if kind=='KICKOFF':
            # Kickoff posteam can be the receiving side, unlike a punt.
            winner=canonical_team(raw['return_team']) if raw.get('return_team') else None
            if winner not in pair or _flag(raw.get('own_kickoff_recovery')) is not False:
                return proof|dict(reason='kickoff_receiving_or_own_recovery_unproven')
        return complete(proof|dict(kind=kind,classification='non_giveaway',winner=winner,loser=next(iter(pair-{winner})),reason='explicit_native_non_giveaway_'+kind))
    # A prior ordinary snap or unknown reset prevents carrying an older origin.
    return proof|dict(reason='intervening_physical_action_or_unproven_possession_reset')


def _summary(drives, unknown_extra=0):
    out={};unknown_class=sum(d['classification'] is None for d in drives)+unknown_extra
    for name in ('giveaway','non_giveaway'):
        subset=[d for d in drives if d['classification']==name]
        values=[d['start_yardline100'] for d in subset if d['start_yardline100'] is not None]
        unknown_position=len(subset)-len(values);hist={str(int(v)):values.count(v) for v in sorted(set(values))}
        mean=sum(values)/len(values) if values else None
        out[name]=dict(known_classified_drives=len(subset),known_start_drives=len(values),unknown_start_drives=unknown_position,
            unknown_class_membership=unknown_class,known_sample_histogram=hist,known_sample_mean=mean,
            exact_histogram=hist if not (unknown_class or unknown_position) else None,
            mean_start_yardline100=mean if not (unknown_class or unknown_position) else None)
    a,b=(out[k]['mean_start_yardline100'] for k in ('giveaway','non_giveaway'))
    x,y=(out[k]['known_sample_mean'] for k in ('giveaway','non_giveaway'))
    return dict(cells=out,giveaway_minus_non_giveaway_start_yardline100=a-b if a is not None and b is not None else None,
        known_sample_difference=x-y if x is not None and y is not None else None,
        non_giveaway_subclasses=dict(Counter(d['acquisition']['kind'] for d in drives if d['classification']=='non_giveaway')),
        unit='yards_to_incoming_offense_opposing_goal_line')


def build_turnover_drive_start_context(records, original_drives, native_order, fumbles):
    if original_drives.get('version')!=DRIVE_VERSION or native_order.get('version')!='validated_native_order_map_v1' or fumbles.get('version')!='fumble_event_components_v1':raise ValueError('Reviewed source parent versions required')
    before=original_drives['before_period']
    if type(before)is not int or not 1<=before%100<=18 or any(p['before_period']!=before for p in (native_order,fumbles)):raise ValueError('Same prior REG boundary required')
    sha=original_drives['source']['content_sha256']
    if native_order['source_byte_sha256']!=sha or fumbles['provenance']['source']['content_sha256']!=sha:raise ValueError('Exact same immutable source required')
    order_index={(r['game_id'],str(r['play_id'])):r for r in native_order['rows']}
    if len(order_index)!=len(native_order['rows']):raise ValueError('Duplicate reviewed native key')
    fb={(r['game_id'],str(r['play_id'])):r for r in fumbles['event_basis']};fl={(r['game_id'],str(r['play_id'])):r for r in fumbles['fumble_ledger']}
    rows=defaultdict(list);seen=set();unknown_order=set(native_order['unknown_order_games'])
    for raw in records:
        if raw.get('season_type')!='REG':continue
        year=_integer(raw.get('season'));week=_integer(raw.get('week'));play=_integer(raw.get('play_id'));gid=raw.get('game_id','');parts=gid.split('_')
        if year is None or week is None or play is None or len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}'] or not 1<=week<=18:raise ValueError('Native integral game/play/period required')
        if year*100+week>=before:continue
        key=(gid,str(play));n=order_index.get(key)
        if key in seen or n is None or key not in fb:raise ValueError('Duplicate, missing order or missing fumble native key')
        seen.add(key);o=_order(raw.get('order_sequence'))
        if o is None or o!=_order(n['order_sequence']) or not n['native_order_verified']:unknown_order.add(gid)
        pair={canonical_team(t) for t in parts[2:]}
        if len(pair)!=2:raise ValueError('Two native sides required')
        for field in ('posteam','defteam'):
            if raw.get(field) and canonical_team(raw[field]) not in pair:raise ValueError('Native side contradicts game')
        if raw.get('posteam') and raw.get('defteam') and canonical_team(raw['posteam'])==canonical_team(raw['defteam']):raise ValueError('Same offense and defense')
        rows[gid].append(dict(raw=raw,order=o,play_id=str(play),physical=_physical(raw),fumble_basis=fb[key],fumble=fl.get(key)))
    if seen!=set(order_index):raise ValueError('Full native source/order key universe required')
    games=[];all_drives=[];consumed=set();origins=[]
    for gid,items in rows.items():
        items.sort(key=lambda r:r['order'] if r['order'] is not None else Decimal(-1))
        if len({e['order'] for e in items})!=len(items):unknown_order.add(gid)
        pair={canonical_team(t) for t in gid.split('_')[2:]}
        for e in items:
            proof=_origin(e['raw'],e['fumble_basis'],e['fumble'],pair)
            if proof and (proof['classification']=='giveaway' or proof.get('typed_classification')=='giveaway'):origins.append(dict(game_id=gid,**proof))
        for g in (g for g in original_drives['game_rows'] if g['game_id']==gid):
            team=g['team'];opponent=next(iter(pair-{team}));drives=[]
            for original in g['drives']:
                did=original['original_drive_id']
                owned=[e for e in items if e['raw'].get('posteam') and canonical_team(e['raw']['posteam'])==team and _integer(e['raw'].get('drive'))==did]
                physical=[e for e in owned if e['physical'] is True];first=physical[0] if physical else None
                unknown_earlier=first is None or any(e['physical'] is None and (e['order'] is None or e['order']<=first['order']) for e in owned)
                if first and original['source_first_play_id'] is not None:
                    source_first=next((e for e in items if e['play_id']==str(original['source_first_play_id'])),None)
                    if source_first is None:unknown_earlier=True
                    elif any(e['physical'] is not False and not e['raw'].get('posteam') and source_first['order']<=e['order']<=first['order'] for e in items):unknown_earlier=True
                labels={str(e['raw']['drive_start_transition']) for e in owned if e['raw'].get('drive_start_transition')}
                label=next(iter(labels)) if len(labels)==1 else None
                acquisition=dict(play_id=None,kind=None,classification=None,winner=None,loser=None,reason='unproven_first_physical_snap_or_source_link')
                if first and not unknown_earlier and gid not in unknown_order and original['first_play_link_verified']:
                    for prior in reversed([e for e in items if e['order']<first['order']]):
                        proof=_origin(prior['raw'],prior['fumble_basis'],prior['fumble'],pair)
                        if proof is not None:
                            acquisition=proof|dict(order_sequence=str(prior['order']));break
                classification=acquisition['classification']
                match=label==acquisition['kind'] or label=='MUFFED_PUNT' and acquisition['kind']=='FUMBLE'
                if classification is not None and (not match or acquisition['winner']!=team):
                    acquisition=acquisition|dict(reason='reported_start_or_incoming_team_conflicts_with_typed_origin',typed_classification=classification,classification=None);classification=None
                if classification=='giveaway':consumed.add((gid,acquisition['play_id']))
                d=dict(game_id=gid,incoming_offense=team,opponent_defense=opponent,season=g['season'],week=g['week'],original_drive_id=did,
                    source_start_transition=label,raw_start_transitions=sorted(labels),source_first_play_id=original['source_first_play_id'],
                    first_physical_play_id=first['play_id'] if first else None,first_physical_order=str(first['order']) if first else None,
                    first_physical_boundary_unknown=unknown_earlier,first_play_link_verified=original['first_play_link_verified'],
                    reported_start_yardline100=original['reported_start_yardline100'],start_yardline100=original['start_yardline100'],
                    first_physical_snap_yardline100=original['first_observed_physical_snap_yardline100'],classification=classification,acquisition=acquisition)
                drives.append(d);all_drives.append(d)
            unknown_side_events=sum(e['physical'] is not False and not e['raw'].get('posteam') for e in items)
            unknown_extra=g['unknown_original_drive_events']+unknown_side_events
            games.append(dict(game_id=gid,season=g['season'],week=g['week'],incoming_offense=team,opponent_defense=opponent,
                unknown_original_drive_events=unknown_extra,unknown_side_physical_events=unknown_side_events,drives=drives,
                metrics=_summary(drives,unknown_extra)))
    profiles=[]
    for season,defense in sorted({(g['season'],g['opponent_defense']) for g in games}):
        gs=[g for g in games if g['season']==season and g['opponent_defense']==defense]
        profiles.append(dict(season=season,defense=defense,observed_game_ids=sorted(g['game_id'] for g in gs),
            metrics=_summary([d for g in gs for d in g['drives']],sum(g['unknown_original_drive_events'] for g in gs))))
    core=dict(version=VERSION,catalog_id='X06-M05',before_period=before,game_rows=sorted(games,key=lambda g:(g['game_id'],g['incoming_offense'])),
        profiles=profiles,censored_giveaway_anchors=[p for p in origins if (p['game_id'],p['play_id']) not in consumed],
        source=deepcopy(original_drives['source']),definition='Opponent ORIGINAL-drive source start field position after typed INT/sole lost fumble vs explicit kick/punt/missedFG/downs non-giveaway mixture',
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        limitations=['Observed physical ORIGINAL drives, not proof of full-game possession completeness or original pregame availability',
            'Unknown intervening acquisition/reset never inherits an older origin; return TDs without incoming physical drive are censored',
            'Reported start differs from first physical LOS; smaller yardline100 means closer to scoring',
            'Normal is an explicit heterogeneous non-giveaway acquisition mixture, not an inferred typical possession',
            'No causal field-position effect, forecast distribution or model/optimizer use'])
    return dict(**core,semantic_sha256=digest(core))


def derive_retrospective_drive_starts(snapshot,original_ref,order_ref,fumble_ref,*,order_published_at,actual_read_at):
    """Authenticate compact parents and one indexed CSV; never inflate events."""
    from datetime import datetime, UTC
    from pathlib import Path
    import csv, hashlib, json
    from .factual_designation import clock
    from .fumble_event_components import REQUIRED, FLAGS
    from backend.app.services.source_capture import verify_snapshot_artifact
    read=clock(actual_read_at);lock=clock(snapshot.slate_lock_at)
    if read is None or lock is None or not lock<=read<=datetime.now(UTC):raise ValueError('Actual nonfuture postlock read required')
    if clock(order_published_at) is None or clock(order_published_at)>read:raise ValueError('Native order publication clock missing or future')
    verify_snapshot_artifact(snapshot)
    meta=snapshot.metadata_json or {}
    if snapshot.source_system!='nflreadpy' or snapshot.dataset!='play_by_play' or snapshot.media_type!='text/csv' or meta.get('contract_id')!='operational_opportunity_source_v1' or meta.get('loader')!='load_pbp' or snapshot.source_uri!=f'nflreadpy://pbp/{snapshot.season}':raise ValueError('Indexed operational native PBP contract required')
    if snapshot.byte_count>64*1024*1024 or any(clock(v) is None or clock(v)>read for v in (snapshot.captured_at,snapshot.observed_at)):raise ValueError('Source clock/byte bounds differ')
    def load(ref,directory):
        path=Path(ref['path'])
        if path.resolve().parent!=(Path('artifacts')/directory).resolve() or ref['bytes']>8*1024*1024:raise ValueError('Managed parent path/size differs')
        raw=path.read_bytes()
        if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Managed parent immutable bytes differ')
        return json.loads(raw)
    original=load(original_ref,'original_drive_field_context');order=load(order_ref,'game_clock_pace_catalog');fumbles=load(fumble_ref,'fumble_event_components')
    for value,name,key in ((original,'original_drive_field_context','producer_sha256'),(fumbles,'fumble_event_components','producer_code_sha256')):
        if value.get('pregame_serving_eligible') is not False or value.get('forecast') is not None:raise ValueError('Descriptive nonserving parents required')
        provenance=value['provenance']
        if provenance.get(key)!=hashlib.sha256((Path('backend/app/product_services')/(name+'.py')).read_bytes()).hexdigest():raise ValueError('Current parent producer differs')
        for field in ('actual_read_at','actual_derived_at','actual_publication_at'):
            # Fumble source read clock is stored in its source receipt.
            value_clock=provenance.get(field) or provenance.get('source',{}).get(field)
            if clock(value_clock) is None or clock(value_clock)>read:raise ValueError('Parent actual clock missing or future')
    if digest({k:original[k] for k in ('version','before_period','game_rows','source_event_sha256','definitions')})!=original['semantic_sha256']:raise ValueError('Original-drive semantic core differs')
    if digest({k:order[k] for k in ('version','before_period','rows','unknown_order_games')})!=order['semantic_sha256']:raise ValueError('Native-order semantic core differs')
    if digest({k:fumbles[k] for k in ('version','before_period','game_rows','team_recovery_rows','fumble_ledger','event_basis','definitions')})!=fumbles['semantic_sha256']:raise ValueError('Fumble semantic core differs')
    ancestor=original['provenance']['parent_ref'];compressed=Path(ancestor['path']).read_bytes()
    if len(compressed)!=ancestor['compressed_bytes'] or hashlib.sha256(compressed).hexdigest()!=ancestor['artifact_sha256']:raise ValueError('Compressed event ancestor differs')
    if original['source']['snapshot_id']!=str(snapshot.snapshot_id) or fumbles['provenance']['source']['snapshot_id']!=str(snapshot.snapshot_id) or order['source_snapshot_id']!=str(snapshot.snapshot_id) or ancestor['source_snapshot_id']!=str(snapshot.snapshot_id):raise ValueError('Native source snapshot differs')
    if original['source_event_sha256']!=order['event_receipt_sha256'] or original['source_event_sha256']!=ancestor['event_receipt_sha256']:raise ValueError('Native event ancestor differs')
    before=snapshot.season*100+snapshot.week
    if original['before_period']!=before or original['source']['content_sha256']!=snapshot.content_sha256:raise ValueError('Source boundary/hash differs')
    required=set(REQUIRED)|{'order_sequence','drive','drive_start_transition','interception','touchdown','return_touchdown','own_kickoff_recovery','return_team','kickoff_attempt','punt_attempt','punt_blocked','field_goal_attempt','field_goal_result','fourth_down_failed'}
    optional=set(FLAGS)|{'desc'}
    records=[]
    with Path(snapshot.artifact_path).open(newline='') as stream:
        reader=csv.DictReader(stream);names=set(reader.fieldnames or [])
        if not required<=names:raise ValueError('Native acquisition schema missing')
        for i,row in enumerate(reader):
            if i>=100000:raise ValueError('Native source row bound exceeded')
            if row.get('season_type')=='REG' and _integer(row.get('season'))!=snapshot.season:raise ValueError('Native source season differs')
            records.append({k:row[k] if row[k]!='' else None for k in (required|optional)&names})
    result=build_turnover_drive_start_context(records,original,order,fumbles)
    result['provenance']=dict(original_drive_ref=deepcopy(original_ref),native_order_ref=deepcopy(order_ref),fumble_ref=deepcopy(fumble_ref),
        original_parent_provenance=deepcopy(original['provenance']),fumble_parent_provenance=deepcopy(fumbles['provenance']),
        order_published_at=str(order_published_at),actual_read_at=read.isoformat(),actual_derived_at=datetime.now(UTC).isoformat(),
        original_no_play_field_present='no_play' in names,raw_csv_native_rows=len(records),
        source_snapshot_id=str(snapshot.snapshot_id),source_byte_sha256=snapshot.content_sha256,
        producer_code_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path('backend/app/product_services/fumble_event_components.py'),Path('backend/app/product_services/original_drive_field_context.py')]},
        primary_dictionary='https://nflfastr.com/reference/fast_scraper.html',compressed_ancestor_hash_only=True,parent_inflates=0)
    return result
