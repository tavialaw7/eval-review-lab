"""Command-line interface for generating standalone evaluation reports."""

import argparse
import json
import math
import sys
from importlib.resources import files
from pathlib import Path

from .core import InputError, evaluate, read_cases


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="paired case records in JSONL format")
    parser.add_argument("--output-dir", type=Path, default=Path("build"))
    parser.add_argument("--max-regressions", type=int, default=0)
    parser.add_argument("--min-delta-pp", type=float, default=0)
    parser.add_argument("--enforce-gate", action="store_true", help="exit 1 when the gate fails")
    args = parser.parse_args(argv)
    if args.max_regressions < 0:
        parser.error("--max-regressions must be non-negative")
    if not math.isfinite(args.min_delta_pp) or not -100 <= args.min_delta_pp <= 100:
        parser.error("--min-delta-pp must be finite and between -100 and 100")
    try:
        report = evaluate(read_cases(args.input), args.max_regressions, args.min_delta_pp)
        payload = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False)
        assets = files("eval_review").joinpath("assets")
        template = assets.joinpath("report.html").read_text(encoding="utf-8")
        html = (
            template.replace("/* REPORT_CSS */", assets.joinpath("report.css").read_text(encoding="utf-8"))
            .replace("/* REPORT_JS */", assets.joinpath("report.js").read_text(encoding="utf-8"))
            .replace("<!-- REPORT_DATA -->", payload.replace("<", r"\u003c"))
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "report.json").write_text(payload + "\n", encoding="utf-8")
        (args.output_dir / "index.html").write_text(html, encoding="utf-8")
    except (InputError, OSError, UnicodeError) as error:
        parser.exit(2, f"eval-review: {error}\n")

    summary = report["overall"]
    status = "PASS" if report["gate"]["passed"] else "BLOCK"
    print(
        f"{status} | {summary['cases']} pairs | {summary['delta_pp']:+.1f} pp | "
        f"{summary['regressions']} regressions | {args.output_dir}"
    )
    return int(args.enforce_gate and not report["gate"]["passed"])


if __name__ == "__main__":
    sys.exit(main())
