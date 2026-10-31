"""Background jobs (translation runs, structure reviews) with progress the frontend can poll."""

import asyncio
import time
import uuid

from pydantic import BaseModel


class Job(BaseModel):
    """A background job (structure review or translation) and its progress, as the client polls it."""

    id: str
    kind: str
    doc_id: str
    langs: list[str]
    status: str = "running"  # running | done | error
    total: int = 0
    done: int = 0
    failed: int = 0
    error: str | None = None
    phase: str | None = None  # "layout": a translation waiting for the document's structure review
    started: str
    finished: str | None = None


class JobManager:
    """Runs background jobs as asyncio tasks and keeps their records in memory."""

    def __init__(self):
        self.jobs = {}
        self._tasks = {}  # job id -> task, while it runs

    def start(self, kind, doc_id, langs, work):
        """`work(job)` is an async function that updates the job as it goes."""
        job = Job(
            id=uuid.uuid4().hex[:12],
            kind=kind,
            doc_id=doc_id,
            langs=langs,
            started=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )
        self.jobs[job.id] = job

        async def run():
            """Run the work, then mark the job done or record the error."""
            try:
                await work(job)
                job.status = "done"
                job.finished = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            except Exception as exc:  # surface any failure on the job instead of losing it
                job.status, job.error = "error", repr(exc)
                job.finished = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        task = asyncio.get_running_loop().create_task(run())
        self._tasks[job.id] = task
        task.add_done_callback(lambda _: self._tasks.pop(job.id, None))
        return job

    def running_for(self, doc_id, kind=None):
        """The document's running jobs, optionally only those of one kind."""
        return [
            j
            for j in self.jobs.values()
            if j.doc_id == doc_id and j.status == "running" and (kind is None or j.kind == kind)
        ]

    async def wait(self, doc_id, kind):
        """Until the document's running jobs of `kind` have finished (however they end)."""
        tasks = [self._tasks[j.id] for j in self.running_for(doc_id, kind) if j.id in self._tasks]
        await asyncio.gather(*tasks, return_exceptions=True)
