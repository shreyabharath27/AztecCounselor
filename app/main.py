import os

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

from app.database import get_connection

app = FastAPI()

# Browsers block requests between the Next.js development server (port 3000)
# and FastAPI (port 8000) unless the API explicitly allows that origin.
frontend_origins = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in frontend_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routes.transcript import router as transcript_router 
app.include_router(transcript_router)

from app.routes.plans import router as plans_router
app.include_router(plans_router)


class StudentCreate(BaseModel):
    major: str = Field(min_length=1, max_length=20)
    year: int = Field(ge=1, le=8)


@app.get("/")
def read_root():
    return {"message": "Aztec Counselor backend is running"}


@app.post("/students", status_code=status.HTTP_201_CREATED)
def create_student(student: StudentCreate):
    """Create a student record that transcript and plan routes can reference."""
    major = student.major.strip().upper()
    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute(
            """
            SELECT 1
            FROM grad_req
            WHERE major = %s
            LIMIT 1
            """,
            (major,),
        )
        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=422,
                detail=f"No graduation requirements found for major '{major}'.",
            )

        cursor.execute(
            """
            INSERT INTO students (major, year)
            VALUES (%s, %s)
            RETURNING id, major, year
            """,
            (major, student.year),
        )
        created_student = cursor.fetchone()
        connection.commit()
        return created_student
    except HTTPException:
        connection.rollback()
        raise
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


@app.get("/students/{student_id}/plans/latest")
def get_latest_plan(student_id: int):
    """Return the newest saved plan without generating another Bedrock response."""
    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    try:
        cursor.execute("SELECT 1 FROM students WHERE id = %s", (student_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Student not found")

        cursor.execute(
            """
            SELECT id AS plan_id, student_id, constraints_used,
                   plan_data AS plan, evaluation, created_at
            FROM plans
            WHERE student_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (student_id,),
        )
        plan = cursor.fetchone()
        if plan is None:
            raise HTTPException(
                status_code=404,
                detail="No saved plan found for this student",
            )
        return plan
    finally:
        cursor.close()
        connection.close()


@app.get("/courses")
def get_courses():
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT course_code, course_name, course_descrip,
                   credits, prerequisites, catalog_url
            FROM courses
            ORDER BY course_code
            """
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        connection.close()


@app.get("/courses/{course_code}")
def get_course(course_code: str):
    formatted_code = course_code.replace("-", " ").upper()

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT course_code, course_name, course_descrip,
                   credits, prerequisites, catalog_url
            FROM courses
            WHERE course_code = %s
            """,
            (formatted_code,)
        )

        course = cursor.fetchone()

        if course is None:
            raise HTTPException(status_code=404, detail="Course not found")

        return course
    finally:
        cursor.close()
        connection.close()
