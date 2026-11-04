"""
Evaluation Engine: rule-based checks on a generated degree plan.

No LLM and no database calls in here. These are plain rules applied to data,
so the same plan always gets the same verdict.

evaluate_plan() returns:
    {
      "passed": True or False,   # False if any "error" issues were found
      "error_count": int,
      "warning_count": int,
      "issues": [
        {"severity": "error" or "warning", "type": str,
         "course": str or None, "term": str or None, "message": str},
        ...
      ]
    }

Errors are problems the model can fix: a prerequisite scheduled too late,
a requirement left unfinished, a term over the unit limit.
Warnings are things the checker can't be sure about: prerequisites that
aren't courses, or catalog units that differ from what the model listed.
"""

import re

COURSE_CODE = re.compile(r"\b([A-Z]{2,5})\s?(\d{2,3}[A-Z]?)\b")
NON_COURSE_HINTS = ("consent", "permission", "admission", "standing", "placement", "score", "instructor")
MIN_TERM_UNITS = 12
MAX_TERM_UNITS = 16  # keep in step with the "12 to 16 units" rule in the prompt (plans.py)


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _issue(severity, kind, message, course=None, term=None):
    return {"severity": severity, "type": kind, "course": course, "term": term, "message": message}


def _result(issues):
    errors = sum(1 for i in issues if i["severity"] == "error")
    return {
        "passed": errors == 0,
        "error_count": errors,
        "warning_count": len(issues) - errors,
        "issues": issues,
    }


def parse_prerequisites(text):
    """
    Turn catalog prerequisite text into a rough structure.

      "CS 150 and MATH 150"   -> clauses [{CS 150}, {MATH 150}]
      "MATH 150 or MATH 141"  -> clauses [{MATH 150, MATH 141}]

    A clause is satisfied when ANY course in it is satisfied, and every clause
    must be satisfied. This is a heuristic: catalog wording varies, so unusual
    phrasing can be misread. Grade requirements ("C or better") are ignored.
    """
    if not text:
        return {"clauses": [], "concurrent_ok": False, "non_course": False}

    clauses = []
    for piece in re.split(r";|,|\band\b", text, flags=re.IGNORECASE):
        codes = {f"{m.group(1)} {m.group(2)}" for m in COURSE_CODE.finditer(piece)}
        if codes:
            clauses.append(codes)

    lowered = text.lower()
    return {
        "clauses": clauses,
        "concurrent_ok": "concurrent" in lowered,
        "non_course": any(hint in lowered for hint in NON_COURSE_HINTS),
    }


def evaluate_plan(plan, completed_codes, requirements):
    """
    plan:            the model's JSON, {"semesters": [{"term", "courses": [...]}]}
    completed_codes: set of course codes the student already finished
    requirements:    the requirement groups built in plans.py
    """
    issues = []

    if not isinstance(plan, dict) or not isinstance(plan.get("semesters"), list) or not plan["semesters"]:
        return _result([
            _issue("error", "bad_format", "The plan must be a JSON object with a non-empty 'semesters' list.")
        ])

    # Every course the plan is allowed to use, with its catalog details
    catalog = {}
    for group in requirements:
        for course in group["courses"]:
            catalog[course["course_code"]] = course

    done = set(completed_codes)  # courses finished before the term being checked
    planned = set()              # every course scheduled anywhere in the plan
    last_index = len(plan["semesters"]) - 1

    for index, sem in enumerate(plan["semesters"]):
        if not isinstance(sem, dict) or not isinstance(sem.get("courses"), list):
            issues.append(_issue("error", "bad_format", f"Semester #{index + 1} is malformed."))
            continue

        term = sem.get("term", f"term {index + 1}")
        entries = [c for c in sem["courses"] if isinstance(c, dict) and c.get("course_code")]
        term_codes = {c["course_code"] for c in entries}
        term_units = 0.0

        for entry in entries:
            code = entry["course_code"]
            info = catalog.get(code)

            if info is None:
                issues.append(_issue(
                    "error", "unknown_course",
                    f"{code} is not in any requirement group for this major.", code, term))
                term_units += _num(entry.get("units"))
                continue

            if code in completed_codes:
                issues.append(_issue("error", "already_completed", f"{code} was already completed.", code, term))
            if code in planned:
                issues.append(_issue("error", "duplicate", f"{code} is scheduled more than once.", code, term))
            planned.add(code)

            # Trust the catalog's units over the model's
            catalog_units = info.get("credits")
            term_units += _num(catalog_units) if catalog_units is not None else _num(entry.get("units"))
            if catalog_units is not None and abs(_num(entry.get("units")) - _num(catalog_units)) > 0.01:
                issues.append(_issue(
                    "warning", "units_mismatch",
                    f"{code}: the plan lists {entry.get('units')} units but the catalog says {catalog_units}.",
                    code, term))

            # Prerequisites
            prereq = parse_prerequisites(info.get("prerequisites"))
            for clause in prereq["clauses"]:
                satisfied = any(
                    c in done or (prereq["concurrent_ok"] and c in term_codes)
                    for c in clause
                )
                if satisfied:
                    continue
                options = " or ".join(sorted(clause))
                if any(c in catalog for c in clause):
                    # The model could have scheduled it, so this one is fixable
                    issues.append(_issue(
                        "error", "prerequisite_not_met",
                        f"{code} needs {options} completed in an earlier term.", code, term))
                else:
                    issues.append(_issue(
                        "warning", "prerequisite_outside_plan",
                        f"{code} lists {options} as a prerequisite, but it isn't completed and isn't in "
                        f"this degree's requirement groups. Check whether AP or transfer credit covers it.",
                        code, term))
            if prereq["non_course"]:
                issues.append(_issue(
                    "warning", "unverifiable_prerequisite",
                    f"{code} has a prerequisite the checker can't verify (instructor consent, placement, etc.).",
                    code, term))

        done |= term_codes

        # Unit limits for the term
        if term_units > MAX_TERM_UNITS:
            issues.append(_issue(
                "error", "term_overloaded",
                f"{term} has {term_units:g} units (max {MAX_TERM_UNITS}).", None, term))
        elif term_units < MIN_TERM_UNITS and index != last_index:
            issues.append(_issue(
                "warning", "term_light",
                f"{term} has only {term_units:g} units (target {MIN_TERM_UNITS} to {MAX_TERM_UNITS}).", None, term))

        if "total_units" in sem and abs(_num(sem["total_units"]) - term_units) > 0.01:
            issues.append(_issue(
                "warning", "total_units_mismatch",
                f"{term}: the plan says {sem['total_units']} total units but the courses add up to {term_units:g}.",
                None, term))

    # Does the finished plan actually satisfy every requirement group?
    for group in requirements:
        name = group.get("requirement", "a requirement group")
        rule = str(group.get("rule", "")).lower()
        group_courses = group["courses"]

        if rule == "required":
            # "Required" means every course in the group
            missing = [
                c["course_code"] for c in group_courses
                if not c["completed"] and c["course_code"] not in planned
            ]
            if missing:
                issues.append(_issue("error", "requirement_unmet", f"'{name}' still needs: {', '.join(missing)}."))
        elif rule == "choose_units":
            earned = _num(group.get("units_completed")) + sum(
                _num(c.get("credits")) for c in group_courses
                if c["course_code"] in planned and not c["completed"]
            )
            needed = _num(group.get("units_needed"))
            if earned < needed:
                issues.append(_issue(
                    "error", "requirement_unmet",
                    f"'{name}' has {earned:g} of {needed:g} required units."))
        else:
            issues.append(_issue(
                "warning", "unknown_rule",
                f"'{name}' has an unrecognized rule '{group.get('rule')}', so it wasn't checked."))

    return _result(issues)