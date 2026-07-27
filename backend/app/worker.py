"""Standalone durable queue worker.

Run with ``python -m backend.app.worker`` in a process separate from FastAPI.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import socket
import threading
from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import uuid4

from .db import SessionLocal, initialize_database
from .services.job_handlers import execute_job_handler
from .services.job_queue import (
    PermanentJobError,
    claim_next_job,
    complete_job,
    fail_job,
    heartbeat_job,
    update_job_progress,
)


LOGGER = logging.getLogger(__name__)
JobHandler = Callable[[str, "JobExecutionContext", dict[str, Any]], dict[str, Any]]


@dataclass
class JobExecutionContext:
    job_id: str
    worker_id: str
    run_id: str | None
    checkpoint: dict[str, Any] = field(default_factory=dict)
    lease_seconds: int = 300

    def progress(
        self,
        stage: str,
        current: int,
        total: int,
        message: str,
        *,
        run_id: str | None = None,
        checkpoint: dict[str, Any] | None = None,
    ) -> None:
        if run_id is not None:
            self.run_id = run_id
        if checkpoint is not None:
            self.checkpoint = dict(checkpoint)
        with SessionLocal() as session:
            updated = update_job_progress(
                session,
                job_id=self.job_id,
                worker_id=self.worker_id,
                stage=stage,
                current=current,
                total=total,
                message=message,
                lease_seconds=self.lease_seconds,
                run_id=run_id,
                checkpoint=checkpoint,
            )
        if not updated:
            raise RuntimeError("Operational job lease was lost while updating progress.")


def _heartbeat_loop(
    *,
    stop_event: threading.Event,
    job_id: str,
    worker_id: str,
    lease_seconds: int,
    heartbeat_seconds: float,
) -> None:
    while not stop_event.wait(heartbeat_seconds):
        try:
            with SessionLocal() as session:
                if not heartbeat_job(
                    session,
                    job_id=job_id,
                    worker_id=worker_id,
                    lease_seconds=lease_seconds,
                ):
                    return
        except Exception:  # noqa: BLE001
            LOGGER.exception("Unable to heartbeat operational job %s", job_id)


def execute_claimed_job(
    *,
    job_id: str,
    job_type: str,
    request_payload: dict[str, Any],
    worker_id: str,
    run_id: str | None,
    checkpoint: dict[str, Any] | None,
    lease_seconds: int,
    handler: JobHandler = execute_job_handler,
    heartbeat_seconds: float | None = None,
) -> None:
    context = JobExecutionContext(
        job_id=job_id,
        worker_id=worker_id,
        run_id=run_id,
        checkpoint=dict(checkpoint or {}),
        lease_seconds=lease_seconds,
    )
    stop_event = threading.Event()
    heartbeat_interval = heartbeat_seconds or max(1.0, lease_seconds / 3.0)
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        kwargs={
            "stop_event": stop_event,
            "job_id": job_id,
            "worker_id": worker_id,
            "lease_seconds": lease_seconds,
            "heartbeat_seconds": heartbeat_interval,
        },
        name=f"job-heartbeat-{job_id[:8]}",
        daemon=True,
    )
    heartbeat_thread.start()
    try:
        result = handler(job_type, context, request_payload)
        with SessionLocal() as session:
            if not complete_job(
                session,
                job_id=job_id,
                worker_id=worker_id,
                result_payload=result,
                run_id=context.run_id,
            ):
                LOGGER.warning("Completion ignored after lease loss for job %s", job_id)
    except PermanentJobError as exc:
        with SessionLocal() as session:
            fail_job(
                session,
                job_id=job_id,
                worker_id=worker_id,
                error_message=str(exc),
                permanent=True,
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("Operational job %s failed", job_id)
        with SessionLocal() as session:
            fail_job(
                session,
                job_id=job_id,
                worker_id=worker_id,
                error_message=str(exc),
            )
    finally:
        stop_event.set()
        heartbeat_thread.join(timeout=max(1.0, heartbeat_interval + 1.0))


def run_worker(
    *,
    worker_id: str,
    poll_seconds: float = 1.0,
    lease_seconds: int = 300,
    once: bool = False,
    stop_event: threading.Event | None = None,
) -> int:
    stop_event = stop_event or threading.Event()
    processed = 0
    while not stop_event.is_set():
        with SessionLocal() as session:
            job = claim_next_job(
                session,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )
            if job is None:
                if once:
                    return processed
            else:
                snapshot = {
                    "job_id": job.job_id,
                    "job_type": job.job_type,
                    "request_payload": dict(job.request_json),
                    "run_id": job.run_id,
                    "checkpoint": dict(job.checkpoint_json or {}),
                }
        if job is None:
            stop_event.wait(max(0.05, poll_seconds))
            continue
        execute_claimed_job(
            **snapshot,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        processed += 1
        if once:
            return processed
    return processed


def _worker_id() -> str:
    return (
        f"{socket.gethostname()}:{os.getpid()}:"
        f"{str(uuid4())[:8]}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the football_26 operational worker.")
    parser.add_argument("--worker-id", default=_worker_id())
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--lease-seconds", type=int, default=300)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    initialize_database()
    stop_event = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    LOGGER.info("Starting operational worker %s", args.worker_id)
    run_worker(
        worker_id=args.worker_id,
        poll_seconds=args.poll_seconds,
        lease_seconds=args.lease_seconds,
        once=args.once,
        stop_event=stop_event,
    )


if __name__ == "__main__":
    main()
