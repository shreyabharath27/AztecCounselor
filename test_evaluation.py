"""
Quick test for the plan checker. No database, AWS, or model calls needed.

Run from the project root (the SDSU_PLANNER folder), with (venv) active:
    python test_evaluation.py
"""

from app.evaluation import evaluate_plan


def course(code, credits, prerequisites=None, completed=False):
    return {
        "course_code": code,
        "course_name": code,
        "credits": credits,
        "prerequisites": prerequisites,
        "completed": completed,
    }


# Fake requirement groups shaped like the ones plans.py builds from Postgres
requirements = [
    {
        "requirement": "Lower Division Core", "level": "lower", "units_needed": 6,
        "rule": "Required", "units_completed": 3,
        "courses": [course("CS 150", 3, None, True), course("CS 160", 3, "CS 150")],
    },
    {
        "requirement": "Upper Division Core", "level": "upper", "units_needed": 6,
        "rule": "Required", "units_completed": 0,
        "courses": [course("CS 210", 3, "CS 160"), course("CS 240", 3, "CS 210 or CS 250")],
    },
    {
        "requirement": "Upper Division Electives", "level": "upper", "units_needed": 6,
        "rule": "Choose_Units", "units_completed": 0,
        "courses": [course("CS 450", 3, "CS 240"), course("CS 460", 3, None)],
    },
]
completed_codes = {"CS 150"}


def sem(term, *codes):
    return {"term": term, "courses": [{"course_code": c, "units": 3} for c in codes]}


# A plan that should pass (warnings about light terms are fine)
good_plan = {"semesters": [
    sem("Spring 2027", "CS 160", "CS 460"),
    sem("Fall 2027", "CS 210"),
    sem("Spring 2028", "CS 240"),
    sem("Fall 2028", "CS 450"),
]}

# A plan with deliberate mistakes
bad_plan = {"semesters": [
    sem("Spring 2027", "CS 240", "CS 150", "CS 999"),
    sem("Fall 2027", "CS 210", "CS 210"),
]}

good = evaluate_plan(good_plan, completed_codes, requirements)
bad = evaluate_plan(bad_plan, completed_codes, requirements)

print("GOOD PLAN:", "passed" if good["passed"] else "FAILED",
      f"({good['error_count']} errors, {good['warning_count']} warnings)")
print("BAD PLAN: ", "passed" if bad["passed"] else "failed",
      f"({bad['error_count']} errors, {bad['warning_count']} warnings)")
for issue in bad["issues"]:
    print(f"  [{issue['severity']}] {issue['type']}: {issue['message']}")

bad_types = {i["type"] for i in bad["issues"]}
expected = {"prerequisite_not_met", "already_completed", "unknown_course", "duplicate", "requirement_unmet"}

assert good["passed"], "the good plan should pass"
assert not bad["passed"], "the bad plan should fail"
assert expected <= bad_types, f"missing expected issue types: {expected - bad_types}"
print("\nAll checks behaved as expected.")