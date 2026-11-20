import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from eval_review.core import InputError, evaluate, kappa, paired_p_value, read_cases

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "data" / "example.jsonl"


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.cases = read_cases(EXAMPLE)

    def test_fixture_captures_lift_with_regressions(self):
        report = evaluate(self.cases, max_regressions=0, min_delta_pp=0)
        overall = report["overall"]
        self.assertEqual(overall["cases"], 24)
        self.assertEqual((overall["baseline_passes"], overall["candidate_passes"]), (13, 18))
        self.assertEqual((overall["improvements"], overall["regressions"]), (9, 4))
        self.assertEqual(overall["disagreements"], 2)
        self.assertAlmostEqual(overall["delta_pp"], 20.8333333333)
        self.assertAlmostEqual(overall["agreement_rate"], 46 / 48)
        self.assertAlmostEqual(overall["paired_p_value"], 0.266845703125)
        self.assertEqual(report["categories"]["Formatting"]["candidate_passes"], 5)
        self.assertFalse(report["gate"]["passed"])

    def test_threshold_is_inclusive_and_requires_both_conditions(self):
        delta = evaluate(self.cases, 4, 0)["overall"]["delta_pp"]
        self.assertTrue(evaluate(self.cases, 4, delta)["gate"]["passed"])
        self.assertFalse(evaluate(self.cases, 4, delta + 0.01)["gate"]["passed"])
        self.assertFalse(evaluate(self.cases, 3, delta)["gate"]["passed"])

    def test_split_review_flags_disagreement_and_fails_case(self):
        report = evaluate({"ER-009": self.cases["ER-009"]}, 0, 0)
        row = report["cases"][0]
        self.assertEqual(row["candidate_disagreement"], 1)
        self.assertEqual(row["candidate_pass"], 0)

    def test_kappa_with_constant_or_mixed_reviewer_pairs(self):
        self.assertIsNone(kappa([0, 0, 0, 6]))
        self.assertAlmostEqual(kappa([2, 0, 0, 2]), 1.0)
        case = copy.deepcopy(self.cases["ER-009"])
        case["baseline"]["reviews"][0]["reviewer"] = "reviewer-c"
        self.assertIsNone(evaluate({case["id"]: case}, 0, 0)["overall"]["cohens_kappa"])

    def test_paired_p_value_with_no_discordance_or_all_improvements(self):
        self.assertEqual(paired_p_value(0, 0), 1.0)
        self.assertAlmostEqual(paired_p_value(5, 0), 0.0625)
        self.assertAlmostEqual(paired_p_value(2, 2), 1.0)


class InputTests(unittest.TestCase):
    def setUp(self):
        self.record = json.loads(EXAMPLE.read_text(encoding="utf-8").splitlines()[0])

    def assert_bad_input(self, records, pattern):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "input.jsonl"
            data.write_text("\n".join(records), encoding="utf-8")
            with self.assertRaisesRegex(InputError, pattern):
                read_cases(data)

    def test_duplicate_case_reports_exact_line(self):
        item = json.dumps(self.record)
        self.assert_bad_input([item, "", item], r"input\.jsonl:3: duplicate case id")

    def test_duplicate_reviewer_is_rejected(self):
        reviews = self.record["candidate"]["reviews"]
        reviews[1]["reviewer"] = reviews[0]["reviewer"]
        self.assert_bad_input([json.dumps(self.record)], "reviewers must be distinct")

    def test_boolean_is_not_a_rubric_score(self):
        self.record["candidate"]["reviews"][0]["scores"]["clarity"] = True
        self.assert_bad_input([json.dumps(self.record)], "scores must be integers")

    def test_malformed_json_and_empty_input(self):
        self.assert_bad_input(["{"], r"input\.jsonl:1:")
        self.assert_bad_input([""], "expected at least one case")


class CliTests(unittest.TestCase):
    def run_report(self, source, destination, *options):
        return subprocess.run(
            [sys.executable, "-m", "eval_review", str(source), "--output-dir", str(destination), *options],
            cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def test_report_and_ci_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            blocked = self.run_report(EXAMPLE, destination, "--enforce-gate")
            self.assertEqual(blocked.returncode, 1, blocked.stderr)
            self.assertTrue((destination / "index.html").is_file())
            self.assertFalse(json.loads((destination / "report.json").read_text())["gate"]["passed"])
            self.assertEqual(self.run_report(EXAMPLE, destination).returncode, 0)
            passed = self.run_report(EXAMPLE, destination, "--max-regressions", "4", "--enforce-gate")
            self.assertEqual(passed.returncode, 0, passed.stderr)
            invalid = self.run_report(EXAMPLE, destination, "--min-delta-pp", "nan")
            self.assertEqual(invalid.returncode, 2)

    def test_embedded_data_preserves_html_like_text(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            source = destination / "input.jsonl"
            record = json.loads(EXAMPLE.read_text(encoding="utf-8").splitlines()[0])
            marker = "</script><p>literal review text</p>"
            record["prompt"] = marker
            source.write_text(json.dumps(record), encoding="utf-8")
            result = self.run_report(source, destination)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(marker, (destination / "index.html").read_text(encoding="utf-8"))
            exported = json.loads((destination / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(exported["cases"][0]["prompt"], marker)


if __name__ == "__main__":
    unittest.main()
