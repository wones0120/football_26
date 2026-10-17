"""Read-only, bounded report library. Only catalogued text is served."""
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

RESEARCH_ROOT = Path(__file__).resolve().parents[3] / 'research'
CATALOG = RESEARCH_ROOT / 'analyst_reports/catalog.json'
MAX_BYTES = 256 * 1024
ID_PATTERN = r'^[a-z0-9][a-z0-9_-]{0,79}$'

class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evidence_id: str = Field(pattern=ID_PATTERN)
    path: str

class Report(BaseModel):
    model_config = ConfigDict(extra='forbid')
    report_id: str = Field(pattern=ID_PATTERN)
    title: str
    category: Literal['briefing', 'specialist', 'lineup_review']
    season: int | None = None
    week: int | None = None
    slates: list[str] = Field(default_factory=list)
    version: str
    recorded_at: AwareDatetime | None = None
    preliminary: bool | None = None
    application_status: Literal['research_only', 'saved_run_comparison', 'unknown']
    saved_run_ids: list[str] = Field(default_factory=list)
    summary: str
    path: str
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)

class Catalog(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1]
    reports: list[Report] = Field(max_length=100)

def _path(relative: str, markdown=False) -> Path:
    declared = Path(relative)
    if declared.is_absolute() or '..' in declared.parts or declared.suffix.lower() not in ({'.md'} if markdown else {'.md', '.json', '.csv', '.txt'}):
        raise ValueError('Invalid controlled report path')
    path = (RESEARCH_ROOT / declared).resolve()
    if not path.is_relative_to(RESEARCH_ROOT.resolve()):
        raise ValueError('Report path escapes library')
    return path

def _text(path: Path) -> str:
    # Read a bounded amount even if the file grows after the size check.
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Report exceeds library text limit')
    return data.decode('utf-8')

def _catalog() -> list[Report]:
    catalog_path = CATALOG.resolve()
    if not catalog_path.is_relative_to(RESEARCH_ROOT.resolve()):
        raise ValueError('Catalog escapes library')
    reports = Catalog.model_validate(json.loads(_text(catalog_path))).reports
    if len({r.report_id for r in reports}) != len(reports):
        raise ValueError('Duplicate report identifier')
    for report in reports:
        _path(report.path, markdown=True)
        if len({e.evidence_id for e in report.evidence}) != len(report.evidence):
            raise ValueError('Duplicate evidence identifier')
        for evidence in report.evidence:
            _path(evidence.path)
    return reports

def _metadata(report: Report) -> dict:
    return report.model_dump(mode="json", exclude={'path', 'evidence'}) | {'available': _path(report.path, markdown=True).is_file()}

def list_reports() -> dict:
    return {'rows': [_metadata(r) for r in _catalog()]}

def _find(report_id: str, reports: list[Report]) -> Report:
    if not re.fullmatch(ID_PATTERN, report_id):
        raise LookupError('Unknown report')
    report = next((r for r in reports if r.report_id == report_id), None)
    if report is None:
        raise LookupError('Unknown report')
    return report

def read_report(report_id: str) -> dict:
    reports = _catalog()
    report = _find(report_id, reports)
    path = _path(report.path, markdown=True)
    try:
        markdown = _text(path)
    except FileNotFoundError as exc:
        raise LookupError('Report is not available') from exc
    report_paths = {_path(r.path, markdown=True): r.report_id for r in reports}
    evidence_paths = {_path(e.path): e.evidence_id for e in report.evidence}
    links = []
    for target in dict.fromkeys(re.findall(r'\]\(([^\s)]+)\)', markdown)):
        if target.startswith(('https://', 'http://', '#')):
            continue
        local, _, fragment = target.partition('#')
        resolved = (path.parent / local).resolve()
        if resolved in report_paths:
            links.append({'target': target, 'kind': 'report', 'report_id': report_paths[resolved], 'fragment': fragment})
        elif resolved in evidence_paths and resolved.is_relative_to(RESEARCH_ROOT.resolve()):
            links.append({'target': target, 'kind': 'evidence', 'evidence_id': evidence_paths[resolved]})
        else:
            links.append({'target': target, 'kind': 'unavailable'})
    return {'report': _metadata(report), 'markdown': markdown, 'sha256': sha256(markdown.encode()).hexdigest(), 'links': links}

def read_evidence(report_id: str, evidence_id: str) -> dict:
    report = _find(report_id, _catalog())
    evidence = next((e for e in report.evidence if e.evidence_id == evidence_id), None)
    if evidence is None:
        raise LookupError('Unknown report evidence')
    path = _path(evidence.path)
    try:
        content = _text(path)
    except FileNotFoundError as exc:
        raise LookupError('Evidence is not available') from exc
    return {'report_id': report_id, 'evidence_id': evidence_id, 'label': path.name, 'content': content, 'sha256': sha256(content.encode()).hexdigest()}
