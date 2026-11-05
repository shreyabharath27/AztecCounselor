"use client";

import { ChangeEvent, FormEvent, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

type Course = {
  course_code: string;
  units: number;
};

type Semester = {
  term: string;
  courses: Course[];
  total_units: number;
};

type Issue = {
  severity: "error" | "warning";
  type: string;
  course?: string | null;
  term?: string | null;
  message: string;
};

type PlanResponse = {
  plan_id: number;
  student_id?: number;
  created_at: string;
  plan: {
    semesters: Semester[];
    notes?: string;
  };
  evaluation: {
    passed: boolean;
    error_count: number;
    warning_count: number;
    attempts?: number;
    issues: Issue[];
  };
};

async function readResponse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = body?.detail ?? "Something went wrong. Please try again.";
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return body as T;
}

export default function Home() {
  const [studentId, setStudentId] = useState("");
  const [major, setMajor] = useState("CS");
  const [year, setYear] = useState("3");
  const [file, setFile] = useState<File | null>(null);
  const [constraints, setConstraints] = useState("");
  const [uploadMessage, setUploadMessage] = useState("");
  const [planResponse, setPlanResponse] = useState<PlanResponse | null>(null);
  const [error, setError] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const requireStudentId = () => {
    const id = Number(studentId);
    if (!Number.isInteger(id) || id <= 0) {
      throw new Error("Enter a valid student ID first.");
    }
    return id;
  };

  const runAction = async (name: string, action: () => Promise<void>) => {
    setError("");
    setBusyAction(name);
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong.");
    } finally {
      setBusyAction(null);
    }
  };

  const createStudent = (event: FormEvent) => {
    event.preventDefault();
    runAction("student", async () => {
      const response = await fetch(`${API_URL}/students`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ major, year: Number(year) }),
      });
      const student = await readResponse<{ id: number; major: string; year: number }>(response);
      setStudentId(String(student.id));
      setUploadMessage(`Student profile #${student.id} created.`);
    });
  };

  const selectFile = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] ?? null);
    setUploadMessage("");
  };

  const uploadTranscript = () => {
    runAction("upload", async () => {
      const id = requireStudentId();
      if (!file) throw new Error("Choose a PDF transcript first.");

      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`${API_URL}/students/${id}/upload-transcript`, {
        method: "POST",
        body: formData,
      });
      const result = await readResponse<{ courses_saved: number }>(response);
      setUploadMessage(`${result.courses_saved} completed courses were saved.`);
    });
  };

  const generatePlan = () => {
    runAction("generate", async () => {
      const id = requireStudentId();
      const response = await fetch(`${API_URL}/students/${id}/generate-plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ constraints: constraints.trim() || null }),
      });
      const result = await readResponse<PlanResponse>(response);
      setPlanResponse(result);
    });
  };

  const loadLatestPlan = () => {
    runAction("latest", async () => {
      const id = requireStudentId();
      const response = await fetch(`${API_URL}/students/${id}/plans/latest`);
      const result = await readResponse<PlanResponse>(response);
      setPlanResponse(result);
    });
  };

  const totalPlannedUnits =
    planResponse?.plan.semesters.reduce((total, semester) => total + Number(semester.total_units || 0), 0) ?? 0;

  return (
    <main className="site-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="Aztec Counselor home">
          <span className="brand-mark">AC</span>
          <span>
            <strong>AZTEC COUNSELOR</strong>
            <small>Plan boldly. Graduate confidently.</small>
          </span>
        </a>
        <span className="system-status"><i /> Backend connected at port 8000</span>
      </header>

      <section className="hero" id="top">
        <div className="eyebrow">SDSU COURSE PLANNING - IMPROVED</div>
        <h1>bored of planning classes?</h1>
        <p>
          Just upload your transcript, note any specific requests and receive a plan. 
        </p>
        <div className="hero-rule"><span>01</span><i /><span>UPLOAD</span><i /><span>PLAN</span><i /><span>GRADUATE</span></div>
      </section>

      <section className="workspace">
        <div className="control-column">
          <section className="panel">
            <div className="panel-heading">
              <span className="step-number">01</span>
              <div><p>IDENTIFY</p><h2>Student profile</h2></div>
            </div>

            <label htmlFor="student-id">Existing student ID</label>
            <input
              id="student-id"
              inputMode="numeric"
              placeholder="e.g. 12"
              value={studentId}
              onChange={(event) => setStudentId(event.target.value)}
            />

            <div className="or-divider"><span>or create a student</span></div>

            <form className="inline-form" onSubmit={createStudent}>
              <div>
                <label htmlFor="major">Major</label>
                <input id="major" value={major} onChange={(event) => setMajor(event.target.value.toUpperCase())} />
              </div>
              <div>
                <label htmlFor="year">Current year</label>
                <select id="year" value={year} onChange={(event) => setYear(event.target.value)}>
                  <option value="1">1st year</option>
                  <option value="2">2nd year</option>
                  <option value="3">3rd year</option>
                  <option value="4">4th year</option>
                  <option value="5">5th year</option>
                </select>
              </div>
              <button className="secondary-button full" disabled={busyAction !== null} type="submit">
                {busyAction === "student" ? "Creating…" : "Create student profile"}
              </button>
            </form>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <span className="step-number">02</span>
              <div><p>UNDERSTAND</p><h2>Upload transcript</h2></div>
            </div>

            <label className="upload-box" htmlFor="transcript-file">
              <span className="upload-icon">↑</span>
              <strong>{file ? file.name : "Choose your transcript"}</strong>
              <small>{file ? "Ready to upload" : "PDF format · your file stays private"}</small>
              <input id="transcript-file" type="file" accept="application/pdf,.pdf" onChange={selectFile} />
            </label>
            <button className="secondary-button full" disabled={busyAction !== null || !file} onClick={uploadTranscript}>
              {busyAction === "upload" ? "Reading transcript…" : "Upload and extract courses"}
            </button>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <span className="step-number">03</span>
              <div><p>PERSONALIZE</p><h2>Set your priorities</h2></div>
            </div>

            <label htmlFor="constraints">Anything your plan should consider?</label>
            <textarea
              id="constraints"
              rows={4}
              placeholder="Example: I want to graduate in three years and avoid summer classes."
              value={constraints}
              onChange={(event) => setConstraints(event.target.value)}
            />
            <button className="primary-button full" disabled={busyAction !== null} onClick={generatePlan}>
              {busyAction === "generate" ? "Building your plan…" : "Generate my degree plan →"}
            </button>
            <button className="text-button" disabled={busyAction !== null} onClick={loadLatestPlan}>
              {busyAction === "latest" ? "Loading…" : "View my latest saved plan"}
            </button>
          </section>

          {uploadMessage && <div className="notice success">✓ {uploadMessage}</div>}
          {error && <div className="notice error">! {error}</div>}
        </div>

        <section className="results-panel">
          <div className="results-heading">
            <div>
              <p>YOUR ROADMAP</p>
              <h2>Degree plan</h2>
            </div>
            {planResponse && <span className={`review-pill ${planResponse.evaluation.passed ? "passed" : "review"}`}>
              {planResponse.evaluation.passed ? "✓ CHECKS PASSED" : "REVIEW NEEDED"}
            </span>}
          </div>

          {!planResponse ? (
            <div className="empty-plan">
              <div className="compass"><span>✦</span></div>
              <h3>Your roadmap will appear here.</h3>
              <p>Upload your transcript, share your priorities, and let Aztec Counselor organize the path ahead.</p>
            </div>
          ) : (
            <div className="plan-content">
              <div className="plan-summary">
                <div><strong>{planResponse.plan.semesters.length}</strong><span>semesters</span></div>
                <div><strong>{totalPlannedUnits}</strong><span>planned units</span></div>
                <div><strong>{planResponse.evaluation.warning_count}</strong><span>warnings</span></div>
              </div>

              <div className="semester-list">
                {planResponse.plan.semesters.map((semester, index) => (
                  <article className="semester-card" key={`${semester.term}-${index}`}>
                    <div className="semester-title">
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <h3>{semester.term}</h3>
                      <b>{semester.total_units} UNITS</b>
                    </div>
                    <div className="course-list">
                      {semester.courses.map((course) => (
                        <div className="course-row" key={course.course_code}>
                          <span className="course-code">{course.course_code}</span>
                          <span className="course-line" />
                          <span>{course.units} units</span>
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>

              {planResponse.plan.notes && (
                <div className="notes"><strong>Advisor notes</strong><p>{planResponse.plan.notes}</p></div>
              )}

              {planResponse.evaluation.issues.length > 0 && (
                <div className="issues">
                  <h3>Plan review</h3>
                  {planResponse.evaluation.issues.map((issue, index) => (
                    <div className={`issue ${issue.severity}`} key={`${issue.type}-${index}`}>
                      <b>{issue.severity}</b><span>{issue.message}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      </section>

      <footer>
        <span>AZTEC COUNSELOR</span>
        <p>Built to make every semester count.</p>
        <span>SAN DIEGO, CA</span>
      </footer>
    </main>
  );
}
