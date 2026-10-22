"""Authoritative source-documented coordinator transitions, not play calling."""
from html.parser import HTMLParser
from urllib.parse import urlparse
from copy import deepcopy
import hashlib,json,re
from .factual_designation import clock
from .evaluation_record import digest

VERSION='documented_coordinator_change_v1'
ROLES={'offensive_coordinator':'offensive coordinator','defensive_coordinator':'defensive coordinator'}

class _Documents(HTMLParser):
    def __init__(self):super().__init__();self.active=False;self.parts=[];self.documents=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script'and dict(attrs).get('type','').lower()=='application/ld+json':self.active=True;self.parts=[]
    def handle_data(self,data):
        if self.active:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=='script'and self.active:
            self.active=False
            try:self.documents.append(json.loads(''.join(self.parts)))
            except (ValueError,TypeError):pass

def _walk(value):
    if isinstance(value,list):
        for v in value:yield from _walk(v)
    elif isinstance(value,dict):
        yield value
        if '@graph'in value:yield from _walk(value['@graph'])

def extract_coordinator_statement(raw,source,*,authority,kind,person,role,actual_cutoff):
    boundary=clock(actual_cutoff);observed=clock(source.get('observed_at'));captured=clock(source.get('captured_at'))
    if boundary is None or observed is None or captured is None or not observed<=captured<=boundary:raise ValueError('Actual source observation/capture chronology required')
    if hashlib.sha256(raw).hexdigest()!=source.get('sha256')or len(raw)!=source.get('bytes'):raise ValueError('Immutable original document bytes differ')
    uri=source.get('source_uri','');u=urlparse(uri)
    if u.scheme!='https'or u.hostname!=authority.get('host')or source.get('team_id')!=authority.get('team_id')or not authority.get('team_name'):raise ValueError('Explicit official authority/native team binding required')
    if role not in ROLES or kind not in {'departure','appointment'}or not isinstance(person,str)or not person.strip():raise ValueError('Declared literal coordinator role/person/kind required')
    parser=_Documents();parser.feed(raw.decode('utf-8'));docs=[d for v in parser.documents for d in _walk(v)if d.get('@type')=='NewsArticle'and d.get('url')==uri]
    if len(docs)!=1:raise ValueError('Unique same-URI primary NewsArticle required')
    d=docs[0];body=d.get('articleBody');published=clock(d.get('datePublished'));modified=clock(d.get('dateModified'))
    if not isinstance(body,str)or authority['team_name']not in body or published is None or modified is None or not published<=modified<=captured:raise ValueError('Primary article body/team and reported publication clocks required')
    article_id=d.get('mainEntityOfPage',{}).get('@id')
    if not isinstance(article_id,str)or not article_id:raise ValueError('Stable source-native article identifier required')
    literal_role=ROLES[role];p=re.escape(person);rr=re.escape(literal_role)
    pattern=(r'parted\s+ways\s+with\s+'+rr+r'\s+'+p+r'(?=[,.;]|\s+and\b|$)')if kind=='departure'else(p+r'\s+has\s+been\s+hired\s+as\s+'+rr+r'(?=[,.;]|$)')
    matches=list(re.finditer(pattern,body,re.I))
    if len(matches)!=1:raise ValueError('Unique explicit same-person coordinator departure/appointment statement required')
    m=matches[0]
    # Bind the appointment to this club's announcing head coach, not a rival
    # mentioned elsewhere in the same official news page or biography.
    prefix=body[:m.start()].rsplit('.',1)[-1].strip()
    subject=re.escape(authority['team_name'])+r"\s+Head\s+Coach\s+[A-Za-z .’'\-]+?\s+(?:has\s+)?announced(?:\s+that)?(?:\s+the\s+team\s+has)?\s*$"
    if not re.fullmatch(subject,prefix,re.I):raise ValueError('Direct same-team announcing subject required, not background or rival hire')
    return dict(team_id=authority['team_id'],team_name=authority['team_name'],role=role,literal_role=body[m.start():m.end()],kind=kind,source_person_literal=person,source_coach_entity_id=None,
        source_article_id=article_id,source_uri=uri,source_snapshot_id=source['snapshot_id'],source_sha256=source['sha256'],evidence_character_range=[m.start(),m.end()],source_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        reported_announcement_at=published.isoformat(),reported_article_modified_at=modified.isoformat(),original_observed_at=observed.isoformat(),actual_capture_at=captured.isoformat(),
        employment_effective_at=None,effective_upper_bound_source_claim_at=published.isoformat(),effective_time_interpretation='Past-tense source claim is effective no later than announcement; exact employment time not stated',
        interim_status='not_stated',play_calling_responsibility=None,player_master_id=None)

def build_documented_coordinator_change(departure,appointment):
    if departure.get('kind')!='departure'or appointment.get('kind')!='appointment':raise ValueError('Explicit outgoing and incoming source facts required; hire alone insufficient')
    if(departure['team_id'],departure['role'])!=(appointment['team_id'],appointment['role']):raise ValueError('Same native team and coordinator responsibility required')
    old,new=clock(departure['reported_announcement_at']),clock(appointment['reported_announcement_at'])
    if old is None or new is None or old>new:raise ValueError('Ordered explicit announcement clocks required')
    if departure['source_person_literal']==appointment['source_person_literal']:raise ValueError('Same literal person is not an independently established coordinator change')
    core=dict(version=VERSION,candidate_id='G22-M07',team_id=departure['team_id'],role=departure['role'],documented_transition=True,
        outgoing=deepcopy(departure),incoming=deepcopy(appointment),transition_announcement_at=appointment['reported_announcement_at'],
        announcement_interval_seconds=(new-old).total_seconds(),actual_vacancy_duration=None,intervening_staff_universe='unknown',immediate_predecessor_completeness='unknown',
        target_game_id=None,target_game_applicability=None,all_team_history_completeness=False,play_caller_changed=None,workload_effect=None,
        definition='Source-scoped outgoing and incoming coordinator appointment transition; same native team/responsibility with explicit authority and announcement bounds. Not complete staff chronology or a play-calling change.')
    return dict(**core,semantic_sha256=digest(core),pregame_serving_eligible=False,model_consumed=False,optimizer_consumed=False)
