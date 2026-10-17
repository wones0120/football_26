"""Isolated native Single Stat imports and immutable research reports."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import Response
from ..product_services import single_stat_export as downloads

from ..db import get_db_session
from ..product_services import single_stat as service

router = APIRouter(prefix='/api/single-stat', tags=['single-stat'])


@router.get('/records')
def records():
    return {'rows': service.catalog(), 'warning': 'Library shows the latest 100 records.'}


@router.get('/records/{key}')
def record(key: str):
    try:
        value = service.load(key)
        return {**value, 'current_readiness': service.readiness(value)} if value['kind'] == 'pool' else value
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(status_code=404, detail='Single Stat record unavailable') from exc


@router.post('/pools')
def import_pool(request: service.PoolImport, session: Session = Depends(get_db_session)):
    try:
        value = service.import_pool(request, session)
        return {**value, 'current_readiness': service.readiness(value)}
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/optimize')
def optimize(request: service.Optimize):
    try: return service.optimize(request)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/actual-results')
def actual_results(request: service.ActualResult):
    try: return service.actual_result(request)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post('/templates')
def import_template(request: downloads.TemplateImport):
    try: return downloads.import_template(request)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/records/{key}/export-readiness')
def export_readiness(key: str):
    try: return downloads.export_readiness(key)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/records/{key}/download')
def download(key: str, template_sha256: str | None = None, accept_research: bool = False):
    try: filename, content, receipt = downloads.build_download(key, template_sha256, accept_research=accept_research)
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(content,media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{filename}"',
        'X-Single-Stat-Export-Receipt':receipt['sha256'],'X-Single-Stat-Entry-Ready':'false','X-Single-Stat-Classification':'RESEARCH_CSV_NOT_SUBMITTED'})
