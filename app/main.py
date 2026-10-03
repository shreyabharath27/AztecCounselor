from fastapi import FastAPI, HTTPException

from app.database import get_connection

app = FastAPI()

from app.routes.transcript import router as transcript_router 
app.include_router(transcript_router)


@app.get("/")
def read_root():
    return {"message": "Aztec Counselor backend is running"}


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