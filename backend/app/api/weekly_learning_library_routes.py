"""Read-only exact weekly report recovery and download."""
from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import Response
from ..product_services import weekly_learning_library as library

router=APIRouter(prefix='/api/learning/weekly-library',tags=['weekly-learning-library'])

@router.get('')
def reports(entry_user:str=Query(min_length=1,max_length=200),season:int|None=None,week:int|None=Query(default=None,ge=1,le=25),latest_per_week:bool=True):
    try:return {'rows':library.list_reports(entry_user=entry_user,season=season,week=week,latest_per_week=latest_per_week),'rebuild_performed':False}
    except ValueError as exc:raise HTTPException(422,detail=str(exc)) from exc

@router.get('/{key}')
def report(key:str,entry_user:str=Query(min_length=1,max_length=200)):
    try:
        receipt,value,_=library.load_report(key,entry_user=entry_user)
        return {'record':receipt,'report':value,'rebuild_performed':False}
    except (OSError,ValueError,KeyError) as exc:raise HTTPException(404,detail='Saved weekly report unavailable for this username') from exc

@router.get('/{key}/download')
def download(key:str,entry_user:str=Query(min_length=1,max_length=200)):
    try:
        receipt,_,raw=library.load_report(key,entry_user=entry_user)
        return Response(raw,media_type='application/json',headers={'Content-Disposition':f'attachment; filename="week-learning-{receipt["season"]}-w{receipt["week"]}-{key[:12]}.json"','X-Report-Content-SHA256':key})
    except (OSError,ValueError,KeyError) as exc:raise HTTPException(404,detail='Saved weekly report unavailable for this username') from exc
