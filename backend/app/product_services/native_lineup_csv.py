"""Minimal lineup-upload CSV serialization using observed DraftKings slot layouts.

Per-format services prove canonical/native identity, scope, roles and readiness.
These files contain lineup IDs only, never contest/entry assignments or submission.
"""
import csv
import io

LAYOUTS = {'single_stat': ('FLEX', 'FLEX', 'FLEX'), 'tiers': ('T1', 'T2', 'T3', 'T4', 'T5', 'T6')}
SCHEMA_VERSION = 'draftkings_native_lineup_csv_v1'


def render_native_lineup_csv(headers, native_rosters):
    headers=tuple(headers)
    if headers != LAYOUTS['single_stat'] and (not headers or headers != tuple(f'T{i+1}' for i in range(len(headers)))):
        raise ValueError('Unsupported native lineup CSV slot layout')
    lineups=native_rosters
    if not lineups or len(lineups)>500: raise ValueError('Native lineup CSV requires 1–500 lineups')
    normalized=[]
    for lineup in lineups:
        ids=[str(value) for value in lineup]
        if len(ids)!=len(headers) or any(not value.isascii() or not value.isdigit() for value in ids):
            raise ValueError('Every native slot requires one exact numeric source ID')
        if len(set(ids))!=len(ids): raise ValueError('Duplicate native player in lineup CSV')
        normalized.append(ids)
    output=io.StringIO(newline='')
    csv.writer(output,lineterminator='\r\n').writerows([headers,*normalized])
    return output.getvalue().encode('utf-8')
