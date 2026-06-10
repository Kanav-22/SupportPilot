# SupportPilot

AI-powered support ticket triage pipeline for classifying tickets, assigning priority, drafting first replies, and measuring zero-shot versus few-shot prompts against human-labeled ground truth.

## What It Builds

SupportPilot ingests a labeled support-ticket CSV into SQLite, runs two prompt variants through an OpenAI-compatible chat completion API, stores structured triage results, and generates a reproducible metrics report.

The n8n workflow is included as the automation showcase. The Python runner is the reliable local path for development and final metrics.

## Architecture

```text
Labeled CSV -> scripts/01_load_dataset.py -> SQLite tickets
SQLite tickets -> n8n or scripts/03_run_experiment.py -> LLM API
LLM JSON -> SQLite triage_results -> scripts/04_analysis.py -> reports/metrics_report.md
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Fill in `.env` with either Groq for development or OpenAI for the final measured run.

## Data

Place the raw Kaggle CSV at:

```text
data/raw_tickets.csv
```

Then create the database and load a balanced-ish sample:

```powershell
python scripts/02_setup_db.py
python scripts/01_load_dataset.py --csv data/raw_tickets.csv --sample-size 200
```

If the dataset column names differ, pass them explicitly:

```powershell
python scripts/01_load_dataset.py --text-col "Ticket Description" --category-col "Ticket Type" --priority-col "Ticket Priority"
```

## Run The Experiment

Smoke test one variant on five tickets:

```powershell
python scripts/03_run_experiment.py --provider groq --variant zero_shot --limit 5
```

Run both variants over remaining tickets:

```powershell
python scripts/03_run_experiment.py --provider groq --variant both
```

For the final resume-backed run, switch to OpenAI:

```powershell
python scripts/03_run_experiment.py --provider openai --variant both
```

## Generate Metrics

```powershell
python scripts/04_analysis.py --cost-profile openai_gpt_4o_mini
```

The report is written to:

```text
reports/metrics_report.md
```

## n8n

Start the local HTTP bridge:

```powershell
python scripts/05_api_server.py
```

Import `n8n/workflow.json` into n8n. The starter workflow triggers every 30 seconds and calls:

```text
http://host.docker.internal:8000/triage/batch
```

This bridge avoids SQLite file-sharing issues between Docker and Windows by keeping database writes on the host machine.

## Guardrails

- Do not put API keys in git.
- Do not use resume metrics until they appear in `reports/metrics_report.md`.
- Treat Groq as the free development provider and OpenAI as the final literal API run.
