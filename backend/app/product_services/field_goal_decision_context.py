"""Third-failure opportunity response by frozen anchor range, clock and score."""
from collections import defaultdict
from itertools import product
from .third_down_decision_context import VERSION as PARENT_VERSION,CHOICES
from .late_game_market_response import _score
from .drive_scoring_range import _half
from .original_drive_field_context import _integer
from .defense_context_evidence import _number
from .market_snapshots import canonical_team
from .evaluation_record import digest

VERSION='field_goal_decision_context_v1'
RANGES=('nominal_inside35','nominal_outside35')
TIMES=('late_regulation_half_120','earlier_regulation_half','overtime')
SCORES=('ahead','tied','behind')
CATEGORIES=(*CHOICES,'verified_clock_end_before_next_decision','typed_possession_end_before_next_decision','explicit_penalty_new_series','observed_new_or_repeated_down')
SOURCE_FIELDS=('game_id','play_id','season','week','season_type','posteam','defteam','game_half','qtr','half_seconds_remaining','yardline_100','posteam_score','defteam_score','score_differential')


def project_context_source(row):return {k:None if row[k]=='' else row[k] for k in SOURCE_FIELDS if k in row}


def _time_band(raw):
    half=_half(raw);qtr=_integer(raw.get('qtr'));seconds=_number(raw.get('half_seconds_remaining'))
    if half=='Overtime':return 'overtime'  # No invented regulation half clock for OT.
    if half not in {'Half1','Half2'} or seconds is None:return None
    lower,upper=(900,1800) if qtr in {1,3} else (0,900)
    if not lower<=seconds<=upper:return None
    return 'late_regulation_half_120' if seconds<=120 else 'earlier_regulation_half'


def _context(raw,team):
    if raw is None:return (None,None,None)
    line=_number(raw.get('yardline_100'))
    band=('nominal_inside35' if line<=35 else 'nominal_outside35') if line is not None and 0<=line<=100 else None
    return band,_time_band(raw),_score(raw,team)


def _cell():return dict(known_anchor_members=0,unknown_membership=0,unknown_outcomes=0,known_outcomes={c:0 for c in CATEGORIES})
def _table():return {key:_cell() for key in product(RANGES,TIMES,SCORES)}


def _add(table,context,eligible,outcome):
    for key,cell in table.items():
        if any(value is not None and value!=expected for value,expected in zip(context,key)):continue
        if eligible is not True or None in context:cell['unknown_membership']+=1
        else:
            cell['known_anchor_members']+=1
            if outcome is None:cell['unknown_outcomes']+=1
            else:cell['known_outcomes'][outcome]+=1


def _finish(table):
    rows=[]
    for key,c in table.items():
        n=c['known_anchor_members'];known=sum(c['known_outcomes'].values());choice=sum(c['known_outcomes'][name] for name in CHOICES)
        complete=not c['unknown_membership'] and not c['unknown_outcomes']
        rows.append(dict(nominal_field_site=key[0],clock_band=key[1],preanchor_score_state=key[2],**c,
            all_anchor_denominator=n if not c['unknown_membership'] else None,
            all_anchor_frequencies={name:c['known_outcomes'][name]/n for name in CATEGORIES} if complete and n else None,
            known_outcome_sample_frequencies={name:c['known_outcomes'][name]/known for name in CATEGORIES} if known else None,
            choice_only_sample_frequencies={name:c['known_outcomes'][name]/choice for name in CHOICES} if choice else None,
            exact_choice_only_frequencies={name:c['known_outcomes'][name]/choice for name in CHOICES} if complete and choice else None,
            empty_observed_cell=not n and not c['unknown_membership']))
    return rows


def _contrasts(cells):
    index={(c['nominal_field_site'],c['clock_band'],c['preanchor_score_state']):c for c in cells};results=[]
    pairs=[]
    for time,score in product(TIMES,SCORES):pairs.append(('inside35_minus_outside35',('nominal_inside35',time,score),('nominal_outside35',time,score)))
    for band,score in product(RANGES,SCORES):pairs.append(('late120_minus_earlier_regulation',(band,'late_regulation_half_120',score),(band,'earlier_regulation_half',score)))
    for label,a,b in pairs:
        left,right=index[a],index[b];values={}
        for name in CATEGORIES:
            x,y=left['all_anchor_frequencies'],right['all_anchor_frequencies']
            values[name]=x[name]-y[name] if x is not None and y is not None else None
        results.append(dict(contrast=label,left_context=list(a),right_context=list(b),all_anchor_frequency_differences=values))
    return results


def build_field_goal_decision_context(records,parent):
    if parent.get('version')!=PARENT_VERSION or parent.get('candidate_id')!='X05-M08' or parent.get('pregame_serving_eligible') is not False:
        raise ValueError('Reviewed failed-third anchor/competing-outcome family required')
    before=parent['before_period'];lookup={}
    for raw in records:
        if raw.get('season_type')!='REG':continue
        year,week=_integer(raw.get('season')),_integer(raw.get('week'));gid=raw.get('game_id');play=_integer(raw.get('play_id'))
        if year is None or week is None or not 1<=week<=18 or not isinstance(gid,str) or play is None:raise ValueError('Native context scope required')
        if year*100+week>=before:continue
        parts=gid.split('_')
        if len(parts)!=4 or parts[:2]!=[str(year),f'{week:02d}']:raise ValueError('Native context period/game differs')
        key=(gid,play)
        if key in lookup:raise ValueError('Unique native context play required')
        lookup[key]=raw
    games=[];profile_tables={};profile_gids=defaultdict(list);basis=[];seen_sides=set()
    for game in parent['game_rows']:
        gid,team=game['native_game_id'],game['team'];side=(gid,team)
        if side in seen_sides or team not in {canonical_team(t) for t in gid.split('_')[2:]}:raise ValueError('Unique native parent offense side required')
        seen_sides.add(side);table=_table();seen=set()
        for eligible,anchors in ((True,game['third_failure_anchors']),(None,game['unknown_possible_anchor_rows'])):
            for anchor in anchors:
                play=anchor.get('anchor_play_id') if eligible else anchor.get('play_id');key=(gid,_integer(play))
                if key in seen or anchor.get('native_game_id')!=gid:raise ValueError('Unique same-game native parent anchor required')
                seen.add(key);raw=lookup.get(key)
                if raw is not None:
                    off=canonical_team(raw['posteam']) if raw.get('posteam') else None
                    if off is not None and off!=team:raise ValueError('Context offense contradicts parent anchor')
                    if (int(raw['season']),int(raw['week']))!=(game['season'],game['week']):raise ValueError('Context native period contradicts parent')
                    if eligible and (off!=team or _half(raw)!=anchor['recognized_half']):raise ValueError('Known anchor side/half binding differs')
                context=_context(raw,team);outcome=anchor.get('outcome_category') if eligible else None
                if outcome is not None and outcome not in CATEGORIES:raise ValueError('Unknown parent categorical outcome')
                _add(table,context,eligible,outcome)
                basis.append(dict(native_game_id=gid,team=team,anchor_play_id=play,eligible_anchor=eligible,
                    preanchor_context=list(context),source_context=raw,parent_anchor=anchor))
        cells=_finish(table);games.append(dict(native_game_id=gid,team=team,season=game['season'],week=game['week'],cells=cells,contrasts=_contrasts(cells)))
        pkey=(game['season'],team);pooled=profile_tables.setdefault(pkey,_table());profile_gids[pkey].append(gid)
        for key,c in table.items():
            for field in ('known_anchor_members','unknown_membership','unknown_outcomes'):pooled[key][field]+=c[field]
            for outcome,n in c['known_outcomes'].items():pooled[key]['known_outcomes'][outcome]+=n
    unbound=parent.get('unbound_native_offense_sides',[])
    for gid,team in unbound:
        season=int(gid.split('_')[0]);pooled=profile_tables.setdefault((season,team),_table())
        for c in pooled.values():c['unknown_membership']+=1
    profiles=[]
    for (season,team),table in sorted(profile_tables.items()):
        cells=_finish(table);profiles.append(dict(season=season,team=team,observed_game_ids=profile_gids[season,team],cells=cells,contrasts=_contrasts(cells)))
    core=dict(version=VERSION,candidate_ids=['X06-M04'],before_period=before,game_rows=games,profiles=profiles,
        anchor_basis=basis,unbound_native_offense_sides=unbound,
        definitions=dict(cohort='Each observed failed-third opportunity/series, not all field-goal decisions',
            nominal_site='Frozen PRE-ANCHOR yardline_100<=35 versus>35; not actual kick distance or later decision/end location',
            clock='Frozen pre-anchor recognized regulation half: <=120s versus earlier; known OT has its own band without a fabricated half clock',
            score='Frozen corroborated pre-anchor offense/defense score differential, never final or postplay score',
            full_denominator='All eligible failed-third anchors in matched context; unknown membership/outcomes mask full categorical frequencies',
            choice_sample='FG/punt/physicalfourth choices only, separately named conditional sample',
            pooling='Sum matched context anchor/outcome counts across identical observed native game windows before division'))
    return dict(**core,semantic_sha256=digest(core),model_consumed=False,optimizer_consumed=False,pregame_serving_eligible=False,
        evidence_use='observed_third_failure_context_response_not_kicker_ability_aggression_causal_or_forecast')


def load_reviewed_third_failure_context(ref,*,cutoff):
    from pathlib import Path
    from datetime import datetime,UTC
    import json,hashlib
    from . import third_down_decision_context
    from .factual_designation import clock
    p=Path(ref['path']).resolve();actual=clock(cutoff)
    if p.parent!=Path('artifacts/third_down_decision_context').resolve() or p.name!=ref['sha256']+'.json' or not 0<ref['bytes']<=4*1024*1024:raise ValueError('Managed bounded reviewed failed-third evidence required')
    raw=p.read_bytes()
    if len(raw)!=ref['bytes'] or hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('Failed-third bytes differ')
    x=json.loads(raw);pr=x['provenance'];published=clock(pr.get('actual_publication_at'))
    if actual is None or actual>datetime.now(UTC) or published is None or published>actual:raise ValueError('Failed-third publication unavailable')
    if x.get('version')!=PARENT_VERSION or x.get('candidate_id')!='X05-M08' or x.get('pregame_serving_eligible')is not False or x.get('forecast')is not None or pr.get('producer_code_sha256')!=hashlib.sha256(Path(third_down_decision_context.__file__).read_bytes()).hexdigest():raise ValueError('Reviewed failed-third producer/version/use differs')
    keys=('version','candidate_id','before_period','game_rows','team_profiles','unknown_native_anchor_incidents','unbound_native_offense_sides','definitions')
    if x['semantic_sha256']!=digest({k:x[k] for k in keys}):raise ValueError('Failed-third semantic core differs')
    return x
