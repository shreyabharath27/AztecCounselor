"""
Load courses data from a filled-in CSV into the `courses` table.

Before running:
  pip install psycopg2-binary python-dotenv --break-system-packages

Run:
    python scripts/load_courses_csv.py path/to/your_file.csv

Notes:
- Expects columns: course_code, course_name, course_descrip, credits,
  prerequisites, catelog_url
- If `credits` contains a range like "1-4", only the first number is used.
- Uses ON CONFLICT so re-running this after fixing a row just updates it.
- Requires a UNIQUE constraint on courses.course_code:
    ALTER TABLE courses ADD CONSTRAINT courses_course_code_unique UNIQUE (course_code);
"""

import os
import re
import sys
import csv
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": os.getenv("DB_PORT", 5432),
}


def parse_credits(raw: str) -> int:
    """Turn '3' or '1-4' into a single int (first number found)."""
    match = re.search(r"\d+", raw)
    return int(match.group()) if match else None


def load_csv(path: str) -> list[dict]:
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # normalize keys in case of stray whitespace (e.g. "prerequisites ")
            row = {k.strip(): v.strip() if v else v for k, v in row.items()}
            rows.append(row)
    return rows


def insert_courses(rows: list[dict]) -> None:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    inserted = 0
    for row in rows:
        if not row.get("course_code"):
            continue  # skip any blank rows

        cur.execute(
            """
            INSERT INTO courses (course_code, course_name, course_descrip, credits, prerequisites, catelog_url)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (course_code)
            DO UPDATE SET
                course_name = EXCLUDED.course_name,
                course_descrip = EXCLUDED.course_descrip,
                credits = EXCLUDED.credits,
                prerequisites = EXCLUDED.prerequisites,
                catelog_url = EXCLUDED.catelog_url
            """,
            (
                row["course_code"],
                row.get("course_name"),
                row.get("course_descrip"),
                parse_credits(row.get("credits", "")),
                row.get("prerequisites"),
                row.get("catelog_url"),
            ),
        )
        inserted += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Inserted/updated {inserted} courses.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/load_courses_csv.py path/to/your_file.csv")
        sys.exit(1)

    csv_path = sys.argv[1]
    rows = load_csv(csv_path)
    print(f"Loaded {len(rows)} rows from {csv_path}")
    insert_courses(rows)