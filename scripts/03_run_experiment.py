from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


VARIANTS = {
    "zero_shot": Path("prompts/zero_shot.txt"),
    "few_shot": Path("prompts/few_shot.txt"),
}


def provider_config(provider: str) -> tuple[str, str, str]:
    provider = provider.lower()
    if provider == "groq":
        return (
            os.environ["GROQ_API_KEY"],
            os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
            os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        )
    if provider == "openai":
        return (
            os.environ["OPENAI_API_KEY"],
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        )
    raise ValueError("Provider must be 'groq' or 'openai'.")


def render_prompt(template_path: Path, ticket_text: str) -> str:
    return template_path.read_text(encoding="utf-8").replace("{{ticket_text}}", ticket_text)


def parse_json_response(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        content = content.removeprefix("json").strip()
    return json.loads(content)


def call_llm(
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    timeout: int,
    max_retries: int,
) -> tuple[dict[str, Any], dict[str, int], int]:
    started = time.perf_counter()
    last_response: requests.Response | None = None

    for attempt in range(max_retries + 1):
        response = requests.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
            timeout=timeout,
        )
        last_response = response

        if response.status_code != 429:
            break

        retry_after = response.headers.get("Retry-After")
        wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else min(60, 2 ** attempt)
        print(f"Rate limited by provider; retrying in {wait_seconds}s ({attempt + 1}/{max_retries})")
        time.sleep(wait_seconds)

    latency_ms = round((time.perf_counter() - started) * 1000)
    assert last_response is not None
    last_response.raise_for_status()
    payload = last_response.json()
    usage = payload.get("usage", {})
    result = parse_json_response(payload["choices"][0]["message"]["content"])
    return result, usage, latency_ms


def pending_tickets(conn: sqlite3.Connection, variant: str, limit: int | None) -> list[sqlite3.Row]:
    query = """
        SELECT t.id, t.text
        FROM tickets t
        WHERE NOT EXISTS (
            SELECT 1 FROM triage_results r
            WHERE r.ticket_id = t.id AND r.variant = ?
        )
        ORDER BY t.id
    """
    if limit:
        query += " LIMIT ?"
        return conn.execute(query, (variant, limit)).fetchall()
    return conn.execute(query, (variant,)).fetchall()


def insert_result(
    conn: sqlite3.Connection,
    ticket_id: int,
    variant: str,
    result: dict[str, Any],
    usage: dict[str, int],
    latency_ms: int,
    threshold: float,
) -> None:
    confidence = float(result.get("confidence", 0) or 0)
    conn.execute(
        """
        INSERT INTO triage_results (
            ticket_id, variant, pred_category, pred_priority, pred_sentiment,
            draft_response, confidence, escalated, latency_ms,
            prompt_tokens, completion_tokens
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticket_id,
            variant,
            result.get("category"),
            result.get("priority"),
            result.get("sentiment"),
            result.get("draft_response"),
            confidence,
            1 if confidence < threshold else 0,
            latency_ms,
            usage.get("prompt_tokens", 0),
            usage.get("completion_tokens", 0),
        ),
    )


def mark_processed_when_done(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        UPDATE tickets
        SET status = 'processed'
        WHERE id IN (
            SELECT ticket_id
            FROM triage_results
            GROUP BY ticket_id
            HAVING COUNT(DISTINCT variant) = 2
        )
        """
    )


def run_variant(args: argparse.Namespace, variant: str) -> None:
    api_key, base_url, model = provider_config(args.provider)
    prompt_path = VARIANTS[variant]
    threshold = float(os.getenv("CONFIDENCE_THRESHOLD", args.confidence_threshold))

    with sqlite3.connect(args.db) as conn:
        conn.row_factory = sqlite3.Row
        tickets = pending_tickets(conn, variant, args.limit)
        print(f"Running {variant} on {len(tickets)} tickets with {args.provider}:{model}")
        for index, ticket in enumerate(tickets, start=1):
            prompt = render_prompt(prompt_path, ticket["text"])
            result, usage, latency_ms = call_llm(api_key, base_url, model, prompt, args.timeout, args.max_retries)
            insert_result(conn, ticket["id"], variant, result, usage, latency_ms, threshold)
            conn.commit()
            print(f"[{index}/{len(tickets)}] ticket={ticket['id']} category={result.get('category')} confidence={result.get('confidence')}")
        mark_processed_when_done(conn)
        conn.commit()


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run SupportPilot prompt variants through an OpenAI-compatible API.")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "db/supportpilot.db"), help="Path to SQLite database.")
    parser.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "groq"), choices=["groq", "openai"])
    parser.add_argument("--variant", choices=["zero_shot", "few_shot", "both"], default="both")
    parser.add_argument("--limit", type=int, help="Limit tickets per variant for smoke tests.")
    parser.add_argument("--timeout", type=int, default=60, help="HTTP timeout in seconds.")
    parser.add_argument("--max-retries", type=int, default=4, help="Retries for rate-limited API calls.")
    parser.add_argument("--confidence-threshold", type=float, default=0.70)
    args = parser.parse_args()

    variants = ["zero_shot", "few_shot"] if args.variant == "both" else [args.variant]
    for variant in variants:
        run_variant(args, variant)


if __name__ == "__main__":
    main()
