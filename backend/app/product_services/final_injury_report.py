"""Bounded official-club final-report adapter, reusing immutable context storage.

No crawler and no designation inferred from absence. Unsupported page structures
abstain. The caller supplies a report URL; scope and publication are verified.
"""
from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from Database.player_identity import normalize_player_name
from .factual_designation import FINAL_REPORT, NO_DESIGNATION, clock
from .official_injuries import _Document, observation_clock, resolve_official_player, _record_identity


def _grouped_final_rows(document, *, team, source_uri, final_date):
    """Explicit dated game-status groups, never omission-based clearance."""
    from .market_snapshots import NFL_TEAM_NAMES
    selected_day=False;selected_team=False;groups={};rows=[]
    for node in document.find():
        if node.tag not in {'p','h3'}:continue
        value=' '.join(node.content().split())
        if re.fullmatch(r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), [A-Za-z]+ \d{1,2}, \d{4}',value,re.I):
            selected_day=datetime.strptime(value,'%A, %B %d, %Y').date()==final_date
            selected_team=False;continue
        if node.tag=='h3':
            selected_team=selected_day and any(value.upper()==name.upper() and code==team for name,code in NFL_TEAM_NAMES.items())
            continue
        if not selected_day or not selected_team:continue
        match=re.match(r'^(OUT|DOUBTFUL|QUESTIONABLE|NO GAME STATUS GIVEN):?\s+(.*)$',value)
        if not match:continue
        group,body=match.groups()
        if group in groups:raise ValueError('Duplicate final game-status group')
        groups[group]=True
        if body=='No Players Listed.':continue
        pattern=re.compile(r'([A-Z/]{1,4})\s+([^,()]+?)\s+-\s+([^(),-]+?)\s+\((FP|LP|DNP)\)')
        entries=list(pattern.finditer(body))
        if not entries or pattern.sub('',body).strip(' ,'):
            raise ValueError('Incomplete explicit final status/participation group')
        for entry in entries:
            position,name,injury,practice=entry.groups()
            rows.append(dict(team=team,position=position,player_name=name,
                source_key=source_uri+'#'+position+'-'+normalize_player_name(name),
                game_status=NO_DESIGNATION if group=='NO GAME STATUS GIVEN' else group,
                practice_status={'FP':'FULL','LP':'LIMITED','DNP':'DNP'}[practice],injury=injury))
    if set(groups)!={'OUT','DOUBTFUL','QUESTIONABLE','NO GAME STATUS GIVEN'}:
        raise ValueError('No complete dated final game-status groups found')
    if len({r['source_key'] for r in rows})!=len(rows):raise ValueError('Conflicting duplicate final player designation')
    return rows


def parse_final_report(html, *, source_uri, season, week, team, opponent, kickoff_at, observed_at):
    from .classic_official_context import CLUBS
    from .market_snapshots import NFL_TEAM_NAMES
    host=urlparse(source_uri).hostname
    if host not in {CLUBS[team]+'.com','www.'+CLUBS[team]+'.com'} or urlparse(source_uri).scheme!='https':
        raise ValueError('Final report must be on the exact official club HTTPS host')
    document=_Document(html).root
    articles=[]
    for node in document.find('script'):
        if node.attrs.get('type')=='application/ld+json':
            try:
                value=json.loads(node.content())
                if isinstance(value,dict) and value.get('@type')=='NewsArticle':articles.append(value)
            except json.JSONDecodeError:pass
    if len(articles)!=1:raise ValueError('Final report lacks one explicit NewsArticle publication')
    article=articles[0];published=clock(article['datePublished']);modified=clock(article.get('dateModified') or published)
    kickoff=clock(kickoff_at);observed=clock(observed_at)
    if (published>modified or modified>observed or observed>=kickoff or published<kickoff-timedelta(days=5)
            or published.year!=season):raise ValueError('Final report publication/observation is outside this pregame scope')
    if str(article.get('url','')).rstrip('/')!=source_uri.rstrip('/'):
        raise ValueError('Final report canonical URL differs from requested source')
    body=str(article.get('articleBody') or '')
    headline=str(article.get('headline') or '')
    final_marker=re.search(r'\bgame\s+status\b|\bfinal\s+(?:game\s+status|injury)\s+report\b',headline,re.I)
    if not final_marker:
        final_marker=re.search(r'\bfinal\s+(?:game\s+status|injury)\s+report\b',body,re.I)
    if not final_marker:
        final_marker=re.search(r'announce the following player injuries and game statuses\b',body,re.I)
    if not final_marker:
        raise ValueError('Report lacks explicit authored final/game-status publication evidence')
    opponent_names=[name for name,code in NFL_TEAM_NAMES.items() if code==opponent]
    nicknames={name.split()[-1] for name in opponent_names}
    if not re.search(r'\bWeek\s+'+str(week)+r'\b',body,re.I) or not any(re.search(r'\b'+re.escape(n)+r'\b',body,re.I) for n in nicknames):
        raise ValueError('Final report article does not explicitly identify requested week and opponent')
    rows=[]
    for table in document.find('table'):
        headers=[n.content().strip().lower().replace('satruday','saturday') for n in table.find('th')]
        if len(headers)!=6 or headers[:2]!=['player','injury'] or headers[-1] not in {'status','game status'}:continue
        local_kickoff=kickoff.astimezone(ZoneInfo('America/New_York'))
        final_day=(local_kickoff-timedelta(days=1 if local_kickoff.weekday()==3 else 2)).strftime('%A').lower()
        if headers[-2]!=final_day:continue
        current=[]
        for tr in table.find('tr'):
            cells=[n.content().strip() for n in tr.find('td')]
            if not cells:continue
            if len(cells)!=6 or cells[-2].upper() not in {'FULL','LIMITED','DNP','DID NOT PARTICIPATE','DID NOT PARTICIPATE IN PRACTICE'}:
                raise ValueError('Final practice day is incomplete; blank status cannot establish clearance')
            match=re.fullmatch(r'(QB|RB|WR|TE|K|[A-Z/]+)\s+(.+)',cells[0])
            if not match:raise ValueError('Final injury row lacks explicit position and identity')
            position,name=match.groups();designation=cells[-1].upper()
            if designation not in {'','OUT','QUESTIONABLE','DOUBTFUL'}:raise ValueError('Unsupported final game designation')
            current.append(dict(team=team,position=position,player_name=name,
                source_key=source_uri+'#'+position+'-'+normalize_player_name(name),
                game_status=designation or NO_DESIGNATION,practice_status=cells[-2],injury=cells[1]))
        if current:rows.extend(current)
    if not rows:
        local_kickoff=kickoff.astimezone(ZoneInfo('America/New_York'))
        final_date=(local_kickoff-timedelta(days=1 if local_kickoff.weekday()==3 else 2)).date()
        rows=_grouped_final_rows(document,team=team,source_uri=source_uri,final_date=final_date)
    return dict(rows=rows,published_at=published.isoformat(),modified_at=modified.isoformat(),
        report_contract=FINAL_REPORT,report_phase='final',scope_verified=True,kickoff_at=kickoff.isoformat(),
        season=season,week=week,team=team,opponent=opponent,final_publication_marker=final_marker.group(),
        source_headline=headline)


def capture_final_report(engine, *, season, week, slate, team, source_uri):
    from .slate_preparation import SlatePreparationRequest, slate_games, require_prelock
    from .pregame_context import PregameContextService
    from ..services.source_capture import SourceCaptureService
    from .classic_official_context import CLUBS
    team=team.upper();slate=slate.upper()
    if team not in CLUBS:raise ValueError('Unknown canonical team')
    with Session(engine) as session:
        games=slate_games(session,SlatePreparationRequest(season=season,week=week,slate=slate,action='rebuild'))
    matches=[g for g in games if team in {g['home_team'],g['away_team']}]
    if len(matches)!=1:raise ValueError('Final report team is not uniquely scoped to a slate game')
    game=matches[0];opponent=game['away_team'] if team==game['home_team'] else game['home_team']
    host=urlparse(source_uri).hostname
    if host not in {CLUBS[team]+'.com','www.'+CLUBS[team]+'.com'} or urlparse(source_uri).scheme!='https':
        raise ValueError('Final report URL is not the official club HTTPS host')
    response=httpx.get(source_uri,timeout=20,follow_redirects=False);response.raise_for_status()
    received=datetime.now(UTC);observed=observation_clock(dict(response.headers),received)
    parsed=parse_final_report(response.text,source_uri=source_uri,season=season,week=week,team=team,
        opponent=opponent,kickoff_at=game['kickoff_at'],observed_at=observed)
    with engine.connect() as connection:
        salaries=[dict(r) for r in connection.execute(text('''SELECT DISTINCT s.player_master_id AS player_id,
            s.player_name,s.team,s.position,m.full_name FROM public.curated_salary s
            JOIN public.player_master m USING(player_master_id) WHERE s.season=:season AND s.week=:week
            AND upper(s.slate)=:slate AND s.source_system='draftkings' '''),dict(season=season,week=week,slate=slate)).mappings()]
        aliases=[dict(r) for r in connection.execute(text('''SELECT player_master_id,source_system,source_key,alias_name
            FROM public.player_alias WHERE source_system='nfl_official' ''' )).mappings()]
    players=[];unresolved=[]
    envelope=dict(source_uri=source_uri,observed_at=observed.isoformat(),received_at=received.isoformat(),
        headers=dict(response.headers),body=response.text,parsed=parsed)
    with TemporaryDirectory() as directory,Session(engine) as session:
        path=Path(directory)/'official_final_report.json';path.write_text(json.dumps(envelope,sort_keys=True))
        capture=SourceCaptureService(session).capture_file(path,source_system='nfl_official',dataset='official_final_game_report',
            season=season,week=week,slate=slate,source_uri=source_uri,slate_lock_at=require_prelock(games),
            source_license='Official club final injury report, retained for audit',effective_at=observed,
            observation_basis='http_response_clock',media_type='application/json',row_count=len(parsed['rows']),
            metadata={k:v for k,v in parsed.items() if k!='rows'})
        snapshot=str(capture.snapshot.snapshot_id)
    with engine.begin() as connection:
        for row in parsed['rows']:
            if row['position'] not in {'QB','RB','WR','TE','K'}:continue
            pid,method=resolve_official_player(row,salaries,aliases)
            recorded=_record_identity(connection,row,pid,method,season=season,week=week,slate=slate)
            if not recorded:unresolved.append(row['source_key']);continue
            players.append(dict(player_id=pid,team=team,position=row['position'],injury_status=row['game_status'],
                evidence={**{k:v for k,v in parsed.items() if k!='rows'},'source_snapshot_id':snapshot,
                    'identity_match':method,'practice_report':{'practice_status':row['practice_status'],'observed_at':observed.isoformat()}}))
    if unresolved:raise ValueError('Final report offensive identities require review: '+', '.join(unresolved))
    result=PregameContextService(engine=engine).create_run(dict(season=season,week=week,slate=slate,
        source='nfl_official_final_report',source_uri=source_uri,observed_at=observed,players=players))
    return dict(snapshot_id=snapshot,context_run_id=result['context_run_id'],players=len(players),
        published_at=parsed['published_at'],observed_at=observed.isoformat(),received_at=received.isoformat())
