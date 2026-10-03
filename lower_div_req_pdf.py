import requests
from bs4 import BeautifulSoup
import psycopg2
import re

URL = "https://catalog.sdsu.edu/preview_program.php?catoid=11&poid=10725&returnto=991"

response = requests.get(URL, timeout=30)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")
page_text = soup.get_text(separator="\n")

# ------------------ Extract helpers ------------------

COURSE_RE = re.compile(r"\b([A-Z]{2,4})\s*(\d{3}[A-Z]?)\b")

def numeric_part(token: str) -> int:
    """'150L' -> 150, '254' -> 254"""
    m = re.match(r"(\d{3})", token)
    return int(m.group(1)) if m else 9999

def extract_courses(text: str, subjects: set[str], max_num_exclusive: int | None = None):
    out = []
    for line in text.splitlines():
        for subj, token in COURSE_RE.findall(line):
            if subj not in subjects:
                continue
            if max_num_exclusive is not None and numeric_part(token) >= max_num_exclusive:
                continue
            out.append(f"{subj} {token}")
    # dedupe, preserve order
    return list(dict.fromkeys(out))

# ------------------ Scrape courses ------------------

physics_courses = extract_courses(page_text, {"PHYS"})
cs_core = extract_courses(page_text, {"CS"}, max_num_exclusive=300)      
math_core = extract_courses(page_text, {"MATH"}, max_num_exclusive=300)  

print("Physics courses:")
for c in physics_courses:
    print(" -", c)

print("\nCS core:")
for c in cs_core:
    print(" -", c)

print("\nMATH core:")
for c in math_core:
    print(" -", c)

# ------------------ Insert in database ------------------

def upsert_group(cur, major, level, name, units):
    cur.execute(
        """
        INSERT INTO grad_req (major, req_level, req_name, req_units)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (major, req_level, req_name)
        DO UPDATE SET req_units = EXCLUDED.req_units
        RETURNING id
        """,
        (major, level, name, units),
    )
    return cur.fetchone()[0]

def insert_courses(cur, group_id, courses):
    for course in courses:
        cur.execute(
            """
            INSERT INTO grad_req_courses (group_id, course_code)
            VALUES (%s, %s)
            ON CONFLICT (group_id, course_code) DO NOTHING
            """,
            (group_id, course),
        )

conn = psycopg2.connect(
    dbname="sdsu_planner",
    user="shreyabharath",
    password="",
    host="localhost",
    port=5432
)
cur = conn.cursor()

# Physics group
phys_group_id = upsert_group(
    cur,
    major="CS",
    level="lower",
    name="Lower Division Science",
    units=8  
)
insert_courses(cur, phys_group_id, physics_courses)

# CS core group (separate)
cs_core_group_id = upsert_group(
    cur,
    major="CS",
    level="lower",
    name="Lower Division Core-CS",
    units=17  
)
insert_courses(cur, cs_core_group_id, cs_core)

# Math core group (separate)
math_core_group_id = upsert_group(
    cur,
    major="CS",
    level="lower",
    name="Lower Division Core-Math",
    units=14  
)
insert_courses(cur, math_core_group_id, math_core)

conn.commit()
cur.close()
conn.close()

print("\nInserted Phys + cs_core + math_core into Postgres ✅")
