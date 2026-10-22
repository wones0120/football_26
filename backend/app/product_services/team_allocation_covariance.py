"""Observed same-team allocation covariance, with native and residual actors."""
from collections import defaultdict
from copy import deepcopy
from .evaluation_record import digest
from .market_snapshots import canonical_team
from .opportunity_source_coverage import build_opportunity_source_coverage,count,CHANNELS

VERSION='observed_team_allocation_covariance_v1'
RESIDUAL='unattributed_native_residual'


def _covariance(vectors):
    n=len(vectors)
    if n<2:return None
    width=len(vectors[0]);means=[sum(v[i] for v in vectors)/n for i in range(width)]
    matrix=[[sum((v[i]-means[i])*(v[j]-means[j]) for v in vectors)/(n-1) for j in range(width)] for i in range(width)]
    if any(abs(sum(row))>1e-10 for row in matrix):raise ValueError('Conserved allocation covariance row sum differs')
    return matrix


def build_team_allocation_covariance(source,*,before_period,last_n=8):
    coverage=build_opportunity_source_coverage(source,before_period=before_period)
    if type(last_n) is not int or not 1<=last_n<=32:raise ValueError('Explicit observed same-season window required')
    actor_rows=defaultdict(list)
    for row in source['actor_game_rows']:actor_rows[(row['game_id'],canonical_team(row['team']))].append(row)
    groups=defaultdict(list)
    for row in coverage['game_rows']:
        if int(row['game_id'].split('_')[0])==before_period//100:groups[row['team']].append(row)
    output=[]
    for team,games in sorted(groups.items()):
        games=sorted(games,key=lambda r:(int(r['game_id'].split('_')[1]),r['game_id']))[-last_n:]
        if len({int(r['game_id'].split('_')[1]) for r in games})!=len(games):raise ValueError('One native game per team period required')
        metrics={}
        for mid,ch in (('X02-M09','targets'),('X02-M10','rush_attempts')):
            native={};logs=[]
            for game in games:
                key=(game['game_id'],team);m=game['metrics'][ch]['X08_M02'];by_actor={}
                for actor in actor_rows[key]:
                    metric=actor['metrics'].get(CHANNELS[ch]);n=count(metric['observed_outcome_sum']) if metric and metric['observed_outcome_sum'] is not None else 0
                    if not n:continue
                    name='native:'+actor['source_player_id'];pid=actor['player_master_id']
                    if name in native and native[name]!=pid:raise ValueError('Native canonical identity changes inside team window')
                    native[name]=pid;by_actor[name]=n
                total=m['exact_team_opportunities'];residual=m['known_unattributed_opportunity_lower_bound']
                # Unattributed events may belong to an already known actor. A residual label must not falsely certify the other actor coordinates.
                complete=total is not None and total>0 and residual==0
                logs.append(dict(game_id=game['game_id'],known_native_counts=by_actor,known_residual_lower_bound=residual,exact_team_opportunities=total,
                                 unknown_eligibility_events=m['unknown_eligibility_events'],allocation_vector_exact=complete))
            coordinates=sorted(native)+[RESIDUAL];vectors=[]
            for log in logs:
                if log['allocation_vector_exact']:
                    total=log['exact_team_opportunities'];vector=[log['known_native_counts'].get(k,0)/total for k in coordinates[:-1]]+[0.]
                    if abs(sum(vector)-1)>1e-10:raise ValueError('Native allocation shares do not conserve team budget')
                    vectors.append(vector)
            known=_covariance(vectors);exact=known if len(vectors)==len(logs) else None
            metrics[mid]=dict(channel=ch,unit='allocation_share_squared',coordinates=[dict(key=k,source_player_id=k[7:],player_master_id=native[k]) for k in coordinates[:-1]]+[dict(key=RESIDUAL,source_player_id=None,player_master_id=None)],
                covariance=exact,known_complete_sample_covariance=known,observed_team_logs=len(logs),known_complete_allocation_logs=len(vectors),
                unknown_or_zero_budget_logs=len(logs)-len(vectors),sample_divisor='n_minus_1',logs=logs)
        output.append(dict(team=team,season=before_period//100,metrics=metrics))
    facts=dict(version=VERSION,before_period=before_period,last_n_same_season_observed_team_logs=last_n,catalog_ids=['X02-M09','X02-M10'],team_windows=output)
    return facts|dict(semantic_sha256=digest(facts),source_component_semantic_sha256=source['semantic_measurements_sha256'],provenance=deepcopy(source['provenance']),
        identity_review_requests=deepcopy(source['identity_review_requests']),evidence_use='postlock_descriptive_not_pregame_or_serving',pregame_serving_eligible=False,forecast=None,model_consumed=False,optimizer_consumed=False,
        limitations=['Observed source allocation-share covariance, not predictive joint distribution, uncertainty calibration or event independence',
            'All native rushers including QB and canonically unresolved native actors retain measured mass; no position/salary/user-preference filter',
            'Residual coordinate is explicit; unknown native mass may belong to known actors and therefore masks the entire exact vector/covariance',
            'Absent actor event counts become known zero only inside a fully attributed positive observed team channel budget; not an active/DNP assertion',
            'Zero budgets and incomplete source games stay undefined; known-complete sample covariance is separately labeled, not a complete-window estimate'])


def require_feature_use(value,*,purpose):
    if value.get('version')!=VERSION or purpose!='offline_descriptive' or value.get('pregame_serving_eligible') is not False:raise ValueError('Observed allocation covariance cannot serve models/forecasts/optimizer')
    return value
