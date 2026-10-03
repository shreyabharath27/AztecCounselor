import requests
import psycopg2
from bs4 import BeautifulSoup
import re


URL = "https://catalog.sdsu.edu/preview_program.php?catoid=11&poid=10725&returnto=991"

response = requests.get(URL, timeout=30)
response.raise_for_status()
html = response.text

soup = BeautifulSoup(html, "html.parser")

# ------------------ Extract helpers ------------------

CS_RE = re.compile(r"\bCS\s*(\d{3}[A-Z]?)\b", re.I)

def normalize_course(code: str) -> str:
    return " ".join(code.replace("\xa0", " ").split()).upper()

def extract_cs_courses(text: str, subjects: set[str], min_num_inclusive: int |None = None):
    out = []
    for line in text.splitlines():
        for num in CS_RE.findall(line):
            course_num = int(re.match(r"\d{3}", num).group())

            if min_num_inclusive is not None and course_num < min_num_inclusive:
                continue
            out.append(normalize_course(f"CS {num}"))
    return list(dict.fromkeys(out))

# ------------------ Split core vs electives ------------------

elective_anchor = soup.find(id=re.compile(r"electivecourses", re.I))
if elective_anchor:
    elective_block = elective_anchor.find_parent("div")  # contains the elective section header + text
    elective_text = elective_block.get_text("\n", strip=True)

    full_text = soup.get_text("\n", strip=True)

    # core text = everything before the elective section text appears
    core_text = full_text.split(elective_text, 1)[0]
else:
    core_text = soup.get_text("\n", strip=True)
    elective_text = ""

core_upper_div = extract_cs_courses(core_text, {"CS", "STAT"}, min_num_inclusive=300)
electives_upper_div = extract_cs_courses(elective_text, {"CS"}, min_num_inclusive=300)

print("Upper Div CORE CS courses:")
for c in core_upper_div:
    print(" -", c)

print("\nUpper Div ELECTIVE CS courses:")
for c in electives_upper_div:
    print(" -", c)

# ------------------ DB upsert/insert ------------------

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

def insert_courses(cur, group_id, courses: list[str]):
    for course in courses:
        course = normalize_course(course)
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

core_upper_div_group_id = upsert_group(
    cur, major="CS", level="upper", name="Upper Division Core", units=18
)
insert_courses(cur, core_upper_div_group_id, core_upper_div)

electives_upper_div_group_id = upsert_group(
    cur, major="CS", level="upper", name="Upper Division Electives", units=18
)
insert_courses(cur, electives_upper_div_group_id, electives_upper_div)

conn.commit()
cur.close()
conn.close()

print("\nInserted Upper Div Core and Electives into Postgres ✅")
