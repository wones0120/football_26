"""Unattached official restriction evidence; never a player value without native identity."""
from datetime import datetime,UTC
from html.parser import HTMLParser
from urllib.parse import urlparse
import hashlib,json,re
from .documented_coordinator_change import _Documents,_walk
from .nws_hourly_precipitation_context import _time
VERSION='documented_restriction_source_v1'
class _Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            href=dict(attrs).get('href','')
            if re.fullmatch(r'(?:https://www\.newyorkjets\.com)?/team/players-roster/[^/?#]+/?',href):self.links.append(href)

def inspect_unattached_restriction(raw,source,*,actual_cutoff):
    if hashlib.sha256(raw).hexdigest()!=source.get('sha256')or len(raw)!=source.get('bytes'):raise ValueError('Original immutable bytes required')
    if urlparse(source.get('source_uri','')).scheme!='https'or urlparse(source.get('source_uri','')).hostname!='www.newyorkjets.com'or source.get('team_id')!='NYJ':raise ValueError('Official authority/team required')
    cap,obs,cutoff=(_time(v)for v in(source.get('captured_at'),source.get('observed_at'),actual_cutoff))
    if any(v is None for v in(cap,obs,cutoff))or not obs<=cap<=cutoff<=datetime.now(UTC):raise ValueError('Actual original source clocks required')
    parser=_Documents();text=raw.decode();parser.feed(text);docs=[d for v in parser.documents for d in _walk(v)if d.get('@type')=='NewsArticle'and d.get('url')==source['source_uri']]
    if len(docs)!=1:raise ValueError('Unique native same-URI article required')
    d=docs[0];aid=d.get('mainEntityOfPage',{}).get('@id');body=d.get('articleBody');published=_time(d.get('datePublished'));modified=_time(d.get('dateModified'))
    if not isinstance(aid,str)or not aid or not isinstance(body,str)or published is None or modified is None or max(published,modified)>cap:raise ValueError('Native article/body and published/modified capture bounds required')
    matches=list(re.finditer(r'Jets plan to continue to limit Hall[’\']s snap count in Week 2 against the Cowboys',body))
    if len(matches)!=1:raise ValueError('Unique explicit qualitative intended restriction required')
    if published.year!=2023:raise ValueError('Reported publication year must bind the authored season')
    paragraph=body[:matches[0].start()].rsplit('\n',1)[-1]
    if len(re.findall(r'\bRB Breece Hall\b',paragraph))!=1:raise ValueError('Explicit same-paragraph role and subject required')
    m=matches[0];links=_Links();links.feed(text)
    subject_key=aid+':source-subject:'+str(m.start())+':'+str(m.end())
    return dict(version=VERSION,source_article_id=aid,source_subject_key=subject_key,source_snapshot_id=source['snapshot_id'],source_body_sha256=hashlib.sha256(body.encode()).hexdigest(),qualitative_plan_evidence_range=[m.start(),m.end()],source_display_name='Breece Hall',source_role='RB',source_team_id='NYJ',source_authored_intended_season=2023,source_authored_intended_week=2,source_authored_opponent='DAL',reported_publication_at=published.isoformat(),reported_modification_at=modified.isoformat(),modification_precedes_publication=modified<published,source_profile_href_candidates=sorted(set(links.links)),native_player_id=None,player_master_id=None,canonical_attachment_status='UNVERIFIED',restriction_catalog_value=None,numeric_cap=None,actual_adherence=None,continued_restriction=None,original_pregame_receipt=None,source_index_scope_is_restriction_scope=False,identity_blocker='No article-linked native person/profile and documented NFL-ID chain verified; name/statistical match prohibited',model_consumed=False)

def identity_case_request(fact,source_ref):
    if fact.get('version')!=VERSION or fact.get('canonical_attachment_status')!='UNVERIFIED'or fact.get('player_master_id')is not None:raise ValueError('Only unattached source subject may enter this queue')
    scope=dict(source_ref=source_ref,article_id=fact['source_article_id'],source_subject_key=fact['source_subject_key']);key='restriction-native-subject:'+hashlib.sha256(json.dumps(scope,sort_keys=True).encode()).hexdigest()
    return dict(identity_quarantine_id='restriction-subject:'+hashlib.sha256(key.encode()).hexdigest()[:32],source_record_key=key,source_player_key=fact['source_subject_key'],source_subject_key_is_native_player_id=False,team_id='NYJ',position='RB',display_name=fact['source_display_name'],season=2023,week=2,reason_code='documented_restriction_native_subject_attachment_unverified',candidate_player_ids=[],source_ref=source_ref)
