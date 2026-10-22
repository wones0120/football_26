"""Bounded semantic research requests and authored publication/Prepare receipts.

This is a handoff to the existing Codex research worker, not a football author or
an agent running inside the solver. A neutral scenario never proves research.
"""
from copy import deepcopy
from pathlib import Path
import json
import math
import re
from uuid import UUID
from zoneinfo import ZoneInfo

from .analyst_packets import clock, packet_digest
from .analyst_shadow import digest
from .market_snapshots import canonical_team

CONTRACT = 'analyst_research_request_v1'
PRODUCER_CONTRACT = 'analyst_authored_research_v1'
DIRECTORY = Path('artifacts/analyst_research_requests')
MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_LEGACY_ENVELOPE_BYTES = 8 * 1024 * 1024
FACT_FIELDS = (
    'position', 'official_availability_status', 'availability_status',
    'availability_state', 'injury_status', 'pregame_injury_status',
    'designation_evidence_class', 'designation_conflict',
    'role_active', 'role_rostered', 'canonical_role', 'expected_depth_role',
    'role_availability', 'pregame_role_uncertain',
    'role_change', 'role_starter_evidence', 'is_starting_qb',
    'starting_qb_source', 'kicker_role', 'kicker_role_eligible',
    'practice_participation', 'practice_trend', 'expected_workload_status',
    'projected_targets', 'projected_carries', 'pregame_expected_targets',
    'pregame_expected_carries', 'pregame_expected_routes', 'pregame_expected_snaps',
    'pregame_target_share', 'pregame_carry_share',
    'game_total_line', 'team_spread_line', 'team_implied_total',
    'opponent_implied_total',
)
SOURCE_FIELDS = (
    'source_system', 'source', 'source_uri', 'source_native_key', 'source_player_id', 'source_player_key',
    'status', 'game_status', 'practice_participation', 'designation',
    'injury_status', 'injury_details', 'injury', 'practice_status',
    'evidence_class', 'role', 'starter', 'team', 'position',
    'published_at', 'source_published_at', 'modified_at', 'source_modified_at',
    'effective_at', 'source_effective_at',
    'original_observed_at', 'semantic_content_sha256',
    'total', 'spread', 'home_spread', 'game_total',
)
FACT_CLOCKS = ('availability_observed_at', 'role_observed_at', 'practice_observed_at',
               'expected_workload_observed_at', 'starting_qb_observed_at')


def _league_http_report(value):
    """Exact existing NFL weekly HTTP producer, whose observation is capture time."""
    return (isinstance(value, dict) and value.get('source') == 'nfl_official'
            and bool(re.fullmatch(r'https://www\.nfl\.com/injuries/league/\d{4}/reg\d{1,2}',
                                  str(value.get('source_uri') or '')))
            and (value.get('kind') == 'game_status'
                 or (value.get('evidence_json') or value.get('evidence') or {}).get('observation_basis') == 'http_response_clock'))


def _original_facts(value, *, recapture=False):
    """Keep semantic nested evidence; discard only execution/recapture identity."""
    if isinstance(value, dict):
        league_http = _league_http_report(value)
        recapture = (recapture or league_http or value.get('observation_basis') == 'current_native_slate_designation'
                     or bool(value.get('published_at') or value.get('effective_at')
                             or value.get('original_observed_at')))
        ignored = {'captured_at', 'received_at', 'ingested_at', 'imported_at',
                   'checked_at', 'evaluated_at', 'context_run_id', 'snapshot_id', 'ingest_run_id',
                   'derived_snapshot_id', 'source_snapshot_id', 'pdf_snapshot_id'}
        if league_http:
            ignored.add('pregame_player_context_id')
        if recapture:
            ignored |= {'observed_at', 'source_ids'}
        return {str(k): _original_facts(v, recapture=recapture) for k, v in sorted(value.items())
                if k not in ignored}
    if isinstance(value, list):
        normalized = [_original_facts(v, recapture=recapture) for v in value]
        return sorted({digest(v): v for v in normalized}.values(), key=digest)
    return _value(value)


def _canonical_context_facts(evidence):
    """Normalize only known composition retrieval wrappers, not report history."""
    wrappers = {'availability_observed_at', 'role_observed_at',
                'availability_source_ids', 'role_source_ids'}
    result = {k: _original_facts(v) for k, v in evidence.items()
              if k not in wrappers | {'starter_evidence', 'source_facts'}}
    if _league_http_report(evidence.get('workload_context')) and isinstance(evidence.get('practice_report'), dict):
        # compose_player_contexts retains this exact HTTP producer's report;
        # observed_at is its fetch clock, not a practice event date.
        result['practice_report'] = _original_facts(evidence['practice_report'], recapture=True)
    result['starter_evidence'] = _original_facts(evidence.get('starter_evidence'), recapture=True)
    if (evidence.get('binding_roster_unavailability') or {}).get('kind')=='roster_status':
        result['binding_roster_unavailability']=_original_facts(evidence['binding_roster_unavailability'],recapture=True)
    facts = [_original_facts(f, recapture=f.get('kind') in {'role', 'starting_qb', 'roster_status'})
             for f in evidence.get('source_facts', [])]
    result['source_facts'] = sorted({digest(f): f for f in facts}.values(), key=digest)
    return result


def _check_clocks(value, decision):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {'published_at', 'source_published_at', 'original_observed_at',
                       'modified_at', 'source_modified_at',
                       'effective_at', 'source_effective_at', 'observed_at',
                       'available_at', 'received_at', 'ingested_at', 'captured_at', 'imported_at'} and item:
                if key == 'imported_at':
                    # The existing IngestRun.started_at column uses utcnow_naive.
                    # This internal receipt convention never applies to source
                    # publication, observation or external capture timestamps.
                    from .factual_designation import clock as internal_clock
                    observed = internal_clock(item)
                else:
                    observed = clock(str(item))
                if observed > decision:
                    raise ValueError('Future research source/role evidence')
            elif isinstance(item, (dict, list)):
                _check_clocks(item, decision)
    elif isinstance(value, list):
        for item in value:
            _check_clocks(item, decision)


def _value(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _value(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_value(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def semantic_dependencies(*, games, rows, checked_at, source_manifest=None,
                          workload_receipt=None):
    """Freeze full supplied canonical context, never an eligibility-filtered pool.

    Publication/effective facts remain dependencies. Recapture/ingest IDs and
    clocks are retained as provenance but do not renew authored research. Missing
    fields remain null. Callers must disclose if their reference universe is partial.
    """
    decision = clock(checked_at)
    if not 1 <= len(games) <= 32 or len(rows) > 4096:
        raise ValueError('Research dependency scope exceeds bounded limits')
    manifest = source_manifest or {}
    scope = manifest.get('scope') or {}
    games = [{**g, 'season': g.get('season', scope.get('season')),
              'week': g.get('week', scope.get('week'))} for g in games]
    ids = [str(g['game_id']) for g in games]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate research game identity')
    teams = {str(g['game_id']): {canonical_team(str(t or '')) for t in
             (g.get('teams') or [g.get('home_team'), g.get('away_team')])} for g in games}
    if any(len(t) != 2 or '' in t for t in teams.values()):
        raise ValueError('Research requires two resolved teams per game')
    grouped = {gid: [] for gid in ids}
    provenance = {gid: [] for gid in ids}
    seen = set()
    for row in rows:
        pid = str(row.get('player_id') or row.get('player_master_id') or '')
        try:
            UUID(pid)
        except ValueError as exc:
            raise ValueError('Research requires canonical player UUID') from exc
        if pid in seen:
            raise ValueError('Duplicate canonical research actor')
        seen.add(pid)
        team = canonical_team(str(row.get('player_team') or row.get('team') or ''))
        opponent = canonical_team(str(row.get('opponent_team') or row.get('opponent') or ''))
        explicit = str(row.get('canonical_game_id') or '')
        native = str(row.get('game_id') or row.get('game_info') or '')
        if not explicit and native in ids:
            explicit = native
        matches = [gid for gid in ids if team in teams[gid] and opponent in teams[gid]
                   and team != opponent and (not explicit or explicit == gid)]
        if len(matches) != 1:
            raise ValueError('Research actor game identity missing or ambiguous')
        game = next(g for g in games if str(g['game_id']) == matches[0])
        for key in ('season', 'week'):
            if row.get(key) is not None and game.get(key) is not None and int(row[key]) != int(game[key]):
                raise ValueError('Research actor period conflicts with canonical game')
        if native and native not in ids:
            # The public salary adapter historically calls DK Game Info
            # `game_id`. Keep that native serving key distinct from canonical
            # schedule identity, and validate its known team/date semantics.
            info = re.match(r'^([A-Z]{2,3})@([A-Z]{2,3})(?:\s+(\d{2}/\d{2}/\d{4}))?', native)
            if not info or {canonical_team(info[1]), canonical_team(info[2])} != teams[matches[0]]:
                raise ValueError('Native game identity conflicts with canonical game')
            if info[3] and info[3] != clock(game['kickoff_at']).astimezone(ZoneInfo('America/New_York')).strftime('%m/%d/%Y'):
                raise ValueError('Native game date conflicts with canonical game')
        for key in FACT_CLOCKS:
            if row.get(key) and clock(str(row[key])) > decision:
                raise ValueError('Future research role/availability evidence')
        designation = row.get('designation_resolution') or {}
        _check_clocks(designation, decision)
        starter = row.get('role_starter_evidence')
        _check_clocks(starter, decision)
        for field in FACT_FIELDS:
            if isinstance(row.get(field), (dict, list)):
                _check_clocks(row[field], decision)
        facts = {k: _value(row.get(k)) for k in FACT_FIELDS}
        facts['role_starter_evidence'] = _original_facts(starter, recapture=True)
        if isinstance(starter, dict):
            from .workload_count_forecast import verified_current_role
            facts['current_role_evidence_verified'] = verified_current_role(row, cutoff=checked_at) is not None
        grouped[matches[0]].append(dict(player_master_id=pid, team=team,
            opponent=opponent, facts=facts,
            designation_resolution=_original_facts(designation)))
        provenance[matches[0]].append(dict(player_master_id=pid,
            native_game_id=native or None, canonical_game_id=matches[0],
            original_role_evidence=_value(starter), original_designation_resolution=_value(designation),
            original_fact_clocks={k: _value(row.get(k)) for k in FACT_CLOCKS}))
    records = []
    for game in sorted(games, key=lambda g: str(g['game_id'])):
        gid = str(game['game_id'])
        if clock(game['kickoff_at']) <= decision:
            raise ValueError('Research request must be pregame')
        actors = sorted(grouped[gid], key=lambda r: r['player_master_id'])
        actor_ids = {r['player_master_id'] for r in actors}
        sources = []
        original_sources = []
        for family in ('injuries', 'starters', 'availability', 'markets'):
            for source in manifest.get(family, []):
                source_gid = str(source.get('game_id') or '')
                pid = str(source.get('player_master_id') or source.get('player_id') or '')
                team = canonical_team(source['team']) if source.get('team') else None
                if pid in actor_ids and source_gid and source_gid != gid:
                    raise ValueError('Research source explicitly conflicts with canonical game')
                if source_gid != gid and pid not in actor_ids and not (not source_gid and team in teams[gid]):
                    continue
                for key in ('season', 'week'):
                    if source.get(key) is not None and game.get(key) is not None and int(source[key]) != int(game[key]):
                        raise ValueError('Research source period conflicts with canonical game')
                fact = {k: _value(source.get(k)) for k in SOURCE_FIELDS if source.get(k) is not None}
                if source.get('evidence_json'):
                    evidence = source['evidence_json']
                    # Canonical composition explicitly separates current values
                    # from the retrieval/source-row lineage retained below.
                    from .showdown_player_context import CONTEXT_CONTRACT
                    composed = family == 'availability' and evidence.get('canonical_context_contract') == CONTEXT_CONTRACT
                    fact['evidence'] = _canonical_context_facts(evidence) if composed else _original_facts(evidence, recapture=_league_http_report(source))
                _check_clocks(source, decision)
                original_sources.append(dict(family=family, record=_value(source)))
                for key in ('published_at', 'source_published_at', 'original_observed_at'):
                    if fact.get(key) and clock(fact[key]) > decision:
                        raise ValueError('Future research source evidence')
                sources.append(dict(family=family, player_master_id=pid or None, facts=fact))
        sources = sorted({digest(s): s for s in sources}.values(), key=digest)
        counts = []
        original_counts = []
        for actor in (workload_receipt or {}).get('players', []):
            if str(actor.get('player_master_id')) in actor_ids:
                _check_clocks(actor, decision)
                original_counts.append(_value(actor))
                semantic = {k: _value(actor.get(k)) for k in (
                    'player_master_id', 'team', 'position', 'canonical_role', 'evidence_kind',
                    'version', 'conditional_on', 'counts', 'unreconciled_counts', 'raw_history',
                    'reasons', 'history_window_status', 'role_window', 'native_salary_actor', 'utility')}
                semantic['current_role_evidence'] = _original_facts(actor.get('current_role_evidence'), recapture=True)
                semantic['verified_inactive_gaps'] = _original_facts(actor.get('verified_inactive_gaps') or [], recapture=True)
                counts.append(semantic)
        from .opportunity_source_publication import semantic_game_context
        opportunity_context=manifest.get('opportunity_source') or {}
        _check_clocks(opportunity_context,decision)
        if opportunity_context.get('status')=='available_descriptive' and opportunity_context.get('before_period')!=game['season']*100+game['week']:
            raise ValueError('Opportunity measurement period differs from researched game')
        measured_context=semantic_game_context(opportunity_context,teams=teams[gid],actor_ids=actor_ids)
        semantics = dict(game_id=gid, teams=sorted(teams[gid]),
            kickoff_at=clock(game['kickoff_at']).isoformat(),
            season=game.get('season'), week=game.get('week'),
            actors=actors, source_facts=sources, count_forecasts=sorted(counts, key=digest),
            count_contract=(workload_receipt or {}).get('version'),opportunity_measurements=measured_context)
        response=(workload_receipt or {}).get('component_response')
        inference=(workload_receipt or {}).get('team_opportunity_model_inference')
        if response:
            if response['before_period']!=game['season']*100+game['week']:
                raise ValueError('Component response period differs from researched game')
            values=deepcopy(response['semantic_values'])
            for key in ('reference','new'):
                values[key]['players']=[p for p in values[key]['players'] if p.get('team') in teams[gid]]
                values[key]['teams']={t:v for t,v in values[key]['teams'].items() if t in teams[gid]}
            values['players']=[p for p in values['players'] if p.get('team') in teams[gid]]
            values['efficiency']['actors']={p:v for p,v in values['efficiency']['actors'].items() if v.get('team') in teams[gid]}
            for key in ('reference_shared_budgets','new_shared_budgets'):
                values[key]={t:v for t,v in values[key].items() if t in teams[gid]}
            values['efficiency']['teams']={t:v for t,v in values['efficiency']['teams'].items() if t in teams[gid]}
            semantics['count_component_response']=dict(version=response.get('version'),
                full_source_response_semantic_sha256=digest(values),
                actor_deltas=[{k:p.get(k) for k in ('player_master_id','team','world_activity','base_fp','conditional_mean',
                    'conditional_delta_points','linear_component_delta_points','supported_components','anchor_inconsistency')}
                    for p in values['players'] if p.get('player_master_id') in actor_ids],
                proof_location='Immutable prepared workload receipt component_response; full rates/reference/universe not duplicated in request')
        if inference and inference.get('status')=='forecast_complete':
            semantics['team_count_model']={**deepcopy(inference['semantic_values']),
                'rows':[r for r in inference['inference_rows'] if r['game_id']==gid]}
        records.append(dict(game_id=gid, dependency_sha256=digest(semantics),
            semantics=semantics, canonical_actor_count=len(actors),
            original_actor_provenance=sorted(provenance[gid], key=lambda r: r['player_master_id']),
            original_source_provenance=sorted(original_sources, key=digest),
            original_count_provenance=sorted(original_counts, key=digest),
            original_component_receipt_sha256=(workload_receipt or {}).get('sha256') if response else None,
            original_opportunity_provenance=deepcopy((manifest.get('opportunity_source') or {}).get('provenance')),
            unknowns=['Supplied canonical context is not proof of full NFL roster/source coverage.',
                      'Missing source publication/role facts remain unknown; no replacement allocation inferred.']))
    return dict(contract_id=CONTRACT, checked_at=checked_at, games=records,
        source_provenance_sha256=digest(_value(manifest)),
        dependency_sha256=digest({r['game_id']: r['dependency_sha256'] for r in records}))


def _write(kind, key, value, directory=None):
    root = (Path(directory) if directory is not None else DIRECTORY) / kind
    root.mkdir(parents=True, exist_ok=True)
    path = root / (key + '.json')
    value = {**value, 'record_sha256': digest(value)}
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(payload) > MAX_RECORD_BYTES:
        from .research_receipt_storage import pack
        payload = json.dumps(pack(value, expanded_limit=MAX_LEGACY_ENVELOPE_BYTES),
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        if len(payload) > MAX_RECORD_BYTES:
            raise ValueError('Research logical receipt exceeds bounded size')
    try:
        with path.open('xb') as handle:
            handle.write(payload)
    except FileExistsError:
        existing = _read(path)
        if existing.get('identity') != value['identity']:
            raise ValueError('Research immutable receipt identity mismatch')
        return existing
    return value


def _read(path):
    with Path(path).open('rb') as handle:
        raw = handle.read(MAX_LEGACY_ENVELOPE_BYTES + 1)
    if len(raw) > MAX_LEGACY_ENVELOPE_BYTES:
        raise ValueError('Research legacy receipt envelope exceeds bounded size')
    value = json.loads(raw)
    from .research_receipt_storage import CONTRACT as STORAGE_CONTRACT, unpack
    shared = isinstance(value, dict) and value.get('storage_contract') == STORAGE_CONTRACT
    if shared:
        if len(raw) > MAX_RECORD_BYTES:
            raise ValueError('Research logical receipt exceeds bounded size')
        value = unpack(value, expanded_limit=MAX_LEGACY_ENVELOPE_BYTES)
    # Legacy receipts keep their original logical limit. New shared-object
    # envelopes fit the same 4 MiB storage bound and reconstruct all facts
    # within the existing 8 MiB read envelope, with checked object digests.
    # Never truncate facts or rewrite original bytes.
    logical = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if not shared and len(logical) > MAX_RECORD_BYTES:
        raise ValueError('Research logical receipt exceeds bounded size')
    if digest({k: v for k, v in value.items() if k != 'record_sha256'}) != value.get('record_sha256'):
        raise ValueError('Research receipt checksum mismatch')
    return value


def load_request(key, *, directory=None):
    if not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
        raise ValueError('Invalid research request identity')
    root = Path(directory) if directory is not None else DIRECTORY
    value = _read(root / 'requests' / (key + '.json'))
    if value.get('request_id') != key or digest(value['identity']) != key:
        raise ValueError('Research request identity mismatch')
    return value


def ensure_requests(dependencies, *, prior_packet_sha256, requested_at,
                    current_binding=None, directory=None):
    """One immutable request per affected game, no source/solver job execution."""
    clock(requested_at)
    bound = {g['game_id']: g for g in (current_binding or {}).get('games', [])}
    requests = []
    for game in dependencies['games']:
        known = bound.get(game['game_id'], {})
        if known.get('dependency_sha256') == game['dependency_sha256'] and known.get('disposition') in {'material', 'no_change'}:
            continue
        identity = dict(contract_id=CONTRACT, game_id=game['game_id'],
            dependency_sha256=game['dependency_sha256'], prior_packet_sha256=prior_packet_sha256)
        key = digest(identity)
        value = dict(request_id=key, identity=identity, requested_at=requested_at,
            status='refresh_pending', dependency=game,
            producer_instruction='Investigate only this affected game; publish sourced typed mechanisms or an explicit sourced no-change assessment; then run fresh Prepare and close its binding. No solver-side research or automatic opportunity transfer.')
        requests.append(_write('requests', key, value, directory))
    return requests


def _material_scenarios(packet, gid):
    result = []
    for scenario in (packet.get('scenario_assumptions') or {}).get('scenarios', []):
        for a in scenario.get('assumptions', []):
            if a.get('game_id') != gid or not a.get('elasticity'):
                continue
            field, neutral = ('factor', 1) if a.get('kind') in {'passing_volume', 'rushing_volume'} else ('share_delta', 0) if a.get('kind') == 'target_concentration' else ('fraction', 0)
            if a.get(field, neutral) != neutral:
                result.append(scenario['scenario_id'])
                break
    return set(result)


def validate_producer(packet, *, original_publication=False):
    """Validate authored scope and mechanism assertions without inventing truth."""
    binding = packet.get('research_producer')
    if binding is None:
        return []
    errors = []
    if binding.get('contract_id') != PRODUCER_CONTRACT or not binding.get('producer'):
        return ['Invalid authored research producer contract/identity']
    completed = clock(binding['completed_at'])
    if completed > clock(packet['decision_at']):
        errors.append('Research completion after packet decision')
    games = {g['game_id']: g for g in packet['games']}
    sources = {s['source_id']: s for s in packet['sources']}
    seen = set()
    for assessment in binding.get('games', []):
        gid = assessment.get('game_id')
        if gid not in games or gid in seen:
            errors.append('Duplicate/out-of-scope authored research game')
            continue
        seen.add(gid)
        if completed >= clock(games[gid]['kickoff_at']):
            errors.append('Authored research is not pregame')
        if assessment.get('authored_at') and clock(assessment['authored_at']) > completed:
            errors.append('Original game research clock exceeds producer completion')
        for key in ('request_id', 'dependency_sha256'):
            value = assessment.get(key)
            if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
                errors.append('Invalid research ' + key)
        if assessment.get('disposition') not in {'material', 'no_change', 'partial'}:
            errors.append('Unknown authored research disposition')
        for key in ('mechanism', 'counterevidence', 'unknowns'):
            if not assessment.get(key):
                errors.append('Authored research requires ' + key)
        refs = assessment.get('source_ids') or []
        if not refs or any(s not in sources or sources[s].get('coverage') != 'verified' for s in refs):
            errors.append('Authored research requires verified sources')
        authored_at = clock(assessment.get('authored_at') or binding['completed_at'])
        for sid in refs:
            source = sources.get(sid, {})
            if any(source.get(key) and clock(source[key]) > authored_at
                   for key in ('available_at', 'observed_at', 'published_at', 'modified_at')):
                errors.append('Research completed before cited source evidence was available')
        material = _material_scenarios(packet, gid)
        named = set(assessment.get('scenario_ids') or [])
        derivative = not original_publication and bool(packet.get('preparation_compatibility') or packet.get('intent_scope'))
        if assessment.get('disposition') == 'material' and (not named or (not derivative and not named <= material)):
            errors.append('Material research requires a nonneutral typed scenario for its game')
        if assessment.get('disposition') == 'no_change' and named:
            errors.append('No-change research cannot claim material scenario consumption')
    if not seen:
        errors.append('Authored research requires game assessments')
    return errors


def publish_research(requests, packet, *, assessments, producer, completed_at,
                     directory=None, packet_directory=None):
    """Callable producer completion: normal immutable packet validation/import."""
    from .analyst_packets import import_packet
    authored = deepcopy(packet)
    if not requests or len(requests) > 32:
        raise ValueError('Authored publication requires bounded pending requests')
    for request in requests:
        if load_request(request['request_id'], directory=directory) != request:
            raise ValueError('Research publication differs from immutable pending request')
    by_id = {r['identity']['game_id']: r for r in requests}
    if set(by_id) != {a['game_id'] for a in assessments}:
        raise ValueError('Research response must account for every requested game')
    bound = []
    # Retain genuinely unaffected prior authored game assessments when a
    # producer revises one game in a multigame packet.
    previous_binding = authored.get('research_producer') or {}
    previous = previous_binding.get('games', [])
    for assessment in assessments:
        request = by_id[assessment['game_id']]
        if clock(completed_at) < clock(request['requested_at']):
            raise ValueError('Research completion precedes request')
        bound.append({**deepcopy(assessment), 'request_id': request['request_id'],
            'dependency_sha256': request['identity']['dependency_sha256'],
            'authored_at': completed_at, 'producer': producer})
    bound.extend({**deepcopy(a), 'authored_at': a.get('authored_at', previous_binding.get('completed_at')),
                  'producer': a.get('producer', previous_binding.get('producer'))}
                 for a in previous if a['game_id'] not in by_id)
    authored['research_producer'] = dict(contract_id=PRODUCER_CONTRACT,
        producer=producer, completed_at=completed_at, games=bound)
    errors = validate_producer(authored, original_publication=True)
    if errors:
        raise ValueError('; '.join(errors))
    published = import_packet(authored, directory=packet_directory)
    identity = dict(contract_id=PRODUCER_CONTRACT, packet_sha256=published['analyst_packet_sha256'],
                    request_ids=sorted(r['request_id'] for r in requests))
    return _write('publications', digest(identity), dict(identity=identity,
        publication_id=digest(identity), status='published_prepare_pending',
        packet=published, research_producer=authored['research_producer']), directory)


def coverage(packet, dependencies, *, directory=None):
    binding = (packet or {}).get('research_producer') or {}
    bound = {g['game_id']: g for g in binding.get('games', [])}
    games = []
    for game in dependencies['games']:
        authored = bound.get(game['game_id'])
        state = 'reference_only'
        if authored:
            if authored['dependency_sha256'] != game['dependency_sha256']:
                state = 'refresh_pending'
            elif authored['disposition'] == 'partial':
                state = 'mechanisms_partial'
            elif authored['disposition'] == 'no_change':
                state = 'mechanisms_current'
            else:
                state = 'mechanisms_current' if set(authored['scenario_ids']) <= _material_scenarios(packet, game['game_id']) else 'mechanisms_partial'
        games.append(dict(game_id=game['game_id'], state=state,
            dependency_sha256=game['dependency_sha256'],
            authored_assessment=deepcopy(authored)))
    states = {g['state'] for g in games}
    status = ('refresh_pending' if 'refresh_pending' in states else
              'reference_only' if states == {'reference_only'} else
              'mechanisms_current' if states == {'mechanisms_current'} else 'mechanisms_partial')
    closure = _matching_closure(packet, dependencies, directory=directory) if status == 'mechanisms_current' else None
    return dict(contract_id=PRODUCER_CONTRACT, status=status, games=games,
        dependency_sha256=dependencies['dependency_sha256'],
        probability_status='Conditional mechanisms/no-change review; no calibrated occurrence probabilities',
        producer_executed=bool(binding), producer_loop_closed=bool(closure), closure_receipt=closure)


def _matching_closure(packet, dependencies, *, directory=None):
    if not packet:
        return None
    root = (Path(directory) if directory is not None else DIRECTORY) / 'closures'
    if not root.exists():
        return None
    paths = sorted(root.glob('*.json'))
    if len(paths) > 1000:
        raise ValueError('Research closure ledger exceeds bounded selection limit')
    original = ((packet.get('intent_scope') or {}).get('authoring_packet_sha256')
                or (packet.get('preparation_compatibility') or {}).get('original_packet_sha256')
                or packet_digest(packet))
    matching = []
    for path in paths:
        value = _read(path)
        if value.get('packet_sha256') == original and value.get('dependency_sha256') == dependencies['dependency_sha256']:
            matching.append(value)
    return max(matching, key=lambda v: (clock(v['checked_at']), v['publication_id'])) if matching else None


def finish_preparation(publication, handoff, dependencies, *, directory=None):
    """Close only a new validated published packet actually bound by Prepare."""
    from .analyst_packets import load_packet
    root = Path(directory) if directory is not None else DIRECTORY
    if digest(publication['identity']) != publication.get('publication_id'):
        raise ValueError('Invalid research publication identity')
    if _read(root / 'publications' / (publication['publication_id'] + '.json')) != publication:
        raise ValueError('Publication differs from immutable research receipt')
    expected = publication['packet']['analyst_packet_sha256']
    if handoff.get('source_packet_sha256') != expected or not handoff.get('checked_packet_sha256'):
        raise ValueError('Fresh Prepare did not bind authored publication')
    if digest({k: v for k, v in handoff.items() if k != 'compatibility_sha256'}) != handoff.get('compatibility_sha256'):
        raise ValueError('Invalid prepared research compatibility receipt')
    if (handoff.get('research_coverage') or {}).get('dependency_sha256') != dependencies['dependency_sha256']:
        raise ValueError('Prepare receipt has a different research dependency binding')
    if (handoff.get('research_coverage') or {}).get('status') != 'mechanisms_current':
        raise ValueError('Prepare has no complete current authored research coverage')
    packet_root = Path(publication['packet']['path']).parent
    published_packet = load_packet(expected, directory=packet_root)
    checked = load_packet(handoff['checked_packet_sha256'], directory=packet_root)
    actual_coverage = coverage(checked, dependencies, directory=directory)
    if actual_coverage['status'] != 'mechanisms_current' or validate_producer(published_packet, original_publication=True):
        raise ValueError('Surviving checked packet lacks current authored mechanisms')
    current = {g['game_id']: g['dependency_sha256'] for g in dependencies['games']}
    if any(current.get(g['game_id']) != g['dependency_sha256']
           for g in publication['research_producer']['games']):
        raise ValueError('Research dependencies changed before fresh Prepare')
    if clock(handoff['checked_at']) < clock(publication['research_producer']['completed_at']):
        raise ValueError('Prepare predates authored research completion')
    identity = dict(publication_id=publication['publication_id'],
        prepared_compatibility_sha256=handoff['compatibility_sha256'])
    return _write('closures', digest(identity), dict(identity=identity,
        status='producer_closed', publication_id=publication['publication_id'],
        packet_sha256=expected, dependency_sha256=dependencies['dependency_sha256'],
        prepared_source_sha256=handoff['prepared_source_sha256'],
        checked_packet_sha256=handoff['checked_packet_sha256'],
        request_ids=publication['identity']['request_ids'],
        checked_at=handoff['checked_at']), directory)
