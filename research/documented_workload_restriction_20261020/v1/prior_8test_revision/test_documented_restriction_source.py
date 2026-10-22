from datetime import datetime,UTC,timedelta
import hashlib,json
import pytest
from backend.app.product_services.documented_restriction_source import inspect_unattached_restriction,identity_case_request

def fixture():
 url='https://www.newyorkjets.com/news/test';d={'@type':'NewsArticle','url':url,'mainEntityOfPage':{'@id':'native-article'},'articleBody':"RB Breece Hall: Jets plan to continue to limit Hall's snap count in Week 2 against the Cowboys.",'datePublished':'2023-09-15T20:30:00Z','dateModified':'2023-09-15T20:27:00Z'}
 return d,dict(source_uri=url,team_id='NYJ',snapshot_id='original',captured_at='2026-01-01T00:00:00Z',observed_at='2026-01-01T00:00:00Z')
def run(d,s,extra=''):
 raw=('<script type="application/ld+json">'+json.dumps(d)+'</script>'+extra).encode();s=dict(s,sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw));return inspect_unattached_restriction(raw,s,actual_cutoff=datetime.now(UTC))
def test_qualitative_source_never_player_value_and_clock_anomaly_retained():
 f=run(*fixture());assert f['modification_precedes_publication'];assert f['restriction_catalog_value']is None and f['native_player_id']is None and f['player_master_id']is None;assert f['numeric_cap']is None and f['actual_adherence']is None

def test_generic_roster_not_native_person_link():
 f=run(*fixture(),extra='<a href="https://www.newyorkjets.com/team/players-roster">Roster</a>');assert f['source_profile_href_candidates']==[]
def test_even_candidate_profile_href_not_identity_proof():
 f=run(*fixture(),extra='<a href="/team/players-roster/breece-hall/">Hall</a>');assert len(f['source_profile_href_candidates'])==1 and f['player_master_id']is None
@pytest.mark.parametrize('key,value',[('articleBody','RB Hall injury label only'),('url','https://example.com'),('dateModified','2030-01-01T00:00:00Z')])
def test_source_guards(key,value):
 d,s=fixture();d[key]=value
 with pytest.raises(ValueError):run(d,s)
def test_stable_evidence_specific_queue_no_guess():
 f=run(*fixture());ref={'path':'original','sha256':'abc','bytes':1};a=identity_case_request(f,ref);b=identity_case_request(f,ref);assert a==b and a['candidate_player_ids']==[] and not a['source_subject_key_is_native_player_id'];assert identity_case_request(f,dict(ref,sha256='changed'))['source_record_key']!=a['source_record_key']
def test_no_resolved_case_rewrite():
 f=run(*fixture());f['player_master_id']='existing'
 with pytest.raises(ValueError):identity_case_request(f,{'sha256':'x'})
