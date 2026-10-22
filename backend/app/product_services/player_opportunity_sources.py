"""Bounded managed revised-history inputs for offline player-model preparation.

This loader is not a live/public source-discovery endpoint. Server-owned refs are
required; raw source/derivation clocks and the non-serving classification survive
combination. It never invents original pregame availability.
"""
from copy import deepcopy
from datetime import UTC,datetime
import hashlib
import json
from pathlib import Path
import re

from .factual_designation import clock
from .offensive_volume_features import digest,period
from .player_opportunity_components import VERSION

ROOT=Path(__file__).resolve().parents[3]/'artifacts'
DIRECTORIES={'player_opportunity_history','player_opportunity_components'}


def load_component_sources(refs, *, cutoff, root=None, max_bytes=24*1024*1024):
    """Read exact bounded SHA artifacts; caller refs must come from server ledger."""
    root=Path(root or ROOT).resolve();blocks=[];provenance=[];seen_refs=set()
    for ref in refs:
        sha=ref.get('sha256','')
        if not re.fullmatch(r'[0-9a-f]{64}',sha) or sha in seen_refs:raise ValueError('Invalid/duplicate player component ref')
        seen_refs.add(sha);path=Path(ref['path']).resolve()
        if path.parent.parent!=root or path.parent.name not in DIRECTORIES or path.name!=sha+'.json':
            raise ValueError('Player component ref outside managed source root')
        if path.stat().st_size>max_bytes or path.stat().st_size!=ref['bytes']:raise ValueError('Player component byte bound differs')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Player component artifact checksum mismatch')
        value=json.loads(raw)
        if value.get('version')!=VERSION or value.get('forecast') is not None:raise ValueError('Unsupported measured player artifact')
        if value.get('pregame_serving_eligible') is not False:raise ValueError('Offline input requires explicit non-serving classification')
        if value.get('semantic_measurements_sha256')!=ref.get('semantic_measurements_sha256'):
            raise ValueError('Player source semantic reference differs')
        original=value.get('provenance') or {};retro=original.get('retrospective_read') or {}
        derived=clock(retro.get('actual_derived_at') or original.get('actual_derived_at') or original.get('decision_cutoff_at'))
        clocks=[clock(v) for v in (original.get('actual_publication_at'),original.get('actual_source_received_at'),
                (original.get('artifact_publication') or {}).get('published_at'),
                (original.get('artifact_publication') or {}).get('actual_publication_at')) if v is not None]
        if derived is None or max([derived,*clocks])>clock(cutoff):raise ValueError('Player source unavailable at actual matrix cutoff')
        blocks.append(value);provenance.append(dict(ref=deepcopy(ref),actual_available_at=max([derived,*clocks]).isoformat(),provenance=deepcopy(original)))
    if not blocks:raise ValueError('No player component sources supplied')
    return combine_component_sources(blocks,provenance=provenance,cutoff=cutoff)


def combine_component_sources(blocks, *, provenance, cutoff):
    actors=[];teams=[];seen_actors=set();seen_native=set();seen_teams=set();requests=[];unattributed=[];definitions=None
    for value in blocks:
        if value.get('version')!=VERSION or value.get('forecast') is not None:raise ValueError('Player source contract differs')
        if definitions is None:definitions=value['definitions']
        elif definitions!=value['definitions']:raise ValueError('Cannot combine different player metric definitions')
        for row in value['actor_game_rows']:
            if period(row['game_id'])>=value['before_period']:raise ValueError('Actor beyond source prior-period boundary')
            native=(row['game_id'],row['team'],row['source_player_id']);canonical=(row['game_id'],row['player_master_id'])
            if native in seen_native or (row['player_master_id'] is not None and canonical in seen_actors):
                raise ValueError('Overlapping/ambiguous player source game')
            seen_native.add(native)
            if row['player_master_id'] is not None:seen_actors.add(canonical)
            actors.append(deepcopy(row))
        for row in value['team_denominators']:
            key=(row['game_id'],row['team'])
            if key in seen_teams:raise ValueError('Overlapping team source games; explicit revision resolution required')
            seen_teams.add(key);teams.append(deepcopy(row))
        requests.extend(deepcopy(value.get('identity_review_requests') or []));unattributed.extend(deepcopy(value.get('unattributed_events') or []))
    before=max(value['before_period'] for value in blocks)
    result=dict(version=VERSION,before_period=before,definitions=deepcopy(definitions),forecast=None,
        actor_game_rows=sorted(actors,key=lambda r:(r['game_id'],r['team'],r['source_player_id'])),
        team_denominators=sorted(teams,key=lambda r:(r['game_id'],r['team'])),
        identity_review_requests=requests,unattributed_events=unattributed,
        evidence_use='combined_revised_offline_model_inputs_not_original_pregame',pregame_serving_eligible=False,
        limitations=['Managed source bytes verified at actual read; original historical pregame availability unproven',
                    'Unknown attribution and full-game coverage remain source-specific; no missing actor becomes zero'])
    result['semantic_measurements_sha256']=digest(result)
    result['provenance']=dict(decision_cutoff_at=clock(cutoff).isoformat(),actual_combined_at=datetime.now(UTC).isoformat(),
        source_contexts=deepcopy(provenance),producer_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


def current_history_components(refs, current, *, cutoff, before_period, canonical_ids):
    """Named current consumer of verified, already-retained prior-season facts.

    Original historical availability stays unproven. This is a new current
    consumption receipt, not promotion of a retrospective forecast to live truth.
    Refs must come from the ledger-owned model result, never client paths.
    """
    if not refs:return current
    history=load_component_sources(refs,cutoff=cutoff)
    for context in history['provenance']['source_contexts']:
        original=context['provenance'];descriptor=original.get('original_source_descriptor') or {}
        manifest=descriptor.get('manifest') or {};path=Path(descriptor.get('path','')).resolve()
        repo=ROOT.parent
        if not path.is_relative_to(repo) or not path.is_file():raise ValueError('Historical raw source outside repository')
        if (path.stat().st_size!=manifest.get('bytes') or path.stat().st_size>128*1024*1024
                or hashlib.sha256(path.read_bytes()).hexdigest()!=manifest.get('sha256')):
            raise ValueError('Historical raw source checksum mismatch')
        if clock(manifest.get('received_at')) is None or clock(manifest['received_at'])>clock(cutoff):
            raise ValueError('Historical raw source unavailable at current cutoff')
        if original.get('source',{}).get('content_sha256')!=manifest['sha256']:
            raise ValueError('Historical derived/raw source linkage differs')
    for row in history['actor_game_rows']:
        if period(row['game_id'])//100>=before_period//100:raise ValueError('Current history must be strictly prior-season')
        pid=row.get('player_master_id')
        if pid is not None and canonical_ids.get(row['source_player_id'])!=pid:
            raise ValueError('Historical canonical alias no longer agrees with current source identity')
    for row in history['team_denominators']:
        if period(row['game_id'])//100>=before_period//100:raise ValueError('Current history contains current/future season')
    out=combine_component_sources([history,current],provenance=[history['provenance'],current['provenance']],cutoff=cutoff)
    out.update(evidence_use='current_inference_from_verified_revised_history',pregame_serving_eligible=True,
        current_consumer_contract='new_model_primary_v1')
    out['provenance']['original_historical_pregame_availability_proven']=False
    out['provenance']['current_history_refs']=deepcopy(refs)
    out['semantic_measurements_sha256']=digest({k:v for k,v in out.items() if k not in {'provenance','semantic_measurements_sha256'}})
    return out
