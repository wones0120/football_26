"""Assess source schema without turning named endpoints into measured clocks."""
import re
from collections import Counter

def bind_event(summary,event_id,date,home,away):
    header=summary['header'];competitions=header['competitions']
    if header.get('id')!=event_id or len(competitions)!=1:raise ValueError('Unique native ESPN event required')
    competition=competitions[0];teams=competition['competitors']
    if (not competition['date'].startswith(date+'T')or len(teams)!=2
        or {r['homeAway']:r['team']['abbreviation']for r in teams}!={'home':home,'away':away}
        or len({r['team']['id']for r in teams})!=2):raise ValueError('Native date/home/away team identity differs')
    return dict(event_id=event_id,date=competition['date'],teams=[dict(home_away=r['homeAway'],native_team_id=r['team']['id'],abbreviation=r['team']['abbreviation'])for r in teams])

def plays(summary):
    rows=[p for drive in summary.get('drives',{}).get('previous',[])for p in drive.get('plays',[])]
    if summary.get('drives',{}).get('current'):raise ValueError('Historical completed-drive scope required')
    ids=[p.get('id')for p in rows]
    if any(not isinstance(k,str)or not k for k in ids)or len(set(ids))!=len(ids):raise ValueError('Unique native ESPN play IDs required')
    return rows

def schema_counts(rows):
    result=Counter();start=Counter();end=Counter()
    for row in rows:
        result['plays']+=1
        if row.get('clock',{}).get('displayValue')is not None:result['top_level_clock_values']+=1
        a=row.get('start')or{};b=row.get('end')or{}
        start.update(a.keys());end.update(b.keys())
        if any(k in b for k in ('clock','clockTime','endClockTime','gameClock')):result['end_clock_field_candidates']+=1
        if any(k in row for k in ('clockRunning','restart','runoff','clockCorrection','restartReason')):result['explicit_control_field_candidates']+=1
        # Candidate fields would still need semantics and native linkage validation.
    return dict(counts=dict(result),start_key_counts=dict(start),end_key_counts=dict(end),
        supported_play_end_clock_records=0,supported_restart_enforcement_records=0)

def pdf_mentions(text):
    return [name for name,pattern in {'runoff':r'run[\s-]?off','restart':r'clock.{0,30}(?:start|restart)|(?:start|restart).{0,30}clock','reset':r'clock.{0,30}(?:reset|correct|adjust)'}.items()if re.search(pattern,text,re.I)]
