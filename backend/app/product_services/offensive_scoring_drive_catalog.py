"""Physical offensive touchdown conversion with matched observed native drives."""
from copy import deepcopy
from .evaluation_record import digest
from .offensive_environment_catalog import _count
from .market_snapshots import canonical_team
from .redzone_drive_catalog import KNOWN_BASES

VERSION = 'offensive_scoring_drive_catalog_v1'
TOUCHDOWNS = {'observed_passing_touchdown','observed_rushing_touchdown'}


def _lineage(block):
    p=block['provenance'];p=p.get('original_context_provenance',p);s=p['source']
    result=(s.get('snapshot_id'),s.get('content_sha256'),p.get('event_receipt_sha256'))
    if not all(result):raise ValueError('Complete native source/event ancestry required')
    return result


def _key(gid,team,before_period):
    parts=gid.split('_');team=canonical_team(team)
    if (len(parts)!=4 or not parts[0].isdigit() or not parts[1].isdigit()
            or not 1<=int(parts[1])<=18 or parts[1]!=f'{int(parts[1]):02d}'
            or len({canonical_team(t) for t in parts[2:]})!=2 or int(parts[0])*100+int(parts[1])>=before_period
            or team not in {canonical_team(t) for t in parts[2:]}):
        raise ValueError('Prior native scoring game/team scope required')
    return gid,team


def _touchdowns(row):
    if row is None:return dict(known_physical_TDs=None,exact_TDs=None,status='missing_team_TD_source')
    values={}
    for field in ('rushing_TD','passing_TD'):
        c=row['counts'][field];values[field]=dict(known_count=_count(c['known_count']),unknown_events=_count(c['unknown_events']))
    known=sum(c['known_count'] for c in values.values());unknown=any(c['unknown_events'] for c in values.values())
    return dict(known_physical_TDs=known,exact_TDs=None if unknown else known,
        rushing_TD=values['rushing_TD'],passing_and_receiving_same_physical_TD=values['passing_TD'],
        status='unknown_TD_eligibility' if unknown else 'exact_within_observed_log')


def _redzone(row):
    if row is None:return dict(value=None,status='missing_entered_drive_source',unit='offensive_TDs_per_observed_redzone_entered_drive')
    m=deepcopy(row['metrics']['G23-M06']);outcomes=row['drive_outcomes']
    entered=_count(m['observed_entered_drives']);td=_count(m['known_touchdown_drives'])
    stall=_count(m['known_stall_drives']);unknown=_count(m['unknown_terminal_outcomes'])
    uncertainty=_count(m['unknown_entry_eligibility']);missing=_count(m['entry_events_missing_native_drive'])
    if td+stall+unknown!=entered or len(outcomes)!=entered or len({r['drive_id'] for r in outcomes})!=entered:
        raise ValueError('Entered-drive terminal grain/partition differs')
    known=[r for r in outcomes if r['outcome_known']]
    if any(r['completion_basis'] not in KNOWN_BASES or r.get('native_order_verified') is not True for r in known):
        raise ValueError('Known redzone terminal lacks native source proof')
    if sum(r['completion_basis'] in TOUCHDOWNS for r in known)!=td or len(known)!=td+stall:
        raise ValueError('Physical TD count differs from native drive terminal proofs')
    expected_stall=stall/entered if entered and not(unknown or uncertainty or missing) else None
    if m['value']!=expected_stall:raise ValueError('Source exact non-TD conversion differs')
    return dict(value=td/entered if entered and not(unknown or uncertainty or missing) else None,
        unit='offensive_TDs_per_observed_redzone_entered_drive',known_touchdown_drives=td,
        known_nonTD_terminal_drives=stall,observed_entered_drives=entered,
        unknown_terminal_outcomes=unknown,unknown_entry_eligibility=uncertainty,
        entry_events_missing_native_drive=missing,
        known_terminal_sample_conversion=td/(td+stall) if td+stall else None,
        status='observed_native_entered_drive_measurement')


def build_offensive_scoring_drive_catalog(scoring,drives,redzone,*,before_period):
    expected=('scoring_share_components_v1','drive_volume_catalog_v1','offensive_redzone_stalls_v1')
    if type(before_period)is not int or before_period<200001 or not 1<=before_period%100<=18:
        raise ValueError('Explicit prior REG scope required')
    for source,version in zip((scoring,drives,redzone),expected):
        if (source.get('version')!=version or source.get('before_period')!=before_period
                or source.get('pregame_serving_eligible')is not False
                or source.get('evidence_use')!='postlock_descriptive_not_pregame_or_serving'
                or source.get('forecast')is not None):raise ValueError('Matched reviewed descriptive source versions/scope required')
    lineage=_lineage(scoring)
    if any(_lineage(s)!=lineage for s in (drives,redzone)):
        raise ValueError('TD, offensive-drive and entered-drive sources differ')
    lookups=[]
    for source,field in ((scoring,'team_game_rows'),(drives,'game_rows'),(redzone,'game_rows')):
        lookup={}
        for row in source[field]:
            key=_key(row['game_id'],row['team'],before_period)
            if key in lookup:raise ValueError('Duplicate native scoring team/game')
            lookup[key]=row
        lookups.append(lookup)
    rows=[]
    for key in sorted(set().union(*(set(m) for m in lookups))):
        a,b,c=(m.get(key) for m in lookups);n=_touchdowns(a)
        if b is None:
            m=dict(value=None,numerator=n,denominator=None,status='missing_native_offensive_drive_source')
        else:
            d=deepcopy(b['metrics']['G01-M02']);count=_count(d['observed_native_drives'])
            attached=_count(d['known_attached_snaps']);snaps=_count(d['known_physical_snaps'])
            missing=_count(d['unknown_drive_snap_ids']);unknown=_count(d['unknown_snap_eligibility'])
            if attached+missing!=snaps or attached<count or (attached and not count):raise ValueError('Physical snap/native drive denominator differs')
            if n['exact_TDs'] is not None and not(missing or unknown) and n['exact_TDs']>count:
                raise ValueError('Physical offensive TDs exceed known native offensive drives')
            value=n['exact_TDs']/count if n['exact_TDs']is not None and count and not(missing or unknown) else None
            m=dict(value=value,numerator=n,denominator=d,status='observed_log_TDs_per_native_drive')
        rz=_redzone(c)
        if c is not None and n['exact_TDs'] is not None and rz['known_touchdown_drives']>n['exact_TDs']:
            raise ValueError('Known redzone touchdown subset exceeds exact full-team physical touchdowns')
        if b is not None and c is not None and not(missing or unknown):
            native={_count(float(drive)) for drive in b['native_drive_ids']}
            entered={_count(float(r['drive_id'])) for r in c['drive_outcomes']}
            if len(native)!=count or not entered<=native:
                raise ValueError('Redzone entered drive keys conflict with full offensive native drives')
        m['unit']='physical_offensive_TDs_per_observed_native_drive'
        shares={}
        for mid,field in (('G12-M02','rushing_TD'),('G12-M03','passing_and_receiving_same_physical_TD')):
            component=n.get(field);den=n['exact_TDs']
            shares[mid]=dict(value=component['known_count']/den if component is not None and den is not None and den>0 else None,
                numerator=deepcopy(component),exact_physical_offensive_TD_denominator=den,
                known_physical_offensive_TD_lower_bound=n['known_physical_TDs'],
                unit='fraction_of_physical_offensive_TDs',denominator_definition='rushing+passing physical offensive TDs; receiving not added')
        rows.append(dict(game_id=key[0],team=key[1],metrics={'G12-M01':m,**shares,'G12-M06':rz}))
    basis=dict(version=VERSION,before_period=before_period,game_rows=rows,
        definitions={'G12-M01':'Physical offensive rushing+passing TDs / distinct observed offensive native drives; receiving TD is the same passing event',
            'G12-M02':'Rushing TD / physical offensive rushing+passing TDs, not per-carry rate',
            'G12-M03':'Passing TD / physical offensive rushing+passing TDs, receiving TD not added; not per-pass-attempt rate',
            'G12-M06':'Any passing OR rushing TD after observed inside20 native drive entry / all observed entered drives'})
    return dict(**basis,semantic_sha256=digest(basis),source_semantic_hashes={
        'scoring':scoring['semantic_sha256'],'drives':drives['semantic_sha256'],'redzone':redzone['semantic_sha256']},
        provenance=dict(source_lineage=dict(snapshot_id=lineage[0],source_sha256=lineage[1],event_receipt_sha256=lineage[2]),
            scoring=deepcopy(scoring['provenance']),drives=deepcopy(drives['provenance']),redzone=deepcopy(redzone['provenance'])),
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        limitations=['Observed native drives do not establish complete official game/possession coverage',
            'Unknown numerator/drive/entry/terminal exposures mask exact rates; known lower bounds/samples remain explicit',
            'Passing/receiving are one physical TD; no return/defensive TD added to offensive numerator',
            'Native source/parent identity and actual retrospective clocks require independent immutable intake authentication'],
        consumer_status='Features only; models/scenarios/optimizer/current serving pending')
