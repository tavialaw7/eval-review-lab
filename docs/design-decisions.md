# Design decisions and FAQ

## Walkthrough

1. **Show the result.** Open the [live demo](https://tavialaw7.github.io/eval-review-lab/). The candidate gains 20.8 percentage points, but four existing passes regress.
2. **Show the evidence.** Filter for **Regression** and **Formatting**, then expand **ER-015**. The candidate gives the right date but adds extra text against a date-only instruction.
3. **Show a reviewer split.** Reset the category filter and check **Reviewer disagreement only** with **Regression** still selected. In **ER-009**, the candidate includes an extra label, and the notes show where the reviewers drew different acceptance boundaries.
4. **Show the automation.** Run the CLI with `--enforce-gate`. The exit status is 1 and both report files are written for diagnosis.

## Design questions

| Question | Discussion point |
| --- | --- |
| Why pair by prompt? | It holds the evaluation item constant and exposes improved and regressed cases directly. Unpaired averages lose that evidence. |
| Why use SQLite? | The SQL query groups ratings per case and variant, then joins the two sides. Primary keys enforce reviewer uniqueness after validation. In-memory storage keeps the demo reproducible and avoids operations overhead. |
| What does reviewer agreement measure? | Raw agreement counts matching verdicts. Cohen’s κ adjusts for expected chance agreement under the reviewer marginals. It is unavailable when the reviewer pair varies or expected agreement is 100%. |
| Does this sample prove the candidate is better? | The 24 cases are synthetic. The exact paired p-value is about 0.267, the 95% interval on the change spans −7.4 to +49.1 points, and the sample offers no evidence about performance on production traffic. The gate is a policy rule with its own thresholds. |
| What would you change for a real release? | Build a representative challenge set and track rubric, model, and dataset versions. Define treatment for high-severity cases and specify adjudication, acceptable regression thresholds, and evaluation coverage before testing. |
