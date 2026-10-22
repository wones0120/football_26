import json,hashlib
import pytest
from copy import deepcopy
from backend.app.product_services.documented_coordinator_change import extract_coordinator_statement,build_documented_coordinator_change
A=dict(host='team.example',team_id='NO',team_name='Example Team')
def fixture(kind='departure'):
 person='Pete Sample'if kind=='departure'else'Klint Sample';date='2024-01-16T18:22:00Z'if kind=='departure'else'2024-02-14T23:18:00Z'
 body='Example Team Head Coach Pat Example announced that the team has parted ways with Offensive Coordinator Pete Sample, another coach.'if kind=='departure'else'Example Team Head Coach Pat Example has announced that Klint Sample has been hired as offensive coordinator.'
 uri='https://team.example/news/'+kind;d=dict(**{'@type':'NewsArticle'},url=uri,articleBody=body,datePublished=date,dateModified=date,mainEntityOfPage={'@id':kind+'-native-article'})
 return d,person,dict(source_uri=uri,team_id='NO',snapshot_id=kind,observed_at='2026-10-20T16:00:00Z',captured_at='2026-10-20T16:00:01Z')
def run(kind='departure',change=None):
 d,person,s=fixture(kind)
 if change:change(d,s)
 raw=('<script type="application/ld+json">'+json.dumps(d)+'</script>').encode();s.update(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
 return extract_coordinator_statement(raw,s,authority=A,kind=kind,person=person,role='offensive_coordinator',actual_cutoff='2026-10-20T17:00:00Z')
def test_source_change_has_separate_announced_and_unknown_effective_game_state():
 x=build_documented_coordinator_change(run(),run('appointment'))
 assert x['documented_transition']is True and x['target_game_applicability']is None and x['actual_vacancy_duration']is None
 assert x['outgoing']['employment_effective_at']is None and x['incoming']['play_calling_responsibility']is None
 assert x['outgoing']['player_master_id']is None and x['incoming']['player_master_id']is None
 assert x['model_consumed']is False
@pytest.mark.parametrize('change',[lambda d,s:d.update(articleBody='Example Team hired another coach.'),lambda d,s:d.update(articleBody=d['articleBody']+' '+d['articleBody']),lambda d,s:d.update(url='https://different.example'),lambda d,s:d.update(mainEntityOfPage={}),lambda d,s:d.update(datePublished=None),lambda d,s:d.update(dateModified='2027-01-01T00:00:00Z'),lambda d,s:s.update(captured_at='2026-10-21T00:00:00Z'),lambda d,s:s.update(team_id='WAS'),lambda d,s:d.update(articleBody=d['articleBody'].replace('Offensive Coordinator','Defensive Coordinator'))])
def test_literal_role_statement_authority_and_clock_ambiguity_rejected(change):
 with pytest.raises(ValueError):run(change=change)
def test_new_appointment_alone_does_not_prove_change():
 with pytest.raises(ValueError):build_documented_coordinator_change(run('appointment'),run('appointment'))
@pytest.mark.parametrize('change',[lambda d:d.update(team_id='WAS'),lambda d:d.update(role='defensive_coordinator'),lambda d:d.update(reported_announcement_at='2023-01-01T00:00:00Z'),lambda d:d.update(source_person_literal='Pete Sample')])
def test_pair_native_role_timeline_or_person_conflict_not_transition(change):
 old,new=run(),run('appointment');change(new)
 with pytest.raises(ValueError):build_documented_coordinator_change(old,new)
def test_body_not_related_content_selects_unique_article():
 d,p,s=fixture();raw=('<script type="application/ld+json">'+json.dumps(d)+'</script><script type="application/ld+json">'+json.dumps({'@type':'ImageGallery','url':d['url']})+'</script>').encode();s.update(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
 assert extract_coordinator_statement(raw,s,authority=A,kind='departure',person=p,role='offensive_coordinator',actual_cutoff='2026-10-20T17:00:00Z')['source_article_id']=='departure-native-article'

@pytest.mark.parametrize('kind',['departure','appointment'])
def test_same_official_page_background_rival_statement_not_own_team_event(kind):
 def change(d,s):d['articleBody']=d['articleBody'].replace('announced that ','announced that Rival Club said that ')
 with pytest.raises(ValueError):run(kind,change=change)
