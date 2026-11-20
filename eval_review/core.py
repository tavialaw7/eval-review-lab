"""Validate review inputs and compute paired evaluation metrics."""

import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path

DIMENSIONS = ("accuracy", "instruction_following", "clarity")
SIDES = ("baseline", "candidate")
VERDICTS = ("pass", "fail")
COLUMNS = """
    case_id TEXT NOT NULL,
    category TEXT NOT NULL,
    variant TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK (verdict IN ('pass', 'fail')),
    PRIMARY KEY (case_id, variant, reviewer)
"""
PAIRED_SQL = """
WITH by_side AS (
    SELECT case_id, category, variant,
           MIN(verdict = 'pass') AS all_pass,
           MIN(verdict = 'pass') <> MAX(verdict = 'pass') AS disagreement
      FROM reviews
     GROUP BY case_id, category, variant
)
SELECT baseline.case_id, baseline.category,
       baseline.all_pass AS baseline_pass,
       candidate.all_pass AS candidate_pass,
       baseline.disagreement AS baseline_disagreement,
       candidate.disagreement AS candidate_disagreement
  FROM by_side AS baseline
  JOIN by_side AS candidate USING (case_id, category)
 WHERE baseline.variant = 'baseline' AND candidate.variant = 'candidate'
 ORDER BY baseline.case_id
"""


class InputError(ValueError):
    """An input record does not satisfy the evaluation contract."""


def required_text(record, field):
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InputError(f"{field} must be a non-empty string")
    return value.strip()


def validate_side(data):
    if not isinstance(data, dict):
        raise InputError("each variant must be an object")
    response = required_text(data, "response")
    reviews = data.get("reviews")
    if not isinstance(reviews, list) or len(reviews) != 2:
        raise InputError("each variant requires exactly two reviews")
    clean = []
    for review in reviews:
        if not isinstance(review, dict):
            raise InputError("each review must be an object")
        reviewer = required_text(review, "reviewer")
        verdict = required_text(review, "verdict")
        if verdict not in VERDICTS:
            raise InputError("verdict must be pass or fail")
        scores = review.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(DIMENSIONS):
            raise InputError(f"scores must contain {', '.join(DIMENSIONS)}")
        if any(type(score) is not int or not 1 <= score <= 5 for score in scores.values()):
            raise InputError("scores must be integers from 1 through 5")
        clean.append({
            "reviewer": reviewer,
            "verdict": verdict,
            "scores": scores,
            "note": required_text(review, "note"),
        })
    if len({review["reviewer"] for review in clean}) != 2:
        raise InputError("the two reviewers must be distinct")
    return {"response": response, "reviews": sorted(clean, key=lambda row: row["reviewer"])}


def read_cases(path):
    cases = {}
    with Path(path).open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise InputError("each line must be a JSON object")
                case_id = required_text(record, "id")
                if case_id in cases:
                    raise InputError(f"duplicate case id {case_id!r}")
                cases[case_id] = {
                    "id": case_id,
                    "category": required_text(record, "category"),
                    "prompt": required_text(record, "prompt"),
                    **{side: validate_side(record.get(side)) for side in SIDES},
                }
            except (InputError, json.JSONDecodeError) as error:
                raise InputError(f"{path}:{line_number}: {error}") from error
    if not cases:
        raise InputError(f"{path}: expected at least one case")
    return cases


def kappa(contingency):
    """Pairwise Cohen's kappa for a shared reviewer pair."""
    both_fail, fail_pass, pass_fail, both_pass = contingency
    count = sum(contingency)
    observed = (both_fail + both_pass) / count
    expected = (
        (both_fail + fail_pass) * (both_fail + pass_fail)
        + (pass_fail + both_pass) * (fail_pass + both_pass)
    ) / count**2
    return None if expected == 1 else (observed - expected) / (1 - expected)


def paired_p_value(improvements, regressions):
    """Two-sided exact McNemar p-value from discordant case pairs."""
    discordant = improvements + regressions
    if not discordant:
        return 1.0
    # Evaluate the binomial lower tail in log space to avoid huge integers.
    log_total = math.lgamma(discordant + 1) - discordant * math.log(2)
    tail = math.fsum(
        math.exp(log_total - math.lgamma(k + 1) - math.lgamma(discordant - k + 1))
        for k in range(min(improvements, regressions) + 1)
    )
    return min(1.0, 2 * tail)


def summarize(rows):
    count = len(rows)
    baseline = sum(row["baseline_pass"] for row in rows)
    candidate = sum(row["candidate_pass"] for row in rows)
    improvements = sum(not row["baseline_pass"] and row["candidate_pass"] for row in rows)
    regressions = sum(row["baseline_pass"] and not row["candidate_pass"] for row in rows)
    disagreements = sum(row["baseline_disagreement"] + row["candidate_disagreement"] for row in rows)
    return {
        "cases": count,
        "baseline_passes": baseline,
        "candidate_passes": candidate,
        "delta_pp": 100 * (candidate - baseline) / count,
        "improvements": improvements,
        "regressions": regressions,
        "disagreements": disagreements,
        "agreement_rate": 1 - disagreements / (2 * count),
    }


def evaluate(cases, max_regressions, min_delta_pp):
    rows = []
    reviewer_pairs = set()
    contingency = [0] * 4
    for case in cases.values():
        for side in SIDES:
            first, second = case[side]["reviews"]
            reviewer_pairs.add((first["reviewer"], second["reviewer"]))
            contingency[2 * (first["verdict"] == "pass") + (second["verdict"] == "pass")] += 1
            rows.extend(
                (case["id"], case["category"], side, review["reviewer"], review["verdict"])
                for review in (first, second)
            )
    with closing(sqlite3.connect(":memory:")) as db, db:
        db.row_factory = sqlite3.Row
        db.execute(f"CREATE TABLE reviews ({COLUMNS})")
        db.executemany("INSERT INTO reviews VALUES (?, ?, ?, ?, ?)", rows)
        paired = [dict(row) for row in db.execute(PAIRED_SQL)]

    categories = {}
    for row in paired:
        categories.setdefault(row["category"], []).append(row)
    overall = summarize(paired)
    return {
        "overall": {
            **overall,
            "cohens_kappa": kappa(contingency) if len(reviewer_pairs) == 1 else None,
            "paired_p_value": paired_p_value(overall["improvements"], overall["regressions"]),
        },
        "categories": {name: summarize(categories[name]) for name in sorted(categories)},
        "gate": {
            "max_regressions": max_regressions,
            "min_delta_pp": min_delta_pp,
            "passed": overall["regressions"] <= max_regressions and overall["delta_pp"] >= min_delta_pp,
        },
        "cases": [{**cases[row["case_id"]], **row} for row in paired],
    }
