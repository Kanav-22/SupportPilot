from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field


def load_runner():
    runner_path = Path(__file__).with_name("03_run_experiment.py")
    spec = importlib.util.spec_from_file_location("supportpilot_runner", runner_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load runner from {runner_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load_runner()
app = FastAPI(title="SupportPilot Local Triage API")


class BatchRequest(BaseModel):
    variant: Literal["zero_shot", "few_shot", "both"] = "zero_shot"
    limit: int | None = Field(default=5, ge=1)
    provider: Literal["groq", "openai"] | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/triage/batch")
def triage_batch(request: BatchRequest) -> dict[str, object]:
    load_dotenv()
    provider = request.provider or os.getenv("LLM_PROVIDER", "groq")
    args = SimpleNamespace(
        db=os.getenv("DB_PATH", "db/supportpilot.db"),
        provider=provider,
        limit=request.limit,
        timeout=60,
        confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.70")),
    )

    variants = ["zero_shot", "few_shot"] if request.variant == "both" else [request.variant]
    for variant in variants:
        runner.run_variant(args, variant)

    return {"status": "ok", "provider": provider, "variants": variants, "limit": request.limit}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local SupportPilot HTTP API for n8n.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run("05_api_server:app", host=args.host, port=args.port, reload=False, app_dir=str(Path(__file__).parent))


if __name__ == "__main__":
    main()
