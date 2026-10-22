"""Explicit source play-calling handoff at a measured game, not title inference."""
from urllib.parse import urlparse
from datetime import datetime,UTC
import hashlib,re
from .documented_coordinator_change import _Documents,_walk
from .factual_designation import clock
from .evaluation_record import digest
from .scheduled_venue_displacement import kickoff_utc
from .market_snapshots import canonical_team

VERSION='documented_playcaller_change_v1'

def parse_primary_article(raw,source,*,authority,actual_cutoff):
    now=clock(actual_cutoff);observed=clock(source.get('observed_at'));captured=clock(source.get('captured_at'))
    if now is None or now>datetime.now(UTC)or observed is None or captured is None or not observed<=captured<=now:raise ValueError('Actual source capture/read chronology required')
    if hashlib.sha256(raw).hexdigest()!=source.get('sha256')or len(raw)!=source.get('bytes')or urlparse(source.get('source_uri','')).hostname!=authority['host']or source.get('team_id')!=authority['team_id']:raise ValueError('Immutable official authority/team document required')
    if urlparse(source['source_uri']).scheme!='https':raise ValueError('Authenticated HTTPS authority required')
    p=_Documents();p.feed(raw.decode());docs=[d for v in p.documents for d in _walk(v)if d.get('@type')=='NewsArticle'and d.get('url')==source['source_uri']]
    if len(docs)!=1:raise ValueError('Unique same-URI NewsArticle required')
    d=docs[0];pub=clock(d.get('datePublished'));mod=clock(d.get('dateModified'));aid=d.get('mainEntityOfPage',{}).get('@id')
    if not isinstance(d.get('articleBody'),str)or not isinstance(d.get('headline'),str)or not isinstance(aid,str)or not aid or pub is None or mod is None or not pub<=mod<=captured:raise ValueError('Native article ID/body/headline and source clocks required')
    return dict(source=source,source_article_id=aid,body=d['articleBody'],headline=d['headline'],reported_publication_at=pub.isoformat(),reported_modification_at=mod.isoformat(),body_sha256=hashlib.sha256(d['articleBody'].encode()).hexdigest())

def _one(pattern,text):
    ms=list(re.finditer(pattern,text,re.I))
    if len(ms)!=1:raise ValueError('Unique explicit calling-duty/game clause required')
    return ms[0]

def build_documented_playcaller_change(preview,confirmation,game,*,authority,context):
    team=canonical_team(authority['team_id']);opponent=canonical_team(context['opponent_id']);season,week=context['season'],context['week'];gid=game['game_id']
    if any(x['source'].get('team_id')!=team or urlparse(x['source']['source_uri']).hostname!=authority['host']for x in(preview,confirmation)):raise ValueError('Same official team authority required')
    if(game['season'],game['week'],game['game_type'],canonical_team(game['home_team']),canonical_team(game['away_team']))!=(season,week,'REG',team,opponent)or gid!=f'{season}_{week:02d}_{game["away_team"]}_{game["home_team"]}':raise ValueError('Exact measured native home-team game required')
    home=re.escape(authority['team_short_name']);opp=re.escape(context['opponent_short_name']);old=re.escape(context['outgoing_person']);new=re.escape(context['incoming_person'])
    _one(home+r'\s+vs\.?\s+'+opp+r'.*Week\s+'+str(week)+r'\b',preview['headline'])
    assigned=_one(home+r'\s+quarterbacks\s+coach\s+'+new+r'\s+will\s+have\s+a\s+bigger\s+role\s+within\s+the\s+offense\s+now\s+as\s+he\s+adds\s+play\s+caller\s+to\s+his\s+title\s+due\s+to\s+'+old+r'\s+being\s+relieved\s+of\s+his\s+OC\s+duties',preview['body'])
    called=_one(r'As\s+interim\s+offensive\s+coordinator\s+'+new+r"[’']s\s+first\s+game\s+calling\s+the\s+plays,\s+[^.!?]+?\s+after\s+"+old+r'\s+was\s+relieved\s+of\s+his\s+play\s+calling\s+duties',confirmation['body'])
    result=_one(r'the\s+'+home+r"[’']\s+(\d+)-(\d+)\s+win\s+over\s+the\s+"+re.escape(context['opponent_full_name']),confirmation['body'])
    if(int(result.group(1)),int(result.group(2)))!=(int(game['home_score']),int(game['away_score'])):raise ValueError('Reported measured-game identity/score differs from native schedule')
    kickoff=kickoff_utc(game.get('gameday'),game.get('gametime'));before=clock(preview['reported_publication_at']);after=clock(confirmation['reported_publication_at'])
    if kickoff is None or not before<kickoff<after:raise ValueError('Source preview/observed-game confirmation chronology required')
    def binding(d,m):return dict(source_article_id=d['source_article_id'],source=d['source'],reported_publication_at=d['reported_publication_at'],reported_modification_at=d['reported_modification_at'],body_sha256=d['body_sha256'],evidence_character_range=[m.start(),m.end()])
    core=dict(version=VERSION,candidate_id='G22-M08',team_id=team,side='offense',source_outgoing_person=context['outgoing_person'],source_incoming_person=context['incoming_person'],coach_canonical_ids=None,
        measured_effective_game_id=gid,measured_game_kickoff_at=kickoff.isoformat(),incoming_first_calling_game_source_proven=True,outgoing_playcalling_duties_ended_before_this_game=True,
        interim_incoming=True,exclusive_or_shared_calling_details=None,exact_handoff_employment_at=None,intervening_staff_history_complete=None,
        preview_assignment=binding(preview,assigned),observed_first_game_and_outgoing_duty_confirmation=binding(confirmation,called),game_identity_confirmation=binding(confirmation,result),
        source_preview_published_before_game=True,original_preview_content_captured_before_game=None,current_or_future_playcaller=None,workload_or_causal_effect=None,
        definition='Explicit outgoing offensive PLAYCALLING duty release plus source-assigned incoming duty and observed FIRST calling game; native game corroborated. Title alone does not qualify; retrospective source scope only.')
    return dict(**core,semantic_sha256=digest(core),pregame_serving_eligible=False,model_consumed=False,optimizer_consumed=False)
