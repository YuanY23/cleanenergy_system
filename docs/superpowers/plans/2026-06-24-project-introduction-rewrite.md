# Project Introduction Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `项目总结汇总/项目介绍书.md` with a research-paper-style project memory handbook centered on integrated energy system modeling and suitable for daily interview preparation.

**Architecture:** Build a traceable fact base from the repository's model, data, paper, and result documents; then write one coherent Markdown document that separates modeling, implementation, and experiment conclusions. Validate the finished document for structure, terminology, links, result-version boundaries, and modeling emphasis before handoff.

**Tech Stack:** Markdown, repository source code and CSV/XLSX result artifacts, PowerShell, ripgrep, Git

---

### Task 1: Establish the authoritative project fact base

**Files:**
- Read: `README.md`
- Read: `项目总结汇总/研究论文.md`
- Read: `项目总结汇总/项目模型代码解析.md`
- Read: `项目总结汇总/数据来源汇总.md`
- Read: `src/zero_carbon_park/models/*.py`
- Read: `src/zero_carbon_park/planning/*.py`
- Read: `src/zero_carbon_park/uncertainty/*.py`
- Read: `new_source_results/run_manifest.json`
- Read: `new_source_results/01_full_pipeline/docs/project_conclusions.md`
- Read: `new_source_results/02_capacity_planning/results/v2_capacity_planning/planning_conclusion.md`
- Read: `new_source_results/03_pareto_cost_carbon/results/v3_pareto_cost_carbon/conclusion.md`
- Read: `new_source_results/04_uncertainty_stress_test/results/v4_uncertainty_stress_test/conclusion.md`
- Read: `new_source_results/05_stochastic_planning/results/v4_stochastic_planning/conclusion.md`
- Read: `new_source_results/06_robust_planning/results/v4_robust_planning/conclusion.md`

- [ ] **Step 1: Extract the implemented system boundary and model components**

Record the external energy interfaces, energy buses, generation devices, conversion devices, storage devices, loads, capacity variables, operating variables, state variables, and policy constraints that are present in source code.

- [ ] **Step 2: Trace the project evolution**

Confirm the sequence from S0—S5 day-ahead dispatch to typical-day annualization, deterministic capacity planning, investment sensitivity, cost-carbon Pareto analysis, stress testing, stochastic planning, and robust planning.

- [ ] **Step 3: Separate result versions**

Use `results_v1/` as the quantitative source for this rewrite because it matches the existing introduction and the later project paper built around the first-group dataset. Treat `new_source_results/` as a separate input-source experiment; do not combine its capacities, costs, emissions, Pareto trade-offs, or uncertainty results with `results_v1/`. Where a claim is not traceable to the selected batch, describe the mechanism without a precise number.

- [ ] **Step 4: Identify explicit limitations**

Include reconstructed load data, typical-day approximation, parameter uncertainty, omitted network constraints, linearization assumptions, and the difference between model validation and deployable engineering design.

### Task 2: Draft the modeling-centered document

**Files:**
- Modify: `项目总结汇总/项目介绍书.md`

- [ ] **Step 1: Write the fast-review layer**

Create a title, reading guide, one-page project overview, system diagram in compact text form, technical route, core modeling achievements, and a short statement of the author's contribution.

- [ ] **Step 2: Write the research narrative**

Explain the industrial-park decarbonization background, multi-energy coupling problem, research questions, system boundary, device composition, data system, and project evolution in causal order.

- [ ] **Step 3: Write the integrated energy system model as the main section**

For wind, photovoltaic generation, battery storage, electrolyzer, hydrogen tank, fuel cell, heat pump, gas boiler, the electricity/heat/hydrogen balances, market rules, carbon accounting, and capacity-operation coupling, use the sequence “physical role → variables → constraints → engineering meaning.”

- [ ] **Step 4: Write optimization and implementation as support material**

Explain the objective function, MILP representation, piecewise linearization, Pyomo model organization, HiGHS solution, scenario configuration, and result export without expanding solver internals beyond what is required to understand model feasibility.

- [ ] **Step 5: Write experiments as model validation**

Explain what S0—S5, deterministic capacity planning, sensitivity analysis, Pareto analysis, stress testing, stochastic planning, and robust planning each test. Use current rerun values only where their source and scope are unambiguous.

- [ ] **Step 6: Write engineering interpretation, limitations, and future work**

Discuss resource matching, flexibility allocation, conversion losses, economic selection of devices, risk preferences, limitations, and realistic next improvements.

- [ ] **Step 7: Write the interview-review layer**

Add a three-minute project narrative, concise model highlights, personal capability mapping, and technically defensible answers to common questions about why MILP was used, why fuel cells may have zero optimal capacity, how uncertainties are handled, and what should be improved next.

### Task 3: Replace the original document safely

**Files:**
- Modify: `项目总结汇总/项目介绍书.md`

- [ ] **Step 1: Apply one complete replacement patch**

Use `apply_patch` to replace the existing content while preserving the UTF-8 Markdown file path and avoiding edits to unrelated user files.

- [ ] **Step 2: Confirm UTF-8 readability**

Run a Node UTF-8 read and confirm the title and Chinese headings render correctly. Expected result: no mojibake and no replacement character `�`.

- [ ] **Step 3: Inspect the exact diff**

Run:

```powershell
git diff -- "项目总结汇总/项目介绍书.md"
```

Expected result: only the intended introduction document is shown, with a complete rewrite rather than partial encoding corruption.

### Task 4: Validate document quality and traceability

**Files:**
- Verify: `项目总结汇总/项目介绍书.md`

- [ ] **Step 1: Validate required sections**

Confirm the document contains project overview, background, research questions, system boundary, data, modeling, optimization implementation, experiments, engineering interpretation, limitations, personal contribution, and interview review sections.

- [ ] **Step 2: Scan for unfinished or inflated language**

Run:

```powershell
rg -n "待.{0,2}补充|极其先进|完美表达|绝对最优|file:///" "项目总结汇总/项目介绍书.md"
```

Expected result: no matches.

- [ ] **Step 3: Validate internal Markdown links**

Check each relative file link against the workspace. Expected result: every linked path exists.

- [ ] **Step 4: Validate technical emphasis**

Confirm that integrated energy system modeling is the largest technical section, experimental results are used as evidence, and solver discussion remains subordinate.

- [ ] **Step 5: Validate numerical claims**

For every precise capacity, cost, emission, or percentage claim, confirm the result batch and source file. Remove or qualify claims that cannot be traced consistently.

- [ ] **Step 6: Perform a complete reader pass**

Read the document from beginning to end and verify that a reader can answer: why the project exists, how the energy carriers interact, what was modeled, how the model evolved, what experiments prove, what the main limitations are, and how the author should explain the project in an interview.

### Task 5: Final verification and handoff

**Files:**
- Verify: `项目总结汇总/项目介绍书.md`

- [ ] **Step 1: Report document statistics**

Report UTF-8 character count, heading count, and the final file path.

- [ ] **Step 2: Report verification evidence**

Summarize link checks, placeholder scan, encoding check, result traceability review, and modeling-emphasis review.

- [ ] **Step 3: Preserve unrelated worktree changes**

Run `git status --short` and confirm that no unrelated user file was modified by this execution.
