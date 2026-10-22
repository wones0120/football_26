"""Observed paired physical plays and completed whole-team real scores.

Common-game clock exposure is not an identified causal clock effect or a future
joint law. Swapped team views never increase the unique global game sample.
"""
from collections import defaultdict
from copy import deepcopy
import math
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .offensive_environment_catalog import VERSION as PLAYS_VERSION
from .scoreboard_result_features import VERSION as SCORES_VERSION

VERSION='shared_game_covariance_v1'
AXES=('own_physical_offensive_plays','opponent_physical_offensive_plays','own_completed_TEAM_real_points','opponent_completed_TEAM_real_points')


def _count(value):
    if value is None:return None
    if isinstance(value,bool):raise ValueError('Nonnegative integer measurement required')
    try:n=float(value)
    except(TypeError,ValueError):raise ValueError('Nonnegative integer measurement required')
    if not math.isfinite(n)or n<0 or n!=int(n):raise ValueError('Nonnegative integer measurement required')
    return int(n)


def _moments(samples):
    n=len(samples)
    if not n:return dict(games=0,means=None,observed_cross_moments=None,independence_marginal_products=None,population_covariance=None,correlation=None)
    means={axis:sum(v[i]for v in samples)/n for i,axis in enumerate(AXES)}
    moments={};baseline={};cov={};corr={}
    for i,a in enumerate(AXES):
        moments[a]={};baseline[a]={};cov[a]={}
        for j,b in enumerate(AXES):
            moments[a][b]=sum(v[i]*v[j]for v in samples)/n;baseline[a][b]=means[a]*means[b]
            cov[a][b]=sum((v[i]-means[a])*(v[j]-means[b])for v in samples)/n
    for a in AXES:
        corr[a]={}
        for b in AXES:
            scale=cov[a][a]*cov[b][b]
            corr[a][b]=cov[a][b]/math.sqrt(scale)if scale>0 else None
    return dict(games=n,means=means,observed_cross_moments=moments,independence_marginal_products=baseline,population_covariance=cov,correlation=corr)


def _profile(logs):
    complete=[r['values']for r in logs if all(x is not None for x in r['values'])];known=_moments(complete);unknown=[r['game_id']for r in logs if any(x is None for x in r['values'])]
    exact=deepcopy(known);exact['games']=len(logs)
    if unknown:
        for field in('means','observed_cross_moments','independence_marginal_products','population_covariance','correlation'):exact[field]=None
    return dict(observed_games=len(logs),unique_game_ids=[r['game_id']for r in logs],known_complete_game_ids=[r['game_id']for r in logs if all(x is not None for x in r['values'])],unknown_pair_game_ids=unknown,
        known_complete_sample=known,exact_full_observed_cohort=exact,unknown_axes={a:sum(r['values'][i]is None for r in logs)for i,a in enumerate(AXES)})


def build_shared_game_covariance(plays,scores):
    if plays.get('version')!=PLAYS_VERSION or scores.get('version')!=SCORES_VERSION or plays.get('pregame_serving_eligible')is not False or scores.get('pregame_serving_eligible')is not False:raise ValueError('Reviewed nonserving paired source types required')
    boundary=plays['before_period']
    if boundary!=scores['before_period']:raise ValueError('Matched source strict boundary required')
    physical={};score_index={};gids=set()
    for row in plays['game_rows']:
        gid=row['game_id'];parts=gid.split('_');team=canonical_team(row['team']);key=(gid,team)
        if len(parts)!=4 or key in physical or team not in{canonical_team(t)for t in parts[2:]}:raise ValueError('Unique native physical game/side required')
        m=row['metrics']['G01-M01'];unknown=_count(m['unknown_eligibility']);lower=_count(m['known_lower_bound']);value=_count(m['value'])
        if unknown is None or lower is None or(unknown>0 and value is not None)or(value is not None and value!=lower):raise ValueError('Physical exact versus unknown count contract differs')
        if row['period']!=int(parts[0])*100+int(parts[1]):raise ValueError('Native physical period differs')
        physical[key]=dict(value=value,known_lower_bound=lower,unknown_eligibility=unknown);gids.add(gid)
    for row in scores['game_rows']:
        gid=row['game_id'];parts=gid.split('_')
        if len(parts)!=4 or gid in score_index or(canonical_team(parts[3]),canonical_team(parts[2]))!=(row['home_team'],row['away_team']):raise ValueError('Unique completed native game/home-away required')
        if row['season']!=int(parts[0])or row['week']!=int(parts[1]):raise ValueError('Native score period differs')
        value=row['exact_completed_score']
        if value is not None:
            if len(value)!=2 or any(v is None for v in value):raise ValueError('Both exact completed team scores required')
            value=tuple(_count(v)for v in value)
        score_index[gid]=dict(values=value,unknown_reason=row.get('unknown_reason'));gids.add(gid)
    games=[];teams=defaultdict(list);seasons=defaultdict(list)
    for gid in sorted(gids):
        parts=gid.split('_');season=int(parts[0]);week=int(parts[1]);home,away=canonical_team(parts[3]),canonical_team(parts[2])
        if len({home,away})!=2 or not 1<=week<=18 or season*100+week>=boundary:raise ValueError('Strict prior native REG game scope required')
        source=score_index.get(gid);score=source['values']if source else None
        hp=physical.get((gid,home));ap=physical.get((gid,away));points=(score[0],score[1])if score is not None else(None,None)
        values=[hp['value']if hp else None,ap['value']if ap else None,*points]
        game=dict(game_id=gid,season=season,week=week,home_team=home,away_team=away,values=values,
            physical_source_sides={home:deepcopy(hp),away:deepcopy(ap)},score_source_present=source is not None,completed_score_unknown_reason=source['unknown_reason']if source else'Missing completed score source game',
            orientation='Own=HOME/opponent=AWAY in unique global cohort, matching provider native away_home game key and completed scoreboard')
        games.append(game);seasons[season].append(game)
        for team,opponent,vector in((home,away,values),(away,home,[values[1],values[0],values[3],values[2]])):
            teams[(season,team)].append(dict(game_id=gid,opponent=opponent,values=vector))
    profiles=[dict(season=season,team=team,orientation='Own=declared team/opponent=other native side, one observation per unique game',logs=logs,**_profile(logs))for(season,team),logs in sorted(teams.items())]
    global_profiles=[dict(season=season,orientation='Own=HOME/opponent=AWAY; never add swapped team views as new global samples',**_profile(logs))for season,logs in sorted(seasons.items())]
    core=dict(version=VERSION,catalog_id='X07-M04',before_period=boundary,axes=AXES,game_rows=games,team_season_profiles=profiles,global_season_profiles=global_profiles,
        definition=dict(plays='Source exact physical offensive snap union once, including sacks/spikes/kneels; no sum of overlapping dropback/rush channels',
            scores='Explicit corroborated completed TEAM real points including offense/defense/ST; not pure offensive-unit points or DST fantasy',
            pairing='All four axes on identical same-game complete exposure cohort; unknown any-axis pair masks full statistics, known-complete sample separate',
            covariance='Population centered cross moment E[(X-EX)(Y-EY)]; observed E[XY] and independence EX*EY baseline use same paired marginal cohort',
            correlation='Cov/sqrt(VarX*VarY), undefined for empty or zero variance; no inferred likelihood',
            clock='Observed common-game clock/exposure context only, not identified causal shared-clock effect or calibrated forward joint law'))
    return dict(**core,semantic_sha256=digest(core),provenance=dict(plays_semantic_sha256=plays['semantic_sha256'],scores_semantic_sha256=scores['semantic_sha256']),
        evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,
        pending_other_catalog_ids=['G24-M05'],limitations=['No full-roster relative-alternative impact or G24-M05 completion','Observed physical logs do not independently prove complete-game event capture','Revised source original pregame availability unknown; no models/forecast/causal claims'])
