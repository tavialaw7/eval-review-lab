# Interview walkthrough

## Opening pitch

“Eval Review Lab is a review pipeline for comparing two versions of an LLM on the same prompts. One thing I wanted to surface was how an improved overall pass rate can hide cases that got worse. In the demo, the candidate goes from 54.2% to 75.0%, but four existing passes regress. The gate blocks the release, and the dashboard lets me trace each regression back to the original prompt and reviewer evidence.”

## Two-minute demo

1. **Show the result.** Open `docs/demo.html`. Point out the 20.8 percentage-point gain and the four regressions.
2. **Show the evidence.** Filter for **Regression** and **Formatting**, then expand **ER-015**. The candidate gives the right date but adds extra text against a date-only instruction.
3. **Show a reviewer split.** Reset the category filter and check **Reviewer disagreement only** with **Regression** still selected. In **ER-009**, the candidate includes an extra label. The notes show exactly where the reviewers drew different acceptance boundaries.
4. **Show the automation.** Run the CLI with `--enforce-gate`. The exit status is 1 and both report files are available for diagnosis.

## Technical questions to prepare

| Question | Discussion point |
| --- | --- |
| Why pair by prompt? | It holds the evaluation item constant and exposes improved and regressed cases directly. Unpaired averages lose that evidence. |
| Why use SQLite? | The SQL query groups ratings per case and variant, then joins the two sides. Primary keys enforce reviewer uniqueness after validation. In-memory storage keeps the demo reproducible and avoids operations overhead. |
| What does reviewer agreement measure? | Raw agreement counts matching verdicts. Cohen’s κ adjusts for expected chance agreement under the reviewer marginals. It is unavailable when the reviewer pair varies or expected agreement is 100%. |
| Does this sample prove the candidate is better? | The 24 cases are synthetic. The exact paired p-value is about 0.267, and the sample offers no evidence about performance on production traffic. The gate is a policy rule with its own thresholds. |
| What would you change for a real release? | Build a representative challenge set and track rubric, model, and dataset versions. Define treatment for high-severity cases and specify adjudication, acceptable regression thresholds, and evaluation coverage before testing. |

## Portfolio description

Eval Review Lab is a Python and SQLite tool for paired LLM evaluation. It calculates pass-rate change, flags regressions and reviewer disagreements, and generates a shareable dashboard with case-level evidence. A configurable release gate provides an exit status that a CI pipeline can enforce.
