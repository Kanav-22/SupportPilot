from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


TEXT_CANDIDATES = [
    "text",
    "ticket_text",
    "description",
    "ticket_description",
    "customer_query",
    "customer_message",
    "message",
]
CATEGORY_CANDIDATES = [
    "true_category",
    "category",
    "ticket_type",
    "type",
    "issue_type",
]
PRIORITY_CANDIDATES = [
    "true_priority",
    "priority",
    "ticket_priority",
    "severity",
]
SOURCE_CANDIDATES = [
    "source",
    "channel",
    "ticket_channel",
]


def pick_column(df: pd.DataFrame, candidates: list[str], explicit: str | None, required: bool) -> str | None:
    if explicit:
        if explicit not in df.columns:
            raise ValueError(f"Column '{explicit}' was requested but is not present in the CSV.")
        return explicit

    normalized = {col.lower().strip().replace(" ", "_"): col for col in df.columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]

    if required:
        raise ValueError(
            "Could not infer a required column. Available columns: "
            + ", ".join(str(col) for col in df.columns)
        )
    return None


def load_dataset(
    csv_path: Path,
    db_path: Path,
    sample_size: int,
    seed: int,
    text_col: str | None,
    category_col: str | None,
    priority_col: str | None,
    source_col: str | None,
    replace: bool,
) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    chosen_text = pick_column(df, TEXT_CANDIDATES, text_col, required=True)
    chosen_category = pick_column(df, CATEGORY_CANDIDATES, category_col, required=True)
    chosen_priority = pick_column(df, PRIORITY_CANDIDATES, priority_col, required=False)
    chosen_source = pick_column(df, SOURCE_CANDIDATES, source_col, required=False)

    clean = pd.DataFrame(
        {
            "text": df[chosen_text].astype(str).str.strip(),
            "true_category": df[chosen_category].astype(str).str.strip(),
            "true_priority": df[chosen_priority].astype(str).str.strip() if chosen_priority else None,
            "source": df[chosen_source].astype(str).str.strip() if chosen_source else None,
        }
    )
    clean = clean[(clean["text"] != "") & (clean["true_category"] != "")]
    clean = clean.drop_duplicates(subset=["text", "true_category"])

    if sample_size > 0 and len(clean) > sample_size:
        clean = clean.groupby("true_category", group_keys=False).apply(
            lambda group: group.sample(
                n=max(1, round(sample_size * len(group) / len(clean))),
                random_state=seed,
            )
        )
        if len(clean) > sample_size:
            clean = clean.sample(n=sample_size, random_state=seed)
        elif len(clean) < sample_size:
            remaining = df.index.difference(clean.index)
            top_up = (
                pd.DataFrame(
                    {
                        "text": df.loc[remaining, chosen_text].astype(str).str.strip(),
                        "true_category": df.loc[remaining, chosen_category].astype(str).str.strip(),
                        "true_priority": df.loc[remaining, chosen_priority].astype(str).str.strip()
                        if chosen_priority
                        else None,
                        "source": df.loc[remaining, chosen_source].astype(str).str.strip() if chosen_source else None,
                    }
                )
                .drop_duplicates(subset=["text", "true_category"])
                .head(sample_size - len(clean))
            )
            clean = pd.concat([clean, top_up], ignore_index=True)

    clean = clean.reset_index(drop=True)
    Path("data").mkdir(exist_ok=True)
    clean.to_csv("data/sample_200.csv", index=False)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        if replace:
            conn.execute("DELETE FROM triage_results")
            conn.execute("DELETE FROM tickets")
        rows = clean[["text", "true_category", "true_priority", "source"]].itertuples(index=False, name=None)
        conn.executemany(
            """
            INSERT INTO tickets (text, true_category, true_priority, source, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            rows,
        )

    return clean


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a labeled support-ticket CSV into SQLite.")
    parser.add_argument("--csv", default="data/raw_tickets.csv", help="Path to the raw ticket CSV.")
    parser.add_argument("--db", default="db/supportpilot.db", help="Path to SQLite database.")
    parser.add_argument("--sample-size", type=int, default=200, help="Number of tickets to sample. Use 0 for all.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible sampling.")
    parser.add_argument("--text-col", help="CSV column containing ticket text.")
    parser.add_argument("--category-col", help="CSV column containing ground-truth category.")
    parser.add_argument("--priority-col", help="CSV column containing ground-truth priority.")
    parser.add_argument("--source-col", help="CSV column containing source/channel.")
    parser.add_argument("--append", action="store_true", help="Append instead of replacing existing tickets/results.")
    args = parser.parse_args()

    sample = load_dataset(
        csv_path=Path(args.csv),
        db_path=Path(args.db),
        sample_size=args.sample_size,
        seed=args.seed,
        text_col=args.text_col,
        category_col=args.category_col,
        priority_col=args.priority_col,
        source_col=args.source_col,
        replace=not args.append,
    )
    print(f"Loaded {len(sample)} tickets into {args.db}")
    print(sample["true_category"].value_counts().to_string())


if __name__ == "__main__":
    main()
