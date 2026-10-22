"""Observed source-role packages: snap-weighted retention, not assignments or health."""
from collections import Counter,defaultdict
from datetime import date
from uuid import UUID
import re
from .evaluation_record import digest
from .fumble_event_components import _eligibility,_flag
from .market_snapshots import canonical_team
from .participation_source_components import VERSION as PARTICIPATION_VERSION,_int
from .center_sack_response import ROLES
from .participation_position_components import VERSION as POSITION_VERSION

VERSION='personnel_package_continuity_v1'


def _canonical(value):
    try:return value if str(UUID(str(value)))==value else None
    except (ValueError,TypeError,AttributeError):return None


def globally_qualified_identity(receipts):
    edges={};inverse=defaultdict(set)
    for native,proof in receipts.items():
        values={r.get('player_master_id') for r in proof.get('original_alias_evidence',[]) if _canonical(r.get('player_master_id'))}
        if _canonical(proof.get('player_master_id')):values.add(proof['player_master_id'])
        edges[native]=values
        for pid in values:inverse[pid].add(native)
    withheld={n for n,values in edges.items() if len(values)>1 or any(len(inverse[p])>1 for p in values)}
    result={}
    for native,proof in receipts.items():
        value=dict(proof)
        if native in withheld:value.update(status='global_native_identity_conflict',player_master_id=None)
        result[native]=value
    return result,sorted(withheld)


def physical_membership(raw):
    """Official-inclusive physical union once; spikes/kneels included, 2PT excluded."""
    flags=[_flag(raw.get(k)) for k in ('pass_attempt','rush_attempt','sack')]
    union=True if True in flags else False if all(v is False for v in flags) else None
    eligible,reason=_eligibility(raw)
    if reason=='explicit_exclusion':return False
    physical_pair=raw.get('play_type') in {'pass','run','qb_spike','qb_kneel'} and raw.get('play_type_nfl') in {'PASS','SACK','INTERCEPTION','FUMBLE_RECOVERED_BY_OPPONENT','RUSH'}
    material=any(_flag(raw.get(k)) is True for k in ('qb_dropback','qb_scramble','qb_spike','qb_kneel'))
    if union is False and (physical_pair or material):return None
    return False if eligible is False or union is False else True if eligible is True and union is True else None


def _unit(source,team,receipts):
    scope=source.get('participant_scopes',{}).get('offense',{}) if source else {}
    ids=scope.get('native_player_ids');positions=scope.get('position_by_native_id')
    valid=bool(source and source.get('possession_team')==team and source.get('native_phase') in (None,'REG')
        and scope.get('status')=='aligned_native_position_list' and isinstance(ids,list) and len(ids)==len(set(ids))==11
        and all(isinstance(n,str) and re.fullmatch(r'00-\d{7}',n) for n in ids)
        and isinstance(positions,dict) and set(ids)==set(positions) and all(p in ROLES for p in positions.values()))
    if not valid:return None,'source_eleven_unique_aligned_roles_unknown'
    native=sorted(positions.items());canonical=[];issues=[]
    for native_id,role in native:
        proof=receipts.get(native_id,{})
        pid=_canonical(proof.get('player_master_id')) if proof.get('status')=='unique_native_alias' else None
        if not pid:issues.append(native_id)
        else:canonical.append((pid,role))
    if len({p for p,_ in canonical})!=len(canonical):issues.extend(n for n,_ in native)
    key=tuple(sorted(Counter(positions.values()).items()))
    value=dict(native_participant_roles=native,canonical_participant_roles=sorted(canonical) if not issues else None,
        role_count_tuple=list(key),identity_unknown_native_ids=sorted(set(issues)))
    value['unit_id']=digest(native)
    return value,None


def _comparison(current,prior,units,*,canonical):
    unknown_current=current['unknown_physical_or_side']+current['unknown_units']
    prior_missing=prior is None or prior['observed_offense_rows']==0
    unknown_prior=0 if prior is None else prior['unknown_physical_or_side']+prior['unknown_units']
    if canonical:
        unknown_current+=current['identity_unknown_snaps']
        unknown_prior+=0 if prior is None else prior['identity_unknown_snaps']
    prior_sets=defaultdict(set)
    if prior:
        for uid in prior['unit_snaps']:
            unit=units[uid];members=unit['canonical_participant_roles'] if canonical else unit['native_participant_roles']
            if members is not None:prior_sets[tuple(map(tuple,unit['role_count_tuple']))].add(tuple(map(tuple,members)))
    comparable=retained=nonretained=unknown=comparable_false=0;details=[]
    for uid,count in sorted(current['unit_snaps'].items()):
        unit=units[uid];package=tuple(map(tuple,unit['role_count_tuple']))
        members=unit['canonical_participant_roles'] if canonical else unit['native_participant_roles']
        is_comparable=stayed=None
        if members is not None and not prior_missing:
            previous=prior_sets.get(package,set())
            if previous:
                is_comparable=True
                if tuple(map(tuple,members)) in previous:stayed=True
                elif not unknown_prior:stayed=False
            elif not unknown_prior:is_comparable=False
        if is_comparable is True:
            comparable+=count
            if stayed is True:retained+=count
            elif stayed is False:nonretained+=count
            else:unknown+=count
        elif is_comparable is False:comparable_false+=count
        else:unknown+=count
        details.append(dict(unit_id=uid,current_snaps=count,comparable_package=is_comparable,retained_participants_and_roles=stayed))
    # Unqualified canonical units were included in unknown_current; don't invent their denominator.
    full_unknown=bool(unknown_current or unknown or current['observed_offense_rows']==0)
    value=retained/comparable if comparable and not full_unknown else None
    known_den=retained+nonretained
    return dict(value=value,full_comparable_cohort_known=not full_unknown,known_retained_snaps=retained,known_nonretained_snaps=nonretained,
        known_comparable_snaps=comparable,known_noncomparable_snaps=comparable_false,
        unknown_unit_comparison_snaps=unknown,unknown_current_source_exposures=unknown_current,
        prior_observed_universe_unknown=bool(prior_missing or unknown_prior),
        known_classified_sample_fraction=retained/known_den if known_den else None,unit_comparisons=details)


def build_personnel_package_continuity(participation,pbp_rows,schedule_games,identity_receipts,*,before_period):
    if participation.get('version') not in {PARTICIPATION_VERSION,POSITION_VERSION} or participation.get('pregame_serving_eligible') is not False:
        raise ValueError('Verified historical native participation required')
    identity_receipts,globally_withheld=globally_qualified_identity(identity_receipts)
    season=participation['season'];expected={};team_schedule=defaultdict(list)
    for game in schedule_games:
        if game['season']!=season or game['game_type']!='REG' or season*100+game['week']>=before_period:continue
        gid=game['game_id'];parts=gid.split('_')
        if len(parts)!=4 or parts[:2]!=[str(season),f"{game['week']:02d}"] or gid in expected:raise ValueError('Unique native scheduled game required')
        sides={canonical_team(t) for t in parts[2:]}
        if sides!={game['home_team'],game['away_team']} or None in sides:raise ValueError('Scheduled native teams differ')
        expected[gid]=game
        for team in sorted(sides):team_schedule[team].append(game)
    games={(gid,t):dict(game_id=gid,team=t,season=season,week=g['week'],observed_offense_rows=0,
        known_physical_snaps=0,unknown_physical_or_side=0,unknown_units=0,identity_unknown_snaps=0,unit_snaps=Counter())
        for gid,g in expected.items() for t in (g['home_team'],g['away_team'])}
    sources={};seen=set();units={};basis=[];identity_requests=set();incidents={}
    for source in participation['rows']:
        source_parts=source['game_id'].split('_')
        if len(source_parts)!=4 or source_parts[:2]!=[str(season),f"{source['week']:02d}"] or source.get('season')!=season:raise ValueError('Native participation period/game binding differs')
        key=(source['game_id'],source['play_id'])
        if key in sources:raise ValueError('Duplicate native participation key')
        sources[key]=source
    for raw in pbp_rows:
        if raw.get('season_type')!='REG':continue
        gid=raw['game_id'];play=str(_int(raw['play_id']));year=_int(raw['season']);week=_int(raw['week']);parts=gid.split('_')
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}'] or year!=season:raise ValueError('Native PBP period/game binding differs')
        if year*100+week>=before_period:continue
        if gid not in expected:raise ValueError('Observed PBP game outside scheduled cohort')
        key=(gid,play)
        if key in seen:raise ValueError('Duplicate native PBP event')
        seen.add(key);sides={expected[gid]['home_team'],expected[gid]['away_team']}
        team=canonical_team(raw.get('posteam')) if raw.get('posteam') not in (None,'') else None
        if team is not None and team not in sides:raise ValueError('Native offense outside source game')
        defense=canonical_team(raw.get('defteam')) if raw.get('defteam') not in (None,'') else None
        if defense is not None and (defense not in sides or defense==team):raise ValueError('Native defense outside source game or same as offense')
        membership=physical_membership(raw)
        if team is not None:games[gid,team]['observed_offense_rows']+=1
        if membership is False:continue
        unit=None;reason='unknown_physical_membership_or_offense' if membership is None or team is None else None
        if team is not None and membership is True:
            unit,reason=_unit(sources.get(key),team,identity_receipts)
        possible=sides if team is None else {team}
        for side in possible:
            game=games[gid,side]
            if team is None or membership is None:game['unknown_physical_or_side']+=1
            else:
                game['known_physical_snaps']+=1
                if unit is None:game['unknown_units']+=1
                else:
                    uid=unit['unit_id'];units[uid]=unit;game['unit_snaps'][uid]+=1
                    if unit['canonical_participant_roles'] is None:
                        game['identity_unknown_snaps']+=1;identity_requests.update(unit['identity_unknown_native_ids'])
                        for native in unit['identity_unknown_native_ids']:
                            proof=identity_receipts.get(native,{})
                            incidents[native,gid,team]=dict(game_id=gid,team=team,source_player_id=native,position=dict(unit['native_participant_roles'])[native],
                                reason=proof.get('status','missing_frozen_attachment'),alias_evidence=proof.get('original_alias_evidence',[]))
        basis.append(dict(game_id=gid,play_id=play,team=team,physical_membership=membership,
            unit_id=unit['unit_id'] if unit else None,unknown_reason=reason))
    # A source-only participation row could be another physical snap; never silently omit it.
    for key,source in sorted(sources.items()):
        gid,play=key
        if gid not in expected or key in seen:continue
        sides={expected[gid]['home_team'],expected[gid]['away_team']}
        team=source.get('possession_team')
        if team is not None and team not in sides:raise ValueError('Source-only native offense contradicts game')
        for side in sides if team is None else {team}:games[gid,side]['unknown_physical_or_side']+=1
        basis.append(dict(game_id=gid,play_id=play,team=team,physical_membership=None,unit_id=None,
            unknown_reason='source_participation_has_no_matching_REG_PBP_event'))
    comparisons=[]
    for team,schedule in sorted(team_schedule.items()):
        if len({g['week'] for g in schedule})!=len(schedule):raise ValueError('Unique scheduled same-team week required')
        dates={}
        for g in schedule:
            try:dates[g['game_id']]=date.fromisoformat(g['game_date'])
            except (KeyError,TypeError,ValueError):dates[g['game_id']]=None
        order_known=all(v is not None for v in dates.values()) and len(set(dates.values()))==len(dates)
        schedule.sort(key=(lambda g:(dates[g['game_id']],g['game_id'])) if order_known else (lambda g:(g['week'],g['game_id'])))
        for i,game in enumerate(schedule):
            current=games[game['game_id'],team];prior=games[schedule[i-1]['game_id'],team] if i and order_known else None
            row=dict(game_id=game['game_id'],team=team,season=season,week=game['week'],
                prior_scheduled_game_id=prior['game_id'] if prior else None,scheduled_predecessor_order_proven=order_known,first_game_not_applicable=order_known and i==0 and game['week']==1)
            if row['first_game_not_applicable']:
                row.update(catalog_value=None,native_variant=None,canonical=None)
            else:
                native=_comparison(current,prior,units,canonical=False);canonical=_comparison(current,prior,units,canonical=True)
                row.update(catalog_value=canonical['value'],native_variant=native,canonical=canonical)
            comparisons.append(row)
    for game in games.values():game['unit_snaps']=dict(sorted(game['unit_snaps'].items()))
    profiles=[]
    for team in sorted(team_schedule):
        eligible=[r for r in comparisons if r['team']==team and not r['first_game_not_applicable']]
        metrics={}
        for key in ('canonical','native_variant'):
            values=[r[key] for r in eligible];known=all(v['full_comparable_cohort_known'] for v in values)
            denominator=sum(v['known_comparable_snaps'] for v in values);retained=sum(v['known_retained_snaps'] for v in values)
            sample_den=sum(v['known_retained_snaps']+v['known_nonretained_snaps'] for v in values)
            metrics[key]=dict(value=retained/denominator if known and denominator else None,
                known_retained_snaps=retained,known_comparable_snaps=denominator,unknown_game_comparisons=sum(not v['full_comparable_cohort_known'] for v in values),
                known_classified_sample_fraction=retained/sample_den if sample_den else None)
        profiles.append(dict(season=season,team=team,observed_scheduled_comparisons=len(eligible),**metrics))
    basis.sort(key=lambda e:(e['game_id'],e['play_id']))
    core=dict(version=VERSION,candidate_ids=['G18-M10'],season=season,before_period=before_period,
        unit_registry=units,profiles=profiles,game_rows=sorted(games.values(),key=lambda g:(g['game_id'],g['team'])),continuity_rows=comparisons,
        event_basis=basis,identity_request_native_ids=sorted(identity_requests),identity_review_requests=[incidents[k] for k in sorted(incidents)],global_identity_withheld_native_ids=globally_withheld,
        definition='Comparable literal source-role-count tuples; current physical-snap-weighted retention of exact participant-role sets versus immediate scheduled predecessor',
        canonical_identity_policy='Catalog values require unique frozen canonical participants; native-source variant kept separate',
        source_coverage='Observed source physical-snap universe, not independently complete NFL game or assigned route/block/side roles')
    return dict(**core,semantic_sha256=digest(core),model_consumed=False,optimizer_consumed=False,pregame_serving_eligible=False,
        evidence_use='historical_postseason_revised_observed_package_continuity_not_current_expected_personnel_or_health')


def persist_package_identity_requests(connection,blocks,*,source_refs):
    """Append immutable attachment incidents; never modify alias/master/resolved cases."""
    import json
    from sqlalchemy import text
    incidents=defaultdict(list)
    for block in blocks:
        if block.get('version')!=VERSION or block.get('pregame_serving_eligible') is not False:
            raise ValueError('Exact nonserving package evidence required')
        for row in block['identity_review_requests']:incidents[row['source_player_id'],row['reason']].append(row)
    output=[]
    for (native,reason),rows in sorted(incidents.items()):
        evidence=[{k:a[k] for k in ('alias_id','source_key','player_master_id','created_at')} for row in rows for a in row['alias_evidence']]
        evidence=sorted({digest(a):a for a in evidence}.values(),key=lambda a:(str(a['alias_id']),a['source_key']))
        key='package-frozen-attachment:'+native+':'+digest(dict(reason=reason,evidence=evidence))
        qid='package-native:'+digest(key)[:32];first=min(rows,key=lambda row:row['game_id']);parts=first['game_id'].split('_')
        connection.execute(text("""INSERT INTO target.identity_quarantine
        (identity_quarantine_id,entity_type,source_schema,source_table,source_record_key,source_system,season,week,slate,
         source_player_key,display_name,team_id,position,reason_code,candidate_player_ids,status,first_seen_at,updated_at)
        VALUES (:qid,'player','public','source_snapshot',:key,'nflreadpy',:season,:week,'FEATURE_INVENTORY',:native,NULL,:team,:position,:reason,CAST(:candidates AS jsonb),'open',now(),now())
        ON CONFLICT (source_schema,source_table,source_record_key) DO NOTHING"""),
            dict(qid=qid,key=key,native=native,season=int(parts[0]),week=int(parts[1]),team=first['team'],position=first['position'],
                reason='package_frozen_'+reason,candidates=json.dumps(sorted({a['player_master_id'] for a in evidence}))))
        output.append(dict(source_table='source_snapshot',source_record_key=key,intended_identity_quarantine_id=qid,source_player_key=native,
            reason=reason,native_game_ids=sorted({row['game_id'] for row in rows}),original_alias_evidence=evidence))
    return dict(records=output,requests=len(output),source_refs=source_refs,
        policy='Append-only evidence-specific frozen attachment request; DO NOTHING preserves existing/resolved rows; no alias/master mutation or current missing-alias assertion')


PHYSICAL_FIELDS=('game_id','play_id','season','week','season_type','posteam','defteam','play_type','play_type_nfl',
    'no_play','quarter_end','desc','fumble','pass_attempt','rush_attempt','sack','qb_dropback','qb_spike','qb_kneel','qb_scramble','two_point_attempt')


def load_package_physical_source(descriptor,*,season,cutoff,max_bytes=64*1024*1024,max_rows=100000):
    """One bounded minimal projection of original immutable PBP, no parent inflation."""
    from pathlib import Path
    from datetime import datetime,UTC
    import hashlib,math
    import pyarrow.parquet as pq
    from .factual_designation import clock
    entry=descriptor['manifest'];path=Path(descriptor['path']);read=clock(cutoff);received=clock(entry.get('received_at'))
    if type(season) is not int or season not in (2023,2024,2025) or entry.get('url')!=f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet':
        raise ValueError('Explicit historical native PBP URI required')
    if read is None or received is None or not received<=read<=datetime.now(UTC):raise ValueError('Actual original receipt/read chronology required')
    if path.stat().st_size!=entry['bytes'] or not 0<entry['bytes']<=max_bytes:raise ValueError('Original PBP byte bound differs')
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
    if h.hexdigest()!=entry['sha256']:raise ValueError('Original PBP bytes changed')
    file=pq.ParquetFile(path);available=set(file.schema_arrow.names)
    required={'game_id','play_id','season','week','season_type','posteam','defteam','play_type','play_type_nfl','pass_attempt','rush_attempt','sack','two_point_attempt'}
    if not required<=available or file.metadata.num_rows>max_rows:raise ValueError('Minimal physical source schema/row bound differs')
    rows=[]
    for raw in file.read(columns=[field for field in PHYSICAL_FIELDS if field in available]).to_pylist():
        raw={k:None if isinstance(v,float) and not math.isfinite(v) else v for k,v in raw.items()}
        if raw['season_type']!='REG':continue
        if _int(raw['season'])!=season:raise ValueError('Native PBP season contradicts original URI')
        rows.append(raw)
    return rows,dict(original_descriptor=descriptor,source_sha256=h.hexdigest(),source_total_rows=file.metadata.num_rows,
        scoped_REG_rows=len(rows),field_availability={field:field in available for field in PHYSICAL_FIELDS},actual_read_at=read.isoformat(),
        original_historical_availability='Later revised historical capture, not original pregame proof')


PHYSICAL_VERSION='package_physical_flags_v1'


def load_package_physical_component(ref,*,cutoff,directory=None):
    """Reuse the exact published minimal flags rather than reread original Parquet."""
    from pathlib import Path
    from datetime import datetime,UTC
    import hashlib,json
    from .factual_designation import clock
    path=Path(ref['path']).resolve();root=Path(directory or 'artifacts/package_physical_flags').resolve();boundary=clock(cutoff)
    raw=path.read_bytes()
    if path.parent!=root or path.name!=ref['sha256']+'.json' or len(raw)!=ref['bytes'] or len(raw)>64*1024*1024 or hashlib.sha256(raw).hexdigest()!=ref['sha256']:
        raise ValueError('Exact immutable physical-flag component required')
    block=json.loads(raw);provenance=block['provenance']
    if block.get('version')!=PHYSICAL_VERSION or block.get('pregame_serving_eligible') is not False or block.get('season') not in (2023,2024,2025):
        raise ValueError('Historical physical-flag scope required')
    if boundary is None or boundary>datetime.now(UTC) or not clock(provenance['original_descriptor']['manifest']['received_at'])<=clock(provenance['actual_read_at'])<=clock(provenance['actual_publication_at'])<=boundary:
        raise ValueError('Original/component publication clock proof required')
    if provenance['producer_code_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest():raise ValueError('Physical-flag producer changed')
    core={k:v for k,v in block.items() if k not in ('semantic_sha256','provenance')}
    if digest(core)!=block['semantic_sha256'] or block['source_rows']!=len(block['rows']):raise ValueError('Physical-flag semantic/cardinality proof differs')
    return block
