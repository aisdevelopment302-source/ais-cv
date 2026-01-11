---
name: create-ux-design
description: Work with a peer UX Design expert to plan your applications UX patterns, look and feel.
web_bundle: true
---

# Create UX Design Workflow

**Goal:** Create comprehensive UX design specifications through collaborative visual exploration and informed decision-making where you act as a UX facilitator working with a product stakeholder.

---

## WORKFLOW ARCHITECTURE

This uses **micro-file architecture** for disciplined execution:

- Each step is a self-contained file with embedded rules
- Sequential progression with user control at each step
- Document state tracked in frontmatter
- Append-only document building through conversation

---

## SESSION CONTINUITY RULE

**MANDATORY: After completing each step and saving to document, provide a continuation prompt for fresh session.**

This rule ensures context remains fresh across long workflows. After each step is saved:

1. **Summarize what was completed** in the current step
2. **Provide a copy-paste ready prompt** for the user to continue in a new session
3. **The prompt must include:**
   - Agent to load (UX Designer / Sally)
   - Working document path (`ux-design-specification.md`)
   - PRD reference path
   - Starter kit reference (if applicable)
   - Current step completed and next step to execute
   - Key design decisions made so far (brief summary)
   - Any Party Mode enhancements applied
   - User preferences established

**Prompt Template:**
```
I'm continuing a UX Design workflow for {project_name}.
**Context files to load:**
1. Read `{output_folder}/ux-design-specification.md` — working document with Steps 1-{N} complete
2. Read `{output_folder}/prd.md` — the PRD with user journeys and requirements
3. Reference `{starter_kit_path}` — starter kit we're building on (if applicable)

**Where we are:**
- Acting as Sally (UX Designer agent)
- Just completed Step {N}: {step_name}
- Ready to execute Step {N+1}: {next_step_name}

**Key design decisions from previous steps:**
{bullet list of major decisions}

**Party Mode enhancements applied:**
{list of enhancements if any}

**User preferences:**
{user preferences established}

Please load the UX Designer agent and execute Step {N+1}.
```

---

## INITIALIZATION

### Configuration Loading

Load config from `{project-root}/_bmad/bmm/config.yaml` and resolve:

- `project_name`, `output_folder`, `user_name`
- `communication_language`, `document_output_language`, `user_skill_level`
- `date` as system-generated current datetime

### Paths

- `installed_path` = `{project-root}/_bmad/bmm/workflows/2-plan-workflows/create-ux-design`
- `template_path` = `{installed_path}/ux-design-template.md`
- `default_output_file` = `{output_folder}/ux-design-specification.md`

### Output Files

- Color themes: `{output_folder}/ux-color-themes.html`
- Design directions: `{output_folder}/ux-design-directions.html`

### Input Document Discovery

Discover context documents for UX context (Priority: Analysis folder first, then main folder, then sharded):

- PRD: `{output_folder}/analysis/*prd*.md` or `{output_folder}/*prd*.md` or `{output_folder}/*prd*/**/*.md`
- Product brief: `{output_folder}/analysis/*brief*.md` or `{output_folder}/*brief*.md` or `{output_folder}/*brief*/**/*.md`
- Epics: `{output_folder}/analysis/*epic*.md` or `{output_folder}/*epic*.md` or `{output_folder}/*epic*/**/*.md`
- Research: `{output_folder}/analysis/research/*research*.md` or `{output_folder}/*research*.md` or `{output_folder}/*research*/**/*.md`
- Brainstorming: `{output_folder}/analysis/brainstorming/*brainstorming*.md` or `{output_folder}/*brainstorming*.md`

---

## EXECUTION

Load and execute `steps/step-01-init.md` to begin the UX design workflow.
