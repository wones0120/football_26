from copy import deepcopy
import json,hashlib
import pytest
from backend.app.product_services.documented_playcaller_change import parse_primary_article,build_documented_playcaller_change
A=dict(host='team.example',team_id='BUF',team_short_name='Bills')
C=dict(opponent_id='NYJ',opponent_short_name='Jets',opponent_full_name='New York Jets',season=2023,week=11,outgoing_person='Ken Example',incoming_person='Joe Example')
def fixture():
 source=dict(source_uri='https://team.example/news/preview',team_id='BUF',snapshot_id='preview',observed_at='2026-10-20T16:00:00Z',captured_at='2026-10-20T16:00:01Z')
 pre=dict(source=source,source_article_id='native-preview',headline='Top 5 storylines for Bills vs. Jets | Week 11',body='Bills quarterbacks coach Joe Example will have a bigger role within the offense now as he adds play caller to his title due to Ken Example being relieved of his OC duties.',reported_publication_at='2023-11-15T13:00:00Z',reported_modification_at='2023-11-15T13:00:00Z',body_sha256='a'*64)
 post=dict(source=dict(source,source_uri='https://team.example/news/confirmed',snapshot_id='confirmed'),source_article_id='native-confirmed',headline='Bills first game',body="This Sunday after the Bills' 32-6 win over the New York Jets. As interim offensive coordinator Joe Example's first game calling the plays, the Bills win was a result of a long week for the offense after Ken Example was relieved of his play calling duties.",reported_publication_at='2023-11-20T14:30:00Z',reported_modification_at='2023-11-20T14:30:00Z',body_sha256='b'*64)
 game=dict(game_id='2023_11_NYJ_BUF',season=2023,week=11,game_type='REG',home_team='BUF',away_team='NYJ',home_score=32,away_score=6,gameday='2023-11-19',gametime='16:25')
 return pre,post,game

def run(args=None):return build_documented_playcaller_change(*(args or fixture()),authority=A,context=C)
def test_explicit_duty_transfer_and_measured_first_game_not_title_inference():
 x=run();assert x['measured_effective_game_id']=='2023_11_NYJ_BUF'and x['interim_incoming']is True
 assert x['original_preview_content_captured_before_game']is None and x['exact_handoff_employment_at']is None and x['model_consumed']is False
@pytest.mark.parametrize('bad',['onlyOC','noincoming','nooutgoing','notfirst','duplicate','wrongweek','score','otherteam','otheropponent','phase','aftergame','beforegame'])
def test_title_only_or_wrong_native_duty_game_or_time_does_not_qualify(bad):
 p,c,g=fixture()
 if bad=='onlyOC':c['body']=c['body'].replace('play calling duties','OC duties')
 if bad=='noincoming':p['body']=p['body'].replace('adds play caller','adds offensive coordinator')
 if bad=='nooutgoing':c['body']=c['body'].replace('Ken Example','Another Coach')
 if bad=='notfirst':c['body']=c['body'].replace('first game','second game')
 if bad=='duplicate':p['body']+=' '+p['body']
 if bad=='wrongweek':p['headline']=p['headline'].replace('11','12')
 if bad=='score':g['home_score']=31
 if bad=='otherteam':g['home_team']='KC'
 if bad=='otheropponent':g['away_team']='NE'
 if bad=='phase':g['game_type']='PRE'
 if bad=='aftergame':p['reported_publication_at']='2023-11-21T00:00:00Z'
 if bad=='beforegame':c['reported_publication_at']='2023-11-18T00:00:00Z'
 with pytest.raises(ValueError):run((p,c,g))
@pytest.mark.parametrize('bad',[None,'uri','nativeid','clock','bytes','ambiguous'])
def test_original_article_bytes_native_identifier_and_source_clock_binding(bad):
 p,_,_=fixture();d={'@type':'NewsArticle','url':p['source']['source_uri'],'headline':p['headline'],'articleBody':p['body'],'datePublished':p['reported_publication_at'],'dateModified':p['reported_modification_at'],'mainEntityOfPage':{'@id':'native0'}};s=deepcopy(p['source'])
 if bad=='uri':d['url']='https://wrong.example'
 if bad=='nativeid':d['mainEntityOfPage']={}
 if bad=='clock':d['dateModified']='2027-01-01T00:00:00Z'
 raw=('<script type="application/ld+json">'+json.dumps(d)+'</script>').encode()
 if bad=='ambiguous':raw=raw+raw
 s.update(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
 if bad=='bytes':s['sha256']='0'*64
 if bad:
  with pytest.raises(ValueError):parse_primary_article(raw,s,authority=A,actual_cutoff='2026-10-20T16:01:00Z')
 else:assert parse_primary_article(raw,s,authority=A,actual_cutoff='2026-10-20T16:01:00Z')['source_article_id']=='native0'
