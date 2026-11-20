"use strict";

const report = JSON.parse(document.querySelector("#report-data").textContent);
const get = (id) => document.getElementById(id);
const rate = (fraction) => `${(100 * fraction).toFixed(1)}%`;
const delta = (value) => `${value > 0 ? "+" : ""}${value.toFixed(1)} pp`;

function element(tag, text, style) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (style) node.className = style;
  return node;
}

const overall = report.overall;
const gate = report.gate;
get("summary").textContent = `${overall.cases} paired cases across ${Object.keys(report.categories).length} categories.`;
get("gate-status").textContent = gate.passed ? "Within thresholds" : "Release blocked";
get("gate-status").parentElement.classList.toggle("passed", gate.passed);
get("gate-detail").textContent = `At most ${gate.max_regressions} regressions · Pass-rate change of at least ${delta(gate.min_delta_pp)}`;

const metrics = [
  ["Baseline pass rate", rate(overall.baseline_passes / overall.cases), `${overall.baseline_passes} of ${overall.cases} passed`],
  ["Candidate pass rate", rate(overall.candidate_passes / overall.cases), `${delta(overall.delta_pp)} vs. baseline`],
  ["Regressions", overall.regressions, `${overall.improvements} improved`],
  ["Reviewer agreement", rate(overall.agreement_rate), `${overall.disagreements} split decisions`],
];
for (const [label, value, detail] of metrics) {
  const card = element("article", undefined, "metric");
  card.append(element("p", label), element("strong", value), element("small", detail));
  get("metrics").append(card);
}

function rateCell(passes, count) {
  const cell = element("td");
  const chart = element("div", undefined, "rate");
  const bar = element("meter");
  bar.min = 0;
  bar.max = 1;
  bar.value = passes / count;
  bar.setAttribute("aria-hidden", "true");
  chart.append(bar, element("span", rate(passes / count)));
  cell.append(chart);
  return cell;
}

for (const [name, stats] of Object.entries(report.categories)) {
  const row = element("tr");
  const label = element("th", name);
  label.scope = "row";
  row.append(label, element("td", stats.cases),
    rateCell(stats.baseline_passes, stats.cases), rateCell(stats.candidate_passes, stats.cases),
    element("td", delta(stats.delta_pp), stats.delta_pp > 0 ? "up" : stats.delta_pp < 0 ? "down" : ""),
    element("td", stats.regressions));
  get("categories").append(row);
  const option = element("option", name);
  option.value = name;
  get("category").append(option);
}

function outcome(row) {
  if (row.baseline_pass) return row.candidate_pass ? "unchanged_pass" : "regression";
  return row.candidate_pass ? "improvement" : "unchanged_fail";
}

const labels = {
  regression: "Regression", improvement: "Improvement",
  unchanged_pass: "Both pass", unchanged_fail: "Both fail",
};

function variant(row, side) {
  const block = element("section", undefined, "variant");
  const decision = row[`${side}_pass`] ? "Pass" : "Fail";
  block.append(element("h3", `${side === "baseline" ? "Baseline" : "Candidate"} · ${decision}`),
    element("p", row[side].response, "response"));
  const list = element("ul", undefined, "reviews");
  for (const review of row[side].reviews) {
    const item = element("li");
    const scores = review.scores;
    item.append(
      element("strong", `${review.reviewer} · ${review.verdict}`),
      element("small", `Accuracy ${scores.accuracy}/5 · Instructions ${scores.instruction_following}/5 · Clarity ${scores.clarity}/5`),
      element("p", review.note),
    );
    list.append(item);
  }
  block.append(list);
  return block;
}

function caseDetails(row, result) {
  const details = element("details", undefined, "case");
  const title = element("summary");
  const color = result === "regression" ? " down" : result === "improvement" ? " up" : "";
  title.append(element("strong", row.id), element("span", row.category),
    element("span", labels[result], `tag${color}`));
  if (row.baseline_disagreement || row.candidate_disagreement) {
    title.append(element("span", "Split review", "tag"));
  }
  const body = element("div", undefined, "case-body");
  const pair = element("div", undefined, "case-grid");
  pair.append(variant(row, "baseline"), variant(row, "candidate"));
  body.append(element("strong", "Prompt"), element("p", row.prompt, "prompt"), pair);
  details.append(title, body);
  return details;
}

const rows = report.cases.map((row) => ({ row, result: outcome(row) }));

function renderCases() {
  const selectedOutcome = get("outcome").value;
  const selectedCategory = get("category").value;
  const splitOnly = get("split").checked;
  const matching = rows.filter(({ row, result }) =>
    (selectedOutcome === "all" || result === selectedOutcome)
    && (!selectedCategory || row.category === selectedCategory)
    && (!splitOnly || row.baseline_disagreement || row.candidate_disagreement));
  get("count").textContent = `${matching.length} of ${rows.length} cases`;
  get("cases").replaceChildren();
  for (const { row, result } of matching) get("cases").append(caseDetails(row, result));
  if (!matching.length) get("cases").append(element("p", "No cases match these filters."));
}

for (const id of ["outcome", "category", "split"]) get(id).addEventListener("change", renderCases);
const kappa = overall.cohens_kappa;
const pValue = overall.paired_p_value;
const [ciLow, ciHigh] = overall.delta_ci_pp;
get("method").textContent = `Change 95% CI ${ciLow.toFixed(1)} to ${ciHigh.toFixed(1)} pp · Cohen’s κ ${kappa === null ? "unavailable for these ratings" : kappa.toFixed(2)} · Exact McNemar p ${pValue < 0.001 ? "< 0.001" : pValue.toFixed(3)}`;
renderCases();
