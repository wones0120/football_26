"""User construction preferences based on prior-week season averages."""
import re
from Database.dst import normalize_team
from .classic_season_rank_preferences import load_rankings


def validate_leader_preferences(params, *, showdown):
    for key in ('require_team_leader','require_home_team_leader'):
        if key in params and type(params[key]) is not bool:
            raise ValueError(f'{key} must be an explicit boolean')
        if params.get(key) and not showdown:
            raise ValueError('Team leader preferences require Showdown format')
    if params.get('require_home_team_leader') and not params.get('require_team_leader'):
        raise ValueError('Home-team leader requires team-leader preference enabled')


def leader_preference(pool, params, *, engine=None, season=None, week=None):
    if not params.get('require_team_leader'):
        return dict(enabled=False,required_player_ids=[])
    evidence=load_rankings(engine, season=season, week=week, include_kickers=True)
    history={r['player_id']:r for r in evidence['rows']}
    teams={};homes=set();unranked=[]
    for row in pool.to_dict('records'):
        tm=normalize_team(str(row.get('player_team') or row.get('team') or '').strip().upper())
        match=re.search(r'\b([A-Z]{2,3})@([A-Z]{2,3})\b',str(row.get('game_id') or row.get('game_info') or ''))
        if match: homes.add(normalize_team(match[2]))
        if str(row.get('position') or '').upper() not in {'RB','WR','TE','K'}:continue
        pid=str(row.get('player_id') or '')
        if not pid or not tm: raise ValueError('Invalid team leader identity evidence')
        teams.setdefault(tm, [])
        prior=history.get(pid)
        if prior is None or prior['position'] != str(row.get('position')).upper():
            unranked.append(dict(player_id=pid,name=row.get('name'),team=tm,reason='no_usable_prior_history'))
            continue
        teams[tm].append(dict(player_id=pid,name=row.get('name'),team=tm,season_ppg=prior['ppg'],prior_games=prior['games_played']))
    if len(teams)!=2 or any(not rows for rows in teams.values()):
        raise ValueError('Season-average team leader requires usable prior history for both teams; refresh historical inputs or disable the requirement')
    leaders=[]
    for tm,rows in sorted(teams.items()):
        top=max(p['season_ppg'] for p in rows)
        leaders.extend(p for p in rows if p['season_ppg']==top)
    home=None
    if params.get('require_home_team_leader'):
        if len(homes)!=1 or not homes.issubset(teams): raise ValueError('Home-team leader requires unambiguous home-team evidence')
        home=next(iter(homes))
    ids=sorted({p['player_id'] for p in leaders if home is None or p['team']==home})
    return dict(enabled=True,home_only=home is not None,home_team=home,leaders=leaders,required_player_ids=ids,
        category='user_preference',reason_code='user_season_average_team_leader',scope='captain_or_flex',
        basis='highest_prior_week_season_dk_ppg_before_user_filters_non_qb_excluding_dst',ties='any tied leader qualifies',
        season=season,through_week=week-1,unranked_players=unranked,history=evidence)
