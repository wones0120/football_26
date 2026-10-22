"""Find source annotations without treating narrative as adjudicated clock state."""
import re
from research.game_progression_pilot_20261020.control_linkage.linkage import clock_format,final_row
from research.game_progression_pilot_20261020.observation_contract.contract import native_key

PATTERNS={
    'restart':r'clock.{0,30}(?:start|restart)|(?:start|restart).{0,30}clock',
    'runoff':r'run[\s-]?off',
    'reset_or_correction':r'clock.{0,30}(?:reset|set to|adjust|correct)|(?:reset|adjust|correct).{0,30}clock'}
COMPILED={k:re.compile(v,re.I)for k,v in PATTERNS.items()}

def mentions(raw):
    text=raw.get('desc')
    if not isinstance(text,str):return []
    result=[]
    for kind,pattern in COMPILED.items():
        for match in pattern.finditer(text):
            result.append(dict(kind=kind,span=[match.start(),match.end()],matched_text=match.group(),
                evidence_status='NARRATIVE_CANDIDATE_REQUIRES_ADJUDICATION',native_id=native_key(raw),
                source_finality_qualified=final_row(raw),
                play_end_game_clock=None,runoff_seconds=None,restart_policy=None,enforcement_proven=False))
    return result

def field_format(field,value):
    if field in ('time_of_day','end_clock_time'):return clock_format(value)
    if value in(None,''):return 'MISSING'
    if field=='play_clock'and value in(0,'0'):return 'REPORTED_ZERO_NOT_GAME_CLOCK'
    return 'REPORTED_VALUE_NOT_PLAY_END_PROOF'
