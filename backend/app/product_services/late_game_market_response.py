"""Observed archived-line context and preplay late-game response, no forecast."""
from collections import defaultdict
from .late_half_possession_context import _candidate,_touchdown,_and,MATERIAL
from .drive_scoring_range import _half,_control,_physical_source,VERSION as RANGE_VERSION,LIVE
from .turnover_drive_start_context import _order
from .original_drive_field_context import _integer
from .fumble_event_components import _flag
from .defense_context_evidence import _number
from .market_snapshots import canonical_team
from .workload_market_contexts import MARKET_VERSION
from .evaluation_record import digest

VERSION='late_game_market_response_v1'
GROUPS=('favorite','underdog','pickem');STATES=('ahead','tied','behind')
SOURCE_FIELDS=set(LIVE)|set(MATERIAL)|{'game_id','play_id','season','week','season_type','posteam','defteam','drive','order_sequence','game_half','qtr','half_seconds_remaining','no_play','play_type','play_type_nfl','quarter_end','desc','posteam_score','defteam_score','score_differential'}


def project_late_market_source(r):return {k:r[k]if r[k]!=''else None for k in SOURCE_FIELDS&set(r)}


def _late4(r):
    q=_integer(r.get('qtr'));seconds=_number(r.get('half_seconds_remaining'))
    if q is not None and q!=4:return False
    if q is None or _half(r)!='Half2'or seconds is None or not 0<=seconds<=900:return None
    return seconds<=300


def _score(r,team):
    own,other,diff=(_number(r.get(k))for k in('posteam_score','defteam_score','score_differential'))
    pair={canonical_team(t)for t in r['game_id'].split('_')[2:]};off=canonical_team(r['posteam'])if r.get('posteam')else None;defense=canonical_team(r['defteam'])if r.get('defteam')else None
    if off!=team or defense not in pair or defense==off or any(v is None or v!=int(v)for v in(own,other,diff))or own<0 or other<0 or own-other!=diff:return None
    return 'ahead'if diff>0 else'behind'if diff<0 else'tied'


def _physical(r):
    named,conflict=_control(r)
    return None if named and(conflict or any(_flag(r.get(k))is True for k in MATERIAL))else _physical_source(r)


def _kind(r):
    drop,rush,scramble,kneel,spike=(_flag(r.get(k))for k in('qb_dropback','rush_attempt','qb_scramble','qb_kneel','qb_spike'))
    if drop is True:
        if kneel is True or rush is True and scramble is False:return None
        return 'dropback'
    if drop is False and rush is True and scramble is False and spike is not True:return 'rush'
    return None


def _play_cell():return dict(known_opportunities=0,unknown_membership=0,dropbacks=0,rushes=0,unknown_type=0,kneels=0,unknown_kneels=0)
def _drive_cell():return dict(known_possessions=0,unknown_membership=0,TD=0,unknown_TD=0,FG=0,unknown_FG=0)
def _table(factory):return {(g,s):factory()for g in GROUPS for s in STATES}


def _finish(c,drive=False):
    c=dict(c);n=c['known_possessions'if drive else'known_opportunities'];u=c['unknown_membership']
    if drive:
        for f in('TD','FG'):
            unknown=c['unknown_'+f];c[f+'_fraction']=c[f]/n if n and not u and not unknown else None
            c['known_sample_'+f+'_fraction']=c[f]/(n-unknown)if n>unknown else None
    else:
        for f in('dropbacks','rushes'):
            c[f+'_fraction']=c[f]/n if n and not u and not c['unknown_type']else None
            c['known_sample_'+f+'_fraction']=c[f]/(n-c['unknown_type'])if n>c['unknown_type']else None
        c['kneel_fraction']=c['kneels']/n if n and not u and not c['unknown_kneels']else None
        c['known_sample_kneel_fraction']=c['kneels']/(n-c['unknown_kneels'])if n>c['unknown_kneels']else None
    return c


def _contrasts(table,drive=False):
    fields=('TD_fraction','FG_fraction')if drive else('dropbacks_fraction','rushes_fraction','kneel_fraction')
    out=[]
    for score in STATES:
        a,b=table[('favorite',score)],table[('underdog',score)]
        out.append(dict(comparison='favorite_minus_underdog',score_state=score,values={f:a[f]-b[f]if a[f]is not None and b[f]is not None else None for f in fields}))
    for market in GROUPS:
        a,b=table[(market,'ahead')],table[(market,'behind')]
        out.append(dict(comparison='ahead_minus_behind',market_group=market,values={f:a[f]-b[f]if a[f]is not None and b[f]is not None else None for f in fields}))
    return out


def build_late_game_market_response(records,boundaries,market):
    before=boundaries['before_period']
    if boundaries.get('version')!=RANGE_VERSION or market.get('version')!=MARKET_VERSION or market.get('before_period')!=before or any(x.get('pregame_serving_eligible')is not False for x in(boundaries,market)):raise ValueError('Matched reviewed nonserving source scopes required')
    markets={};market_spreads=defaultdict(list);parents={};timeline=defaultdict(list);index={};bad=set();source_sides=set()
    for r in market['rows']:
        key=(r['game_id'],r['team']);parts=r['game_id'].split('_')
        if key in markets or parts[:2]!=[str(r['season']),f"{r['week']:02d}"]or r['team']not in{canonical_team(t)for t in parts[2:]}:raise ValueError('Unique native market side/period required')
        spread=_number(r['team_spread_line'])
        if spread is not None and abs(spread)>30:raise ValueError('Signed archived teamspread out of bounds')
        market_spreads[r['game_id']].append(spread)
        markets[key]='favorite'if spread is not None and spread<0 else'underdog'if spread is not None and spread>0 else'pickem'if spread==0 else None
    for values in market_spreads.values():
        if len(values)==2 and all(v is not None for v in values)and values[0]!=-values[1]:raise ValueError('Opposing canonical teamspreads must have opposite signs')
    for g in boundaries['game_rows']:
        key=(g['native_game_id'],g['team'])
        if key in parents:raise ValueError('Unique original offense-game required')
        parents[key]=g
    plays={key:_table(_play_cell)for key in parents};drives={key:_table(_drive_cell)for key in parents};events=[];drive_rows=[];unassigned=[]
    def targets(gid,off,group,state):
        for team in({off}if off else{canonical_team(t)for t in gid.split('_')[2:]}):
            if(gid,team)not in parents:continue
            mg=markets.get((gid,team))if group is None or team!=off else group
            for pair in plays[(gid,team)]:
                if(mg is None or pair[0]==mg)and(state is None or pair[1]==state):yield team,pair
    for r in records:
        if r.get('season_type')!='REG':continue
        y,w=_integer(r.get('season')),_integer(r.get('week'));gid=r['game_id'];pid=_integer(r.get('play_id'))
        if y is None or w is None or not 1<=w<=18 or gid.split('_')[:2]!=[str(y),f'{w:02d}']or pid is None:raise ValueError('Native source game-period-play required')
        if y*100+w>=before:continue
        key=(gid,pid)
        if key in index:raise ValueError('Unique native source play required')
        index[key]=r;timeline[gid].append(r)
        if _order(r.get('order_sequence'))is None:bad.add(gid)
        pair={canonical_team(t)for t in gid.split('_')[2:]};off=canonical_team(r['posteam'])if r.get('posteam')else None
        if len(gid.split('_'))!=4 or len(pair)!=2 or off is not None and off not in pair:raise ValueError('Native offense outside unique game pair')
        if off is not None:source_sides.add((gid,off))
        membership=_and(_physical(r),_late4(r))
        if membership is False:continue
        group=markets.get((gid,off));state=_score(r,off)if off else None;kind=_kind(r);kneel=_flag(r.get('qb_kneel'))
        event=dict(game_id=gid,play_id=pid,offense=off,late_physical_membership=membership,market_group=group,preplay_score_state=state,physical_type=kind,qb_kneel=kneel)
        events.append(event)
        for team,cell_key in targets(gid,off,group,state):
            c=plays[(gid,team)][cell_key]
            if membership is not True or off is None or group is None or state is None:c['unknown_membership']+=1;continue
            c['known_opportunities']+=1
            if kind is None:c['unknown_type']+=1
            else:c['dropbacks'if kind=='dropback'else'rushes']+=1
            if kneel is None or kneel is True and kind!='rush':c['unknown_kneels']+=1
            else:c['kneels']+=int(kneel)
    for gid,rs in timeline.items():
        os=[_order(r.get('order_sequence'))for r in rs]
        if len(os)!=len(set(os)):bad.add(gid)
        if gid not in bad:rs.sort(key=lambda r:_order(r['order_sequence']))
    for(gid,team),g in parents.items():
        if(gid,team)not in source_sides:
            for table in(plays[(gid,team)],drives[(gid,team)]):
                for c in table.values():c['unknown_membership']+=1
        if not g['drives']:
            for c in drives[(gid,team)].values():c['unknown_membership']+=1
        for d in g['drives']:
            did=d['original_drive_id'];own=[r for r in timeline[gid]if r.get('posteam')and canonical_team(r['posteam'])==team and _integer(r.get('drive'))==did]
            conditions=[(r,_and(_candidate(r),_late4(r)))for r in own];known=[r for r,v in conditions if v is True];unknown=[r for r,v in conditions if v is None]
            first=min(known,key=lambda r:_order(r['order_sequence']))if known and gid not in bad else None
            proven_first=bool(first and not any(_order(r.get('order_sequence'))<=_order(first['order_sequence'])for r in unknown))
            boundary_rows_present=(gid,d['source_first_play_id'])in index and(gid,d['source_last_play_id'])in index
            entry=True if first else None if unknown or gid in bad or not d['native_boundary_and_cohort_verified']or not boundary_rows_present else False
            group=markets.get((gid,team));state=_score(first,team)if proven_first else None;TD=None;FG=None;barriers=[]
            if first:
                eo=_order(first['order_sequence']);last=index.get((gid,d['source_last_play_id']));end=_order(last.get('order_sequence'))if last else None
                source_first=index.get((gid,d['source_first_play_id']));start=_order(source_first.get('order_sequence'))if source_first else None
                unsafe=bool(unknown or start is None or end is None or not start<=eo<=end or not d['native_boundary_and_cohort_verified']);blocked=False;td=[];fg=[]
                if end is not None:
                    for r in timeline[gid]:
                        order=_order(r['order_sequence'])
                        if not eo<=order<=end:continue
                        named,conflict=_control(r);off=canonical_team(r['posteam'])if r.get('posteam')else None
                        material=conflict or named and any(_flag(r.get(k))is True for k in MATERIAL)
                        if material or _half(r)!='Half2'or _integer(r.get('drive'))!=did or _candidate(r)is not False and off!=team:
                            blocked=True;unsafe=True;barriers.append(_integer(r['play_id']))
                        if blocked:continue
                        m=_and(_candidate(r),_late4(r));td.append(_and(m,_touchdown(r)))
                        flag=_flag(r.get('field_goal_attempt'));attempt=None if flag is True and r.get('play_type')!='field_goal'else False if r.get('play_type')!='field_goal'else flag
                        fg.append(_and(m,attempt))
                terminal=bool(not unsafe and end is not None and end>=eo and d['verified_terminal_class']is not None)
                TD=True if True in td else False if terminal and all(v is False for v in td)else None
                FG=True if True in fg else False if terminal and all(v is False for v in fg)else None
            drive_rows.append(dict(game_id=gid,team=team,original_drive_id=did,late_entry=entry,first_known_late_play_id=_integer(first['play_id'])if first else None,first_late_play_id=_integer(first['play_id'])if proven_first else None,entry_market_group=group,entry_preplay_score_state=state,offensive_TD=TD,live_FG_attempt=FG,continuity_barrier_play_ids=barriers))
            if entry is False:continue
            for target,cell_key in targets(gid,team,group,state):
                c=drives[(gid,target)][cell_key]
                if entry is not True or group is None or state is None:c['unknown_membership']+=1;continue
                c['known_possessions']+=1
                for f,v in(('TD',TD),('FG',FG)):
                    if v is None:c['unknown_'+f]+=1
                    else:c[f]+=int(v)
    # Possible late candidate rows without a certified original cohort affect every compatible drive cell.
    for(gid,pid),r in index.items():
        m=_and(_candidate(r),_late4(r));off=canonical_team(r['posteam'])if r.get('posteam')else None;did=_integer(r.get('drive'))
        if m is False:continue
        exists=off is not None and(gid,off)in parents and any(d['original_drive_id']==did for d in parents[(gid,off)]['drives'])
        if exists:continue
        unassigned.append(dict(game_id=gid,play_id=pid,offense=off,original_drive_id=did))
        for team,cell_key in targets(gid,off,markets.get((gid,off)),_score(r,off)if off else None):drives[(gid,team)][cell_key]['unknown_membership']+=1
    game_rows=[];grouped=defaultdict(list)
    for key,g in sorted(parents.items()):
        p={k:_finish(v)for k,v in plays[key].items()};d={k:_finish(v,True)for k,v in drives[key].items()}
        row=dict(game_id=key[0],team=key[1],season=g['season'],week=g['week'],play_cells=[dict(market_group=k[0],score_state=k[1],**v)for k,v in p.items()],drive_cells=[dict(market_group=k[0],score_state=k[1],**v)for k,v in d.items()],play_contrasts=_contrasts(p),drive_contrasts=_contrasts(d,True));game_rows.append(row);grouped[(g['season'],key[1])].append(key)
    profiles=[]
    for(year,team),keys in sorted(grouped.items()):
        p={k:_finish({f:sum(plays[key][k][f]for key in keys)for f in _play_cell()})for k in _table(_play_cell)};d={k:_finish({f:sum(drives[key][k][f]for key in keys)for f in _drive_cell()},True)for k in _table(_drive_cell)}
        profiles.append(dict(season=year,team=team,observed_game_ids=[k[0]for k in keys],play_cells=[dict(market_group=k[0],score_state=k[1],**v)for k,v in p.items()],drive_cells=[dict(market_group=k[0],score_state=k[1],**v)for k,v in d.items()],play_contrasts=_contrasts(p),drive_contrasts=_contrasts(d,True)))
    core=dict(version=VERSION,candidate_id='X05-M10',before_period=before,game_rows=game_rows,profiles=profiles,event_basis=events,drive_basis=drive_rows,unassigned_drive_incidents=unassigned,
        definition='Archived intended favorite/underdog/pickem versus q4/Half2<=300s preplay ahead/tied/behind physical-play fractions and first-entry-context frozen ORIGINAL-drive TD/FG paths; separate denominators')
    return dict(**core,semantic_sha256=digest(core),pregame_serving_eligible=False,forecast=None,models_or_optimizer_consumed=False,
        limitations=['Realized preplay score context, not final/postplay score; no counterfactual motivation/causal sensitivity','Drive context frozen at first qualifying entry; each original drive counted once, play and drive units separate','Unknown source lines/score/side/clock/eligibility/entry/terminal retain compatible-cell masks and samples','Revised archived intended lines/original quote availability unknown; no current forecast/model/serving claim'])
