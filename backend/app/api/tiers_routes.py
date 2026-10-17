"""Separate, append-only NFL Tiers research endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..db import get_db_session
from ..product_services import tiers

router=APIRouter(prefix='/api/tiers',tags=['tiers'])

@router.get('/records')
def records():return {'rows':tiers.catalog(),'warning':'Latest 100 immutable records.'}

@router.get('/projection-sources')
def sources(season:int=Query(ge=2000),week:int=Query(ge=1,le=25),session:Session=Depends(get_db_session)):
    return {'rows':tiers.projection_sources(session,season,week),'warning':'Existing frozen Sunday Main baselines only; no new projections are built.'}

@router.get('/records/{key}')
def record(key:str):
    try:
        value=tiers.load(key)
        return {**value,'current_readiness':tiers.readiness(value)} if value['kind']=='pool' else value
    except (ValueError,OSError,KeyError) as exc:raise HTTPException(status_code=404,detail='Tiers record unavailable') from exc

@router.post('/pools')
def import_pool(request:tiers.PoolImport,session:Session=Depends(get_db_session)):
    try:
        pool=tiers.import_pool(request,session)
        return {**pool,'current_readiness':tiers.readiness(pool)}
    except (ValueError,OSError,KeyError) as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc

@router.post('/optimize')
def optimize(request:tiers.Optimize):
    try:return tiers.optimize(request)
    except (ValueError,OSError,KeyError) as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc

from fastapi.responses import Response
from ..product_services import tiers_export

@router.post('/templates')
def template(request:tiers_export.TemplateImport):
    try:return tiers_export.import_template(request)
    except (ValueError,OSError,KeyError) as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc

@router.get('/records/{key}/export-readiness')
def export_readiness(key:str):
    try:return tiers_export.export_readiness(key)
    except (ValueError,OSError,KeyError) as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc

@router.get('/records/{key}/download')
def download(key:str,template_sha256:str|None=None,entry:int=Query(default=1,ge=1),accept_research:bool=False):
    try:
        name,data,receipt=tiers_export.build_download(key,template_sha256,entry=entry,accept_research=accept_research)
        return Response(data,media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="{name}"','X-Tiers-Export-Receipt':receipt['sha256']})
    except (ValueError,OSError,KeyError) as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc


@router.post('/pools/{key}/refresh-status')
def refresh_status(key:str,session:Session=Depends(get_db_session)):
    from ..product_services import tiers_status
    try:
        value=tiers_status.refresh_pool(key,session)
        return {**value,'current_readiness':tiers.readiness(value)}
    except (ValueError,OSError,KeyError) as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc
