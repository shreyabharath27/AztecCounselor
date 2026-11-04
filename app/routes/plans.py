"""
Plan generation endpoint.

POST /students/{student_id}/generate-plan

Flow:
  1. Load the student, their completed courses, and the graduation
     requirement groups for their major from Postgres.
  2. Build one prompt from all of that, plus any constraint the student typed
     (e.g. "I want to graduate in 3 years").
  3. Ask Amazon Nova Lite (Bedrock Converse API) for a semester-by-semester
     plan as JSON.
  4. Save the plan in the plans table (a new row every time, so history is kept).
  5. Return the plan.

Register it in app/main.py with:
    from app.routes.plans import router as plans_router
    app.include_router(plans_router)
"""

import os
import json
from typing import Optional

import boto3
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from psycopg2.extras import Json, RealDictCursor
from pydantic import BaseModel

from app.database import get_connection
from app.evaluation import evaluate_plan

load_dotenv()

MAX_REPAIR_ATTEMPTS = 2  # extra model calls allowed to fix problems the checker finds (0 turns repair off)

router = APIRouter()

AWS_REGION = os.getenv("AWS_REGION")
MODEL_ID = "amazon.nova-lite-v1:0"
START_TERM = "Spring 2027"  # first term the plan should cover; change as needed

bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_REGION)


class PlanRequest(BaseModel):
    constraints: Optional[str] = None  # e.g. "I want to graduate in 3 years"


def load_plan_inputs(student_id: int):
    """Pull everything the model needs out of Postgres."""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)  # rows come back as dicts keyed by column name
    try:
        # 1. The student
        cur.execute("SELECT major, year FROM students WHERE id = %s", (student_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Student not found")
        student = {"major": row["major"], "year": row["year"]}

        # 2. Their completed courses (joined to courses for names/credits)
        cur.execute(
            """
            SELECT c.course_code, co.course_name, co.credits, c.grade, c.semester_taken
            FROM completions c
            LEFT JOIN courses co ON co.course_code = c.course_code
            WHERE c.student_id = %s
            ORDER BY c.course_code
            """,
            (student_id,),
        )
        completed = [dict(r) for r in cur.fetchall()]
        # A transcript re-upload inserts duplicate rows, so keep one per course
        completed = list({c["course_code"]: c for c in completed}.values())

        # 3. Requirement groups for their major, with the courses in each group
        cur.execute(
            """
            SELECT r.id AS group_id, r.req_name, r.req_level, r.req_units, r.satisfaction_type,
                   gc.course_code, co.course_name, co.credits, co.prerequisites
            FROM grad_req r
            JOIN grad_req_courses gc ON gc.group_id = r.id
            LEFT JOIN courses co ON co.course_code = gc.course_code
            WHERE r.major = %s
            ORDER BY r.id, gc.course_code
            """,
            (student["major"],),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    # Light data prep: mark which group courses are already done and total the
    # units earned per group, so the model doesn't have to do the arithmetic.
    # Which courses to pick, and in what order, is still the model's decision.
    completed_codes = {c["course_code"] for c in completed}
    groups = {}
    for r in rows:
        g = groups.setdefault(
            r["group_id"],
            {
                "requirement": r["req_name"],
                "level": r["req_level"],
                "units_needed": r["req_units"],
                "rule": r["satisfaction_type"],
                "units_completed": 0,
                "courses": [],
            },
        )
        done = r["course_code"] in completed_codes
        if done and r["credits"]:
            g["units_completed"] += r["credits"]
        g["courses"].append(
            {
                "course_code": r["course_code"],
                "course_name": r["course_name"],
                "credits": r["credits"],
                "prerequisites": r["prerequisites"],
                "completed": done,
            }
        )

    return student, completed, list(groups.values())


def build_prompt(student: dict, completed: list, requirements: list, constraints: Optional[str]) -> str:
    data = {
        "student": student,
        "completed_courses": completed,
        "requirement_groups": requirements,
    }

    return f"""You are an academic advisor building a semester-by-semester degree plan for a college student.

Here is the student's data as JSON:

{json.dumps(data, indent=2, default=str)}

Rules:
1. The plan starts in {START_TERM}. Use only Fall and Spring terms, in order, until every requirement group is satisfied.
2. Never include a course the student has already completed.
3. A group with rule "Required" needs every course listed in it. A group with rule "Choose_Units" needs courses totaling at least "units_needed" units; "units_completed" is already earned, so pick only the remaining units from that group's list.
4. Schedule a course only after its prerequisites (given as text) are completed or scheduled in an earlier term.
5. Aim for 12 to 16 units per term.
6. The student's own constraint: {constraints or "None given"}. If it conflicts with the rules above, follow the rules and explain the conflict in "notes".

Return ONLY valid JSON with no markdown, in exactly this shape:
{{
  "semesters": [
    {{"term": "Spring 2027", "courses": [{{"course_code": "CS 210", "units": 3}}], "total_units": 3}}
  ],
  "notes": "short explanation of key choices or any conflicts"
}}
"""


def build_repair_prompt(original_prompt: str, previous_plan, issues: list) -> str:
    problems = "\n".join(f"- {i['message']}" for i in issues if i["severity"] == "error")
    return f"""{original_prompt}

You previously returned this plan:

{json.dumps(previous_plan, indent=2)}

An automatic checker found these problems with it:

{problems}

Return a corrected plan that fixes every problem and still follows all the rules above.
Return ONLY the full corrected JSON in the same shape, with no markdown."""


def call_bedrock_for_plan(prompt: str) -> dict:
    response = bedrock_client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": 4000, "temperature": 0.2},
    )
    raw = response["output"]["message"]["content"][0]["text"]

    # Strip markdown fences in case the model adds them anyway
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"Could not parse plan JSON from Bedrock:\n{raw}")
        raise HTTPException(status_code=502, detail="The model did not return valid JSON. Try again.")


def save_plan(student_id: int, constraints: Optional[str], plan: dict, evaluation: dict):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            """
            INSERT INTO plans (student_id, constraints_used, plan_data, evaluation)
            VALUES (%s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (student_id, Json({"constraints": constraints}), Json(plan), Json(evaluation)),
        )
        row = cur.fetchone()
        conn.commit()
        return row["id"], row["created_at"]
    finally:
        cur.close()
        conn.close()


@router.post("/students/{student_id}/generate-plan")
def generate_plan(student_id: int, body: Optional[PlanRequest] = None):
    constraints = body.constraints if body else None

    student, completed, requirements = load_plan_inputs(student_id)
    if not requirements:
        raise HTTPException(
            status_code=422,
            detail=f"No graduation requirements found for major '{student['major']}'.",
        )

    prompt = build_prompt(student, completed, requirements, constraints)
    completed_codes = {c["course_code"] for c in completed}

    # First draft from the model, then run the rule-based checker on it
    plan = call_bedrock_for_plan(prompt)
    evaluation = evaluate_plan(plan, completed_codes, requirements)
    attempts = 1

    # If the checker found errors, show the model its mistakes and ask for a fix.
    # Keep the repaired plan only if it has no more errors than the one before.
    while not evaluation["passed"] and attempts <= MAX_REPAIR_ATTEMPTS:
        try:
            candidate = call_bedrock_for_plan(build_repair_prompt(prompt, plan, evaluation["issues"]))
        except HTTPException:
            break  # the repair attempt came back as unusable JSON; keep the plan we have
        candidate_eval = evaluate_plan(candidate, completed_codes, requirements)
        attempts += 1
        if candidate_eval["error_count"] <= evaluation["error_count"]:
            plan, evaluation = candidate, candidate_eval

    evaluation["attempts"] = attempts
    plan_id, created_at = save_plan(student_id, constraints, plan, evaluation)

    return {"plan_id": plan_id, "created_at": created_at, "plan": plan, "evaluation": evaluation}