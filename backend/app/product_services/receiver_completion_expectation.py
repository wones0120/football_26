"""Same-target receiver completion excess over the external provider cp model."""
from collections import defaultdict
from copy import deepcopy
from uuid import UUID
import re
from .evaluation_record import digest
from .opportunity_events import _flag
from .defense_context_evidence import _number
from .environment_context_evidence import _and
from .market_snapshots import canonical_team

VERSION='receiver_completion_expectation_v1'
NATIVE=re.compile(r'00-\d{7}')
FIELDS=('game_id','play_id','season','week','season_type','posteam','receiver_player_id','qb_spike','complete_pass','cp')


def build_receiver_completion_expectation(component,projection,identity_qualification):
    if component.get('version')!='sourcewide_official_channel_component_v1':raise ValueError('Reviewed all-native official component required')
    if component.get('uncertain_official_rows'):raise ValueError('Unscoped possible official targets require explicit compatible actor masks, not silent omission')
    before=component['before_period'];source={};events={};expected=set()
    for r in projection:
        key=(r['game_id'],str(int(r['play_id'])));parts=key[0].split('_')
        if key in source or len(parts)!=4 or r['season_type']!='REG' or (int(r['season']),int(r['week']))!=(int(parts[0]),int(parts[1]))or int(parts[0])*100+int(parts[1])>=before:raise ValueError('Unique matched prior REG source projection required')
        source[key]=r
    for r in component['native_order']['rows']:
        key=(r['game_id'],str(int(r['play_id'])))
        if key in expected:raise ValueError('Duplicate original native row')
        expected.add(key)
    if set(source)!=expected:raise ValueError('Complete original source projection/order cohort required')
    actors=defaultdict(list);by_team=defaultdict(list);ledger=[];residual=[]
    for e in component['official_channel_event_basis']:
        key=(e['game_id'],str(int(e['play_id'])))
        if key in events or key not in source:raise ValueError('Unique native official event/source key required')
        events[key]=e;r=source[key];team=e['team'];pair={canonical_team(t)for t in key[0].split('_')[2:]}
        if team not in pair or canonical_team(r.get('posteam'))!=team:raise ValueError('Native source/official offense differs')
        channels={o['channel']for o in e['opportunities']}
        target=True if 'targets'in channels else None if 'targets'in e['unknown_channels']else False
        passing=True if 'pass_attempts'in channels else None if 'pass_attempts'in e['unknown_channels']else False
        spike=_flag(r.get('qb_spike'));eligible=_and(_and(target,passing),None if spike is None else not spike)
        if eligible is False:continue
        target_rows=[o for o in e['opportunities']if o['channel']=='targets']
        if len(target_rows)>1:raise ValueError('One physical target attribution required')
        native=target_rows[0].get('source_player_id')if target_rows else r.get('receiver_player_id')
        if target_rows and native!=r.get('receiver_player_id'):raise ValueError('Same target native receiver differs from original source')
        if not isinstance(native,str)or not NATIVE.fullmatch(native):native=None
        cp=_number(r.get('cp'));cp=cp if cp is not None and 0<=cp<=1 else None
        complete=_flag(r.get('complete_pass'));observed=float(complete)if complete is not None else None
        known=eligible is True and cp is not None and observed is not None
        item=dict(game_id=key[0],play_id=key[1],team=team,source_player_id=native,eligible=eligible,source_cp=cp,completion=observed,known_matched_outcome=known,excess=observed-cp if known else None)
        by_team[(key[0],team)].append(item);ledger.append(item)
        if native is not None:actors[(key[0],team,native)].append(item)
        else:residual.append(item)
    rows=[]
    for(gid,team,native),items in sorted(actors.items()):
        known=[r for r in items if r['known_matched_outcome']];n=len(known);completions=sum(r['completion']for r in known);expected_completions=sum(r['source_cp']for r in known)
        eligible=sum(r['eligible']is True for r in items);unknown_elig=sum(r['eligible']is None for r in items);unknown_outcome=sum(r['eligible']is True and not r['known_matched_outcome']for r in items)
        compatible=by_team[(gid,team)];team_unknown=sum(r['eligible']is None for r in compatible);unattributed=sum(r['source_player_id']is None for r in compatible)
        exact=n>0 and not(unknown_elig or unknown_outcome or team_unknown or unattributed)
        native_value=(completions-expected_completions)/n if exact else None
        pid=identity_qualification.get(native)
        if pid is not None and str(UUID(pid))!=pid:raise ValueError('Canonical UUID spelling required')
        rows.append(dict(game_id=gid,team=team,source_player_id=native,player_master_id=pid,eligible_targets=eligible,unknown_eligibility=unknown_elig,unknown_outcomes=unknown_outcome,compatible_team_unknown_eligibility=team_unknown,compatible_unattributed_targets=unattributed,
            known_matched_targets=n,known_completions=completions,known_expected_completions=expected_completions,known_sample_catch_fraction=completions/n if n else None,known_sample_mean_cp=expected_completions/n if n else None,known_sample_excess=(completions-expected_completions)/n if n else None,
            native_exact_excess=native_value,catalog_value=native_value if pid is not None else None,percentage_points=100*native_value if pid is not None and native_value is not None else None))
    core=dict(version=VERSION,candidate_id='G09-M02',before_period=before,actor_game_rows=rows,event_basis=ledger,unattributed_events=residual,identity_qualification=deepcopy(identity_qualification),source_event_sha256=component['source_event_sha256'],
        definition='Same receiver-attributed official nonspike targets: sum(completion - source cp)/N = observed catch fraction minus mean provider cp; matched known sample and full exact unknown masks separate',
        unit='probability_fraction; percentage_points explicitly multiplied by100',model_definition='External nflfastR completion probability conditional on comparable game situations; source vintage/model training chronology unknown',
        limitations=['Observed source logs, full-game completeness and original historical availability unknown','Not isolated receiver skill, charted catchability, a fantasy scoring bonus, causal effect or calibrated own forecast'])
    return dict(**core,semantic_sha256=digest(core),pregame_serving_eligible=False,model_consumed=False,optimizer_consumed=False)
