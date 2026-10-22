"""Fresh, source-authenticated inputs for the opt-in primary forecast consumer."""
from datetime import UTC, datetime
from sqlalchemy import select, text,func
from sqlalchemy.orm import Session
from ..models import SourceSnapshot
from ..services.source_capture import SourceCaptureService, verify_snapshot_artifact
from .opportunity_source_capture import capture_opportunity_source, derive_opportunity_event_evidence
from .slate_preparation import SlatePreparationRequest, slate_games, require_prelock


def ensure_source(engine, *, season, week, slate):
    with Session(engine) as session:
        games=slate_games(session,SlatePreparationRequest(season=season,week=week,slate=slate,action='rebuild'))
        lock=require_prelock(games)
        snapshot=session.scalars(select(SourceSnapshot).where(SourceSnapshot.dataset=='play_by_play',
            SourceSnapshot.source_system=='nflreadpy',SourceSnapshot.season==season,
            SourceSnapshot.week==week,func.lower(SourceSnapshot.slate)==slate.lower()).order_by(SourceSnapshot.captured_at.desc())).first()
        if snapshot is None:
            capture=capture_opportunity_source(SourceCaptureService(session),season=season,week=week,slate=slate,slate_lock_at=lock)
            snapshot=capture.snapshot
        verify_snapshot_artifact(snapshot)
        snapshot_id=str(snapshot.snapshot_id)
        session.commit()
        return snapshot_id


def source_inputs(engine, *, season, week, slate, cutoff):
    with Session(engine) as session:
        snapshot=session.scalars(select(SourceSnapshot).where(SourceSnapshot.dataset=='play_by_play',
            SourceSnapshot.source_system=='nflreadpy',SourceSnapshot.season==season,
            SourceSnapshot.week==week,func.lower(SourceSnapshot.slate)==slate.lower(),SourceSnapshot.captured_at<=cutoff)
            .order_by(SourceSnapshot.captured_at.desc())).first()
        if snapshot is None:raise ValueError('Primary models require a fresh scoped PBP source; Prepare again')
        aliases=session.execute(text("SELECT source_key,player_master_id FROM player_alias WHERE source_system IN ('nflreadpy','nflverse')")).all()
        ids={}
        for native,pid in aliases:
            if native in ids and ids[native]!=str(pid):raise ValueError('Conflicting native player alias')
            ids[native]=str(pid)
        receipt=derive_opportunity_event_evidence(snapshot,canonical_ids=ids,before_period=season*100+week,cutoff=cutoff)
        return receipt,dict(snapshot_id=str(snapshot.snapshot_id),sha256=snapshot.content_sha256,
            artifact_path=snapshot.artifact_path,received_at=str(snapshot.captured_at),lock_at=str(snapshot.slate_lock_at))
