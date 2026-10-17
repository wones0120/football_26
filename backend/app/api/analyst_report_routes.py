"""Report reading never creates jobs, imports packets or changes selections."""
from fastapi import APIRouter, HTTPException
from ..product_services import analyst_reports

router = APIRouter(prefix='/api/analyst-reports', tags=['analyst-reports'])

def _read(function, *args):
    try:
        return function(*args)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=503, detail='Report library is unavailable or the text limit was exceeded') from exc

@router.get('')
def report_catalog():
    return _read(analyst_reports.list_reports)

@router.get('/{report_id}')
def report_content(report_id: str):
    return _read(analyst_reports.read_report, report_id)

@router.get('/{report_id}/evidence/{evidence_id}')
def report_evidence(report_id: str, evidence_id: str):
    return _read(analyst_reports.read_evidence, report_id, evidence_id)
