"""Resolve source-scoped ownership observations without global name-only matching."""
from __future__ import annotations

import hashlib
import json

import pandas as pd
from sqlalchemy import text

from Database.player_identity import strip_name_suffix
from .target_schema import validate_target_schema


def resolve_observations(rows: pd.DataFrame, salaries: pd.DataFrame) -> pd.DataFrame:
    result = rows.copy()
    candidates = salaries.copy()
    if not candidates.empty:
        candidates['_name'] = candidates['player_name'].map(strip_name_suffix)
    decisions = []
    for row in rows.to_dict('records'):
        name = strip_name_suffix(row['player_display_name'])
        slot = str(row['roster_position']).strip().upper()
        matches = candidates[candidates['_name'] == name].copy() if not candidates.empty else candidates
        if not matches.empty:
            # A source slot or a natural position must be compatible; FLEX is format-specific.
            showdown = matches['roster_position'].astype(str).str.upper().isin(['CPT', 'FLEX']).any() and (matches['roster_position'].astype(str).str.upper() == 'CPT').any()
            positions = {'RB', 'WR', 'TE'} if slot == 'FLEX' and not showdown else {slot}
            legal = matches['position'].astype(str).str.upper().isin(positions)
            if showdown and slot in {'CPT', 'FLEX'}:
                legal = matches['roster_position'].astype(str).str.upper().eq(slot)
            matches = matches[legal]
        evidence = []
        for candidate in matches.to_dict('records'):
            evidence.append({key: None if pd.isna(candidate.get(key)) else str(candidate.get(key))
                             for key in ('curated_salary_id', 'ingest_run_id', 'source_player_key', 'player_master_id', 'team', 'opponent', 'position', 'roster_position')})
        identities = {(candidate['player_master_id'], candidate['team'], candidate['position']) for candidate in evidence}
        complete = evidence and all(all(candidate.get(key) for key in ('source_player_key', 'player_master_id', 'team', 'opponent')) for candidate in evidence)
        status = 'resolved' if complete and len(identities) == 1 else 'ambiguous' if len(identities) > 1 else 'unresolved'
        decisions.append({'player_id': next(iter(identities))[0] if status == 'resolved' else None,
                          'resolution_status': status,
                          'identity_evidence': {'policy': 'slate_salary_slot_unique_v1', 'normalized_name': name, 'salary_candidates': evidence}})
    for key in ('player_id', 'resolution_status', 'identity_evidence'):
        result[key] = [decision[key] for decision in decisions]
    result['player_master_id'] = result['player_id']
    return result


def attach_salary_identities(engine, rows: pd.DataFrame) -> pd.DataFrame:
    groups = []
    for (season, week, slate), group in rows.groupby(['season', 'week', 'slate'], sort=False):
        with engine.connect() as connection:
            salaries = pd.read_sql(text('''SELECT curated_salary_id, ingest_run_id, source_player_key,
                player_master_id::text, player_name, team, opponent, position, roster_position
                FROM curated_salary WHERE season=:season AND week=:week AND upper(slate)=upper(:slate)
                AND source_system='draftkings' ORDER BY curated_salary_id '''), connection,
                params={'season': int(season), 'week': int(week), 'slate': str(slate)})
        groups.append(resolve_observations(group, salaries))
    return pd.concat(groups).sort_index() if groups else rows.copy()


def persist_observations(engine, rows: pd.DataFrame) -> dict:
    validate_target_schema(engine, consumer="Contest ownership observations",
                           required_tables=("contest_ownership_observation",))
    payloads = []
    for row in rows.to_dict('records'):
        payload = {key: row[key] for key in ('contest_id', 'source_file_id', 'season', 'week', 'slate', 'player_display_name', 'roster_position', 'player_id', 'resolution_status')}
        payload.update(actual_ownership=float(row['pct_drafted']), actual_points=None if pd.isna(row.get('fpts')) else float(row['fpts']),
                       evidence_json=json.dumps(row['identity_evidence'], sort_keys=True))
        payload['observation_id'] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        payloads.append(payload)
    with engine.begin() as connection:
        if payloads:
            connection.execute(text('''INSERT INTO target.contest_ownership_observation
                (observation_id,contest_id,source_file_id,season,week,slate,player_display_name,roster_position,
                 player_id,resolution_status,actual_ownership,actual_points,evidence_json)
                VALUES (:observation_id,:contest_id,:source_file_id,:season,:week,:slate,:player_display_name,:roster_position,
                        :player_id,:resolution_status,:actual_ownership,:actual_points,CAST(:evidence_json AS JSONB))
                ON CONFLICT (observation_id) DO NOTHING'''), payloads)
    return {status: int((rows['resolution_status'] == status).sum()) for status in ('resolved', 'unresolved', 'ambiguous')}
