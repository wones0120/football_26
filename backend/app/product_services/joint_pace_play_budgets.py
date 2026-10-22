"""Observed unique-game joint play budgets versus both strictly prior pace axes."""
from collections import defaultdict
from copy import deepcopy
import math
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .game_clock_pace_catalog import VERSION as PACE_VERSION
from .shared_game_covariance import VERSION as PAIR_VERSION

VERSION='joint_pace_play_budgets_v1'
GROUPS=('fast','slow')


def _number(v,integer=False):
    if isinstance(v,bool)or not isinstance(v,(int,float))or not math.isfinite(v)or v<0 or(integer and int(v)!=v):raise ValueError('Nonnegative finite native measurement required')
    return v


def _pool(logs,pace):
    seconds=0.;exposures=0;unknown=[];known=[]
    for gid,team in logs:
        metric=pace.get((gid,team));valid=metric is not None
        if valid:
            for k in('known_outcome_events','unknown_outcome_events','unknown_eligibility_events','eligible_events'):_number(metric[k],True)
            if metric['eligible_events']!=metric['known_outcome_events']+metric['unknown_outcome_events']:raise ValueError('Pace exposure partition differs')
            if metric['observed_outcome_sum']is not None:_number(metric['observed_outcome_sum'])
            valid=metric.get('native_order_verified')is True and not(metric['unknown_outcome_events']or metric['unknown_eligibility_events'])and metric['known_outcome_events']>0 and metric['observed_outcome_sum']is not None
            if valid and metric['value']!=metric['observed_outcome_sum']/metric['known_outcome_events']:raise ValueError('Exact pace value differs from pooled source quantities')
        if not valid:unknown.append(gid);continue
        seconds+=metric['observed_outcome_sum'];exposures+=metric['known_outcome_events'];known.append(gid)
    value=seconds/exposures if exposures else None
    return dict(scheduled_game_ids=[g for g,t in logs],known_game_ids=known,unknown_game_ids=unknown,known_elapsed_seconds=seconds,known_interval_exposures=exposures,known_sample_seconds_per_interval=value,exact_seconds_per_interval=value if logs and not unknown else None)


def _quantile(values,q):
    if not values:return None
    values=sorted(values);at=(len(values)-1)*q;lo=math.floor(at);hi=math.ceil(at)
    return values[lo]+(values[hi]-values[lo])*(at-lo)


def _group(value,low,high):
    if value is None or low is None or high is None or low==high:return None
    return 'fast'if value<=low else'slow'if value>=high else'middle'


def _moments(values):
    n=len(values)
    if not n:return dict(games=0,home_mean=None,away_mean=None,joint_total_mean=None,population_covariance=None,paired_cross_moment=None,independence_marginal_product=None)
    hm=sum(v[0]for v in values)/n;am=sum(v[1]for v in values)/n
    return dict(games=n,home_mean=hm,away_mean=am,joint_total_mean=hm+am,population_covariance=sum((x-hm)*(y-am)for x,y in values)/n if n>=2 else None,paired_cross_moment=sum(x*y for x,y in values)/n,independence_marginal_product=hm*am)


def _cells(logs):
    result={}
    for hg in GROUPS:
        result[hg]={}
        for ag in GROUPS:
            possible=[r for r in logs if r['home_prior_group']in(None,hg)and r['away_prior_group']in(None,ag)]
            members=[r for r in possible if r['home_prior_group']==hg and r['away_prior_group']==ag]
            uncertain=[r['game_id']for r in possible if r not in members]
            sample=[r['physical_pair']for r in members if all(v is not None for v in r['physical_pair'])]
            missing=[r['game_id']for r in members if any(v is None for v in r['physical_pair'])]
            known=_moments(sample);exact=deepcopy(known)
            if uncertain or missing:
                for field in exact:
                    if field!='games':exact[field]=None
                exact['games']=None if uncertain else len(members)
            result[hg][ag]=dict(known_member_game_ids=[r['game_id']for r in members],unknown_membership_game_ids=uncertain,unknown_response_game_ids=missing,known_complete_sample=known,exact_full_cell=exact)
    contrasts={}
    for field in('home_mean','away_mean','joint_total_mean','population_covariance'):
        values=[result[h][a]['exact_full_cell'][field]for h,a in(('fast','fast'),('fast','slow'),('slow','fast'),('slow','slow'))]
        contrasts[field]=values[0]-values[1]-values[2]+values[3]if all(v is not None for v in values)else None
    conditional={}
    for axis in('home','away'):
        conditional[axis]={}
        for fixed in GROUPS:
            a,b=(result['fast'][fixed],result['slow'][fixed])if axis=='home'else(result[fixed]['fast'],result[fixed]['slow'])
            conditional[axis][fixed]={field:a['exact_full_cell'][field]-b['exact_full_cell'][field]if a['exact_full_cell'][field]is not None and b['exact_full_cell'][field]is not None else None for field in('home_mean','away_mean','joint_total_mean','population_covariance')}
    return dict(cells=result,fast_minus_slow_by_fixed_opposing_axis=conditional,both_axes_difference_of_differences=contrasts)


def build_joint_pace_play_budgets(pace,pairs,schedule,*,reference_before_week=4,last_n=8):
    if pace.get('version')!=PACE_VERSION or pairs.get('version')!=PAIR_VERSION or pace.get('pregame_serving_eligible')is not False or pairs.get('pregame_serving_eligible')is not False or pace['before_period']!=pairs['before_period']:raise ValueError('Matched reviewed nonserving pace and paired-play parents required')
    if reference_before_week!=4 or last_n!=8:raise ValueError('Predeclared W1–3 reference and prior8 recipe required')
    boundary=pace['before_period'];season=boundary//100;games=[];seen=set();team_games=defaultdict(list)
    for row in schedule:
        if row['season']!=season or row['game_type']!='REG'or row['season']*100+row['week']>=boundary:continue
        gid=row['game_id'];home=canonical_team(row['home_team']);away=canonical_team(row['away_team']);parts=gid.split('_')
        if len(parts)!=4 or parts[:2]!=[str(season),f"{row['week']:02d}"]or(canonical_team(parts[3]),canonical_team(parts[2]))!=(home,away)or home==away or gid in seen:raise ValueError('Unique native scheduled scope required')
        seen.add(gid);g=dict(game_id=gid,season=season,week=row['week'],home_team=home,away_team=away);games.append(g)
        for team in(home,away):team_games[team].append(g)
    games.sort(key=lambda g:(g['week'],g['game_id']))
    for team,logs in team_games.items():
        logs.sort(key=lambda g:(g['week'],g['game_id']))
        if len({g['week']for g in logs})!=len(logs):raise ValueError('At most one native scheduled game per team/week')
    pace_index={}
    for r in pace['game_rows']:
        key=(r['game_id'],canonical_team(r['team']))
        if key in pace_index:raise ValueError('Unique native team pace row required')
        pace_index[key]=r['metrics']['G01-M04']
    pair_index={}
    for r in pairs['game_rows']:
        if r['game_id']in pair_index:raise ValueError('Unique physical game pair required')
        pair_index[r['game_id']]=r
    references={team:_pool([(g['game_id'],team)for g in logs if g['week']<reference_before_week],pace_index)for team,logs in sorted(team_games.items())}
    reference_values=[r['exact_seconds_per_interval']for r in references.values()if r['exact_seconds_per_interval']is not None];low=_quantile(reference_values,1/3);high=_quantile(reference_values,2/3);rows=[]
    for g in games:
        contexts={}
        for team in(g['home_team'],g['away_team']):
            previous=[p for p in team_games[team]if p['week']<g['week']][-last_n:];context=_pool([(p['game_id'],team)for p in previous],pace_index);context['max_contributing_period']=max((season*100+p['week']for p in previous),default=None)
            if context['max_contributing_period']is not None and context['max_contributing_period']>=season*100+g['week']:raise ValueError('Strict prior prefix required')
            context['reference_ready']=g['week']>=reference_before_week;context['group']=_group(context['exact_seconds_per_interval'],low,high)if context['reference_ready']else None;contexts[team]=context
        pair=pair_index.get(g['game_id']);values=[None,None]
        if pair:
            if(pair['home_team'],pair['away_team'])!=(g['home_team'],g['away_team'])or pair['season']!=season or pair['week']!=g['week']:raise ValueError('Native paired-play orientation/scope differs')
            values=list(pair['values'][:2])
            for v in values:
                if v is not None:_number(v,True)
        rows.append(dict(**g,pace_contexts=contexts,home_prior_group=contexts[g['home_team']]['group'],away_prior_group=contexts[g['away_team']]['group'],physical_pair=values,joint_physical_plays=sum(values)if all(v is not None for v in values)else None))
    evaluation=[r for r in rows if r['week']>=reference_before_week];profile=_cells(evaluation)
    core=dict(version=VERSION,catalog_id='X01-M09',before_period=boundary,reference_before_week=reference_before_week,last_n_scheduled_games=last_n,reference_team_pace=references,reference_cutpoints=dict(fast_at_or_below=low,slow_at_or_above=high,known_reference_teams=len(reference_values)),game_rows=rows,evaluation_game_ids=[r['game_id']for r in evaluation],home_away_pooled_observed_profile=profile,source_semantic_sha256=dict(pace=pace['semantic_sha256'],paired_plays=pairs['semantic_sha256']),definition=dict(pace='Pooled eligible elapsed game-clock start interval seconds/exposures from G01-M04; no UTC cadence or reciprocal averaging',orientation='One unique native HOME=own/AWAY=opponent game; no swapped independent observations',reference='Fixed first3scheduled-week team pooled pace terciles; labels unavailable beforeW4; middle explicitly excluded',response='Matched physical offensive plays own/opponent and joint total; paired population covariance, crossmoment and marginal-product baseline on SAME complete cell sample',contrast='Fast-minus-slow own pace WITHIN fixed opposing pace group and vice versa; four-cell difference-of-differences separately; both axes materially consumed, home-away pooled observational context, not within-team or causal effect',unknown='Unknown prior source/game/interval or response masks compatible exact cells; known-complete samples separate; no missinggame skips'),pregame_serving_eligible=False,forecast=None)
    return dict(**core,semantic_sha256=digest(core))
