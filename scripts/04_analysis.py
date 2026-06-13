from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


COST_PER_1K = {
    "groq": {"prompt": 0.0, "completion": 0.0},
    "openai_gpt_4o_mini": {"prompt": 0.00015, "completion": 0.00060},
}


def money(tokens: pd.Series, rate_per_1k: float) -> pd.Series:
    return tokens.fillna(0) / 1000 * rate_per_1k


def load_results(db_path: Path) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                t.id AS ticket_id,
                t.true_category,
                t.true_priority,
                r.variant,
                COALESCE(r.provider, 'unknown') AS provider,
                COALESCE(r.model, 'unknown') AS model,
                r.pred_category,
                r.pred_priority,
                r.pred_sentiment,
                r.confidence,
                r.escalated,
                r.latency_ms,
                r.prompt_tokens,
                r.completion_tokens
            FROM triage_results r
            JOIN tickets t ON t.id = r.ticket_id
            """,
            conn,
        )


def summarize(df: pd.DataFrame, cost_profile: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rates = COST_PER_1K[cost_profile]
    df = df.copy()
    df["category_correct"] = df["pred_category"].str.casefold() == df["true_category"].str.casefold()
    df["priority_correct"] = df["pred_priority"].str.casefold() == df["true_priority"].fillna("").str.casefold()
    df["total_tokens"] = df["prompt_tokens"].fillna(0) + df["completion_tokens"].fillna(0)
    df["estimated_cost_usd"] = money(df["prompt_tokens"], rates["prompt"]) + money(df["completion_tokens"], rates["completion"])
    df["experiment"] = df["provider"] + ":" + df["model"] + ":" + df["variant"]

    summary = (
        df.groupby(["provider", "model", "variant"])
        .agg(
            tickets=("ticket_id", "count"),
            category_accuracy=("category_correct", "mean"),
            priority_accuracy=("priority_correct", "mean"),
            avg_confidence=("confidence", "mean"),
            escalation_rate=("escalated", "mean"),
            avg_latency_ms=("latency_ms", "mean"),
            avg_tokens=("total_tokens", "mean"),
            total_estimated_cost_usd=("estimated_cost_usd", "sum"),
        )
        .reset_index()
    )

    by_category = (
        df.groupby(["provider", "model", "true_category", "variant"])
        .agg(
            tickets=("ticket_id", "count"),
            category_accuracy=("category_correct", "mean"),
            avg_confidence=("confidence", "mean"),
        )
        .reset_index()
    )

    prediction_distribution = (
        df.groupby(["provider", "model", "variant", "pred_category"])
        .agg(tickets=("ticket_id", "count"))
        .reset_index()
        .sort_values(["provider", "model", "variant", "tickets"], ascending=[True, True, True, False])
    )

    confusion = (
        df.groupby(["provider", "model", "variant", "true_category", "pred_category"])
        .agg(tickets=("ticket_id", "count"))
        .reset_index()
        .sort_values(["provider", "model", "variant", "true_category", "tickets"], ascending=[True, True, True, True, False])
    )

    return summary, by_category, prediction_distribution, confusion


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_report(
    summary: pd.DataFrame,
    by_category: pd.DataFrame,
    prediction_distribution: pd.DataFrame,
    confusion: pd.DataFrame,
    output_path: Path,
    cost_profile: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    formatted = summary.copy()
    for col in ["category_accuracy", "priority_accuracy", "escalation_rate"]:
        formatted[col] = formatted[col].map(pct)
    formatted["avg_confidence"] = formatted["avg_confidence"].map(lambda value: f"{value:.2f}")
    formatted["avg_latency_ms"] = formatted["avg_latency_ms"].map(lambda value: f"{value:.0f}")
    formatted["avg_tokens"] = formatted["avg_tokens"].map(lambda value: f"{value:.0f}")
    formatted["total_estimated_cost_usd"] = formatted["total_estimated_cost_usd"].map(lambda value: f"${value:.4f}")

    category_formatted = by_category.copy()
    category_formatted["category_accuracy"] = category_formatted["category_accuracy"].map(pct)
    category_formatted["avg_confidence"] = category_formatted["avg_confidence"].map(lambda value: f"{value:.2f}")

    distribution_formatted = prediction_distribution.copy()
    distribution_totals = distribution_formatted.groupby(["provider", "model", "variant"])["tickets"].transform("sum")
    distribution_formatted["share"] = (distribution_formatted["tickets"] / distribution_totals).map(pct)

    confusion_formatted = confusion.copy()

    winner = "Not enough data"
    baseline_note = "Not enough data"
    paired = summary.pivot_table(index=["provider", "model"], columns="variant", values=["category_accuracy", "avg_tokens"])
    paired_complete = paired.dropna()
    if (
        ("category_accuracy", "zero_shot") in paired.columns
        and ("category_accuracy", "few_shot") in paired.columns
        and not paired_complete.empty
    ):
        first_provider, first_model = paired_complete.index[0]
        pair = paired_complete.loc[(first_provider, first_model)]
        zero_accuracy = pair[("category_accuracy", "zero_shot")]
        few_accuracy = pair[("category_accuracy", "few_shot")]
        zero_tokens = pair[("avg_tokens", "zero_shot")]
        few_tokens = pair[("avg_tokens", "few_shot")]
        delta = few_accuracy - zero_accuracy
        token_delta = few_tokens - zero_tokens
        winner = (
            f"For `{first_provider}:{first_model}`, few-shot changed category accuracy by "
            f"{delta * 100:.1f} percentage points and average token usage by "
            f"{token_delta:.0f} tokens per ticket versus zero-shot."
        )

    true_distribution = (
        confusion[["true_category", "tickets"]]
        .groupby("true_category")["tickets"]
        .sum()
        .sort_values(ascending=False)
    )
    if not true_distribution.empty:
        baseline_accuracy = true_distribution.iloc[0] / true_distribution.sum()
        baseline_note = (
            f"Majority-class baseline accuracy is {baseline_accuracy * 100:.1f}% "
            f"by always predicting `{true_distribution.index[0]}`."
        )

    report = f"""# SupportPilot Metrics Report

Generated from local SQLite results.

## Executive Summary

{winner}

{baseline_note}

Cost profile: `{cost_profile}`.

## Variant Metrics

{formatted.to_markdown(index=False)}

## Per-Category Accuracy

{category_formatted.to_markdown(index=False)}

## Prediction Distribution

{distribution_formatted.to_markdown(index=False)}

## Confusion Matrix Rows

{confusion_formatted.to_markdown(index=False)}

## Notes

- Category and priority accuracy are measured against the source dataset's human labels.
- Escalation rate is the share of tickets with model confidence below the configured threshold.
- Cost is estimated from recorded prompt and completion tokens; Groq development runs are treated as $0 in this report.
- The source descriptions contain substantial generic support-ticket boilerplate, so description-only classification can collapse toward broad issue categories.
"""
    output_path.write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SupportPilot A/B metrics report.")
    parser.add_argument("--db", default="db/supportpilot.db", help="Path to SQLite database.")
    parser.add_argument("--output", default="reports/metrics_report.md", help="Report output path.")
    parser.add_argument("--cost-profile", choices=sorted(COST_PER_1K), default="openai_gpt_4o_mini")
    args = parser.parse_args()

    df = load_results(Path(args.db))
    if df.empty:
        raise SystemExit("No triage_results found. Run scripts/03_run_experiment.py first.")

    summary, by_category, prediction_distribution, confusion = summarize(df, args.cost_profile)
    write_report(summary, by_category, prediction_distribution, confusion, Path(args.output), args.cost_profile)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
