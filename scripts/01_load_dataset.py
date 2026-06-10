from __future__ import annotations

# DATA LAYER — swap this file only when changing data source.
# All downstream code reads from the tickets table exclusively.
#
# This is the only project file that should know raw source column names,
# source-file assumptions, cleaning logic, and sampling strategy.

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


DESCRIPTION_COL = "Ticket Description"
PRODUCT_COL = "Product Purchased"
CATEGORY_COL = "Ticket Type"
PRIORITY_COL = "Ticket Priority"
SOURCE_COL = "Ticket Channel"
PLACEHOLDER = "{product_purchased}"

REQUIRED_COLUMNS = [
    DESCRIPTION_COL,
    PRODUCT_COL,
    CATEGORY_COL,
    PRIORITY_COL,
    SOURCE_COL,
]


def validate_columns(df: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(
            "Missing required Kaggle columns: "
            + ", ".join(missing)
            + ". Available columns: "
            + ", ".join(str(column) for column in df.columns)
        )


def clean_ticket_text(df: pd.DataFrame) -> pd.Series:
    descriptions = df[DESCRIPTION_COL].astype(str)
    products = df[PRODUCT_COL].fillna("").astype(str)

    cleaned = pd.Series(
        [
            description.replace(PLACEHOLDER, product).strip()
            for description, product in zip(descriptions, products, strict=True)
        ],
        index=df.index,
    )

    remaining_placeholders = cleaned.str.contains(PLACEHOLDER, regex=False, na=False).sum()
    assert remaining_placeholders == 0, f"{remaining_placeholders} cleaned tickets still contain {PLACEHOLDER}"
    return cleaned


def stratified_sample(df: pd.DataFrame, sample_size: int, seed: int) -> pd.DataFrame:
    if sample_size <= 0:
        return df.sample(frac=1, random_state=seed).reset_index(drop=True)

    categories = sorted(df["true_category"].unique())
    if sample_size % len(categories) != 0:
        raise ValueError(
            f"Sample size {sample_size} must divide evenly across {len(categories)} categories "
            "for this experiment."
        )

    per_category = sample_size // len(categories)
    sampled_groups = []
    for category in categories:
        group = df[df["true_category"] == category]
        if len(group) < per_category:
            raise ValueError(
                f"Category '{category}' has only {len(group)} rows; need {per_category} for stratified sampling."
            )
        sampled_groups.append(group.sample(n=per_category, random_state=seed))

    sample = pd.concat(sampled_groups, ignore_index=True)
    return sample.sample(frac=1, random_state=seed).reset_index(drop=True)


def load_dataset(
    csv_path: Path,
    db_path: Path,
    sample_size: int,
    seed: int,
    replace: bool,
) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    validate_columns(df)

    clean = pd.DataFrame(
        {
            "text": clean_ticket_text(df),
            "true_category": df[CATEGORY_COL].astype(str).str.strip(),
            "true_priority": df[PRIORITY_COL].astype(str).str.strip(),
            "source": df[SOURCE_COL].astype(str).str.strip(),
        }
    )
    clean = clean[(clean["text"] != "") & (clean["true_category"] != "")]
    clean = clean.drop_duplicates(subset=["text", "true_category", "true_priority", "source"])

    sample = stratified_sample(clean, sample_size=sample_size, seed=seed)
    assert len(sample) == sample_size, f"Expected {sample_size} sampled tickets, got {len(sample)}"
    assert not sample["text"].str.contains(PLACEHOLDER, regex=False, na=False).any()

    Path("data").mkdir(exist_ok=True)
    sample.to_csv("data/sample_200.csv", index=False)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        if replace:
            conn.execute("DELETE FROM triage_results")
            conn.execute("DELETE FROM tickets")

        rows = sample[["text", "true_category", "true_priority", "source"]].itertuples(index=False, name=None)
        conn.executemany(
            """
            INSERT INTO tickets (text, true_category, true_priority, source, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            rows,
        )

    return sample


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean and load the suraj520 Kaggle customer support ticket dataset into SQLite."
    )
    parser.add_argument("--csv", default="data/raw_tickets.csv", help="Path to customer_support_tickets.csv.")
    parser.add_argument("--db", default="db/supportpilot.db", help="Path to SQLite database.")
    parser.add_argument("--sample-size", type=int, default=200, help="Exact stratified sample size.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible sampling.")
    parser.add_argument("--append", action="store_true", help="Append instead of replacing existing tickets/results.")
    args = parser.parse_args()

    sample = load_dataset(
        csv_path=Path(args.csv),
        db_path=Path(args.db),
        sample_size=args.sample_size,
        seed=args.seed,
        replace=not args.append,
    )

    print(f"Loaded {len(sample)} tickets into {args.db}")
    print("Sanity check: total count + count per true_category")
    print(f"total: {len(sample)}")
    print(sample["true_category"].value_counts().sort_index().to_string())


if __name__ == "__main__":
    main()
