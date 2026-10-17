"""The run API the dashboard calls in real mode (contract: dashboard/API_CONTRACT.md).

    python -m browseen serve            # http://127.0.0.1:8000

Runs execute in background threads; their events stream from runs/<run_id>/events.jsonl.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from browseen import program as P
from browseen.runtime.runner import RUNS_DIR, new_run_id, run_program, with_query

SSE_POLL_S = 0.3
SSE_MAX_S = 900


class RunRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)  # defaults to each param's recorded example
    mutations: list[str] = Field(default_factory=list)  # testbed mutation ids, e.g. ["M04"]
    seed: int | None = None
    headless: bool = True


def default_agent_run(program: P.Program, params: dict[str, Any], start_url: str, *, run_id: str,
                      runs_dir: Path, headless: bool) -> None:
    """The baseline: the Browser Use agent does the whole task (recorded like a first run)."""
    from browseen.recorder.record import record

    asyncio.run(record(program.task, start_url, params, name=program.program, headless=headless,
                       runs_dir=runs_dir, run_id=run_id))


def create_app(runs_dir: Path = RUNS_DIR, programs_dir: Path = P.PROGRAMS_DIR,
               runner: Callable[..., Any] = run_program, agent_runner: Callable[..., Any] = default_agent_run) -> FastAPI:
    runs_dir, programs_dir = Path(runs_dir), Path(programs_dir)
    app = FastAPI(title="Browseen run API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def latest_or_404(name: str) -> P.Program:
        try:
            return P.latest(name, programs_dir)
        except FileNotFoundError:
            raise HTTPException(404, f"no program named {name!r}")

    def params_for(program: P.Program, body: RunRequest, run_id: str) -> dict[str, Any]:
        params = {k: p.example for k, p in program.params.items() if p.example is not None}
        params.update(body.params)
        if "run_id" in program.params and "run_id" not in body.params:
            params["run_id"] = run_id  # a fresh testbed session for every run
        if missing := sorted(set(program.params) - set(params)):
            raise HTTPException(422, f"missing params: {missing}")
        return params

    def query_for(body: RunRequest) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if body.mutations:
            query["mut"] = ",".join(body.mutations)
        if body.seed is not None:
            query["seed"] = body.seed
        return query

    def in_background(target: Callable[..., Any], **kwargs: Any) -> None:
        threading.Thread(target=target, kwargs=kwargs, daemon=True).start()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/runs")
    def list_runs() -> list[dict[str, str]]:
        found = [d for d in runs_dir.glob("*/") if (d / "events.jsonl").exists()] if runs_dir.exists() else []
        found.sort(key=lambda d: (d / "events.jsonl").stat().st_mtime, reverse=True)
        return [{"run_id": d.name} for d in found]

    def events_path(run_id: str) -> Path:
        path = runs_dir / run_id / "events.jsonl"
        if "/" in run_id or ".." in run_id or not path.exists():
            raise HTTPException(404, f"no events for run {run_id!r}")
        return path

    @app.get("/runs/{run_id}/events.jsonl")
    def run_events_file(run_id: str) -> FileResponse:
        return FileResponse(events_path(run_id), media_type="application/x-ndjson")

    @app.get("/runs/{run_id}/events")
    def run_events_stream(run_id: str) -> StreamingResponse:
        if "/" in run_id or ".." in run_id:
            raise HTTPException(404, "bad run id")
        path = runs_dir / run_id / "events.jsonl"

        async def stream():
            offset, deadline = 0, time.monotonic() + SSE_MAX_S
            while time.monotonic() < deadline:
                if path.exists():
                    with path.open() as f:
                        f.seek(offset)
                        chunk = f.read()
                    complete, _, _ = chunk.rpartition("\n")  # never send a half-written line
                    if complete:
                        offset += len(complete.encode()) + 1
                        for line in complete.splitlines():
                            if line.strip():
                                yield f"data: {line}\n\n"
                                if '"type": "run_finished"' in line:
                                    return
                await asyncio.sleep(SSE_POLL_S)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/programs")
    def list_programs() -> list[str]:
        return sorted(d.name for d in programs_dir.glob("*/") if P.versions(d.name, programs_dir))

    @app.post("/programs/{name}/run")
    def start_run(name: str, body: RunRequest | None = None) -> dict[str, str]:
        body = body or RunRequest()
        program = latest_or_404(name)
        run_id = new_run_id()
        in_background(runner, program=program, params=params_for(program, body, run_id), headless=body.headless,
                      runs_dir=runs_dir, programs_dir=programs_dir, run_id=run_id, url_params=query_for(body),
                      verbose=False)
        return {"run_id": run_id}

    @app.post("/programs/{name}/run-agent")
    def start_agent_run(name: str, body: RunRequest | None = None) -> dict[str, str]:
        body = body or RunRequest()
        program = latest_or_404(name)
        run_id = "r_" + new_run_id()[2:]
        params = params_for(program, body, run_id)
        start_url = with_query(program.resolved(params).start_url, query_for(body))
        in_background(agent_runner, program=program, params=params, start_url=start_url, run_id=run_id,
                      runs_dir=runs_dir, headless=body.headless)
        return {"run_id": run_id}

    @app.get("/programs/{name}/versions")
    def program_versions(name: str) -> list[dict[str, Any]]:
        found = P.versions(name, programs_dir)
        if not found:
            raise HTTPException(404, f"no program named {name!r}")
        return [P.load(P.program_path(name, v, programs_dir)).model_dump(mode="json") for v in found]

    @app.post("/programs/{name}/rollback")
    def program_rollback(name: str, to: int = Query(...)) -> dict[str, Any]:
        try:
            return P.rollback(name, to, programs_dir).model_dump(mode="json")
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))
        except ValueError as e:
            raise HTTPException(409, str(e))

    return app
