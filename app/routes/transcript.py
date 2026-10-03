"""
Transcript upload endpoint.

Flow:
  1. Receive the PDF file from the frontend.
  2. Upload it to S3 (raw file, kept as a record).
  3. Extract text from the PDF locally (pdfplumber).
  4. Send that text to Bedrock to get structured JSON of completed courses.
     (Currently STUBBED — see call_bedrock_extract_courses() below —
     until AWS Bedrock access is configured.)
  5. Insert the structured course data into the completions table.
  6. Return a confirmation to the frontend.

Add this router to your main.py with:
    from app.routes.transcript import router as transcript_router
    app.include_router(transcript_router)
"""

import os
import io
import json
import boto3
import pdfplumber
import psycopg2
from fastapi import APIRouter, UploadFile, File, HTTPException
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# --- AWS / DB config, pulled from .env ---
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION")

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "port": os.getenv("DB_PORT", 5432),
}

s3_client = boto3.client("s3", region_name=AWS_REGION)


def upload_to_s3(file_bytes: bytes, student_id: int, filename: str) -> str:
    """Upload the raw PDF to S3 and return its S3 key (path)."""
    s3_key = f"transcripts/student_{student_id}/{filename}"
    s3_client.put_object(Bucket=S3_BUCKET_NAME, Key=s3_key, Body=file_bytes)
    return s3_key


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Pull raw text out of the PDF using pdfplumber."""
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


def call_bedrock_extract_courses(transcript_text: str) -> list[dict]:
    """
    Sends the extracted transcript text to Amazon Nova Lite via Bedrock's
    Converse API, asking it to return completed courses as JSON.
    """
    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

    prompt = f"""You will be given raw text extracted from a college transcript.
Extract every completed course as a JSON array. Each item must have exactly
these fields: course_code (e.g. "CS 150"), grade (e.g. "A", "B+"), and
semester_taken (e.g. "Fall 2024"). Only include courses with a final grade
(skip in-progress or withdrawn courses). Return ONLY the JSON array, no
other text, no markdown formatting.

Transcript text:
{transcript_text}
"""

    response = client.converse(
        modelId="amazon.nova-lite-v1:0",
        messages=[
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
    )

    raw_output = response["output"]["message"]["content"][0]["text"]

    # Strip accidental markdown code fences if the model adds them anyway
    cleaned = raw_output.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        courses = json.loads(cleaned)
    except json.JSONDecodeError:
        print(f"Could not parse Bedrock output as JSON:\n{raw_output}")
        return []

    return courses


def insert_completions(student_id: int, courses: list[dict]) -> int:
    """Insert extracted completions into the completions table."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    for course in courses:
        cur.execute(
            """
            INSERT INTO completions (student_id, course_code, grade, semester_taken)
            VALUES (%s, %s, %s, %s)
            """,
            (student_id, course["course_code"], course.get("grade"), course.get("semester_taken")),
        )

    conn.commit()
    cur.close()
    conn.close()
    return len(courses)


@router.post("/students/{student_id}/upload-transcript")
async def upload_transcript(student_id: int, file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    file_bytes = await file.read()

    # Step 1: store the raw file in S3
    s3_key = upload_to_s3(file_bytes, student_id, file.filename)

    # Step 2: extract text locally
    transcript_text = extract_text_from_pdf(file_bytes)
    if not transcript_text.strip():
        raise HTTPException(status_code=422, detail="Could not extract any text from this PDF.")

    # Step 3: send to Bedrock (stubbed for now)
    extracted_courses = call_bedrock_extract_courses(transcript_text)

    # Step 4: save to Postgres
    num_inserted = insert_completions(student_id, extracted_courses)

    # Step 5: respond
    return {
        "status": "success",
        "s3_key": s3_key,
        "courses_added": num_inserted,
        "courses": extracted_courses,
    }