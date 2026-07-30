"""Regenerate the CodeSwarm Solution Design PDF.

Requires reportlab (pip install reportlab). Run: python scripts/make_design_pdf.py
"""

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    Preformatted, PageBreak, NextPageTemplate, ListFlowable, ListItem, KeepTogether,
)

import os
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "CodeSwarm-Solution-Design.pdf")

# ---- palette ---------------------------------------------------------------
NAVY = HexColor("#0B2E4F")
TEAL = HexColor("#0E7C86")
AMBER = HexColor("#B26B00")
LIGHT = HexColor("#F2F5F7")
GRID = HexColor("#D3DCE3")
INK = HexColor("#1F2A33")
MUTED = HexColor("#5B6B78")
GREEN = HexColor("#1E7B4F")
RED = HexColor("#B23A3A")

TITLE = "CodeSwarm"
SUBTITLE = "Solution Design Document"
META = [
    ("Project", "CodeSwarm — provider-agnostic multi-agent SDLC framework"),
    ("Version", "0.2.0 (draft)"),
    ("Author", "Ankur Srivastava"),
    ("Date", "30 July 2026"),
    ("Repository", "github.com/ankssri/codingswarm"),
    ("Status", "Implemented & verified"),
]

# ---- styles ----------------------------------------------------------------
ss = getSampleStyleSheet()
body = ParagraphStyle("body", parent=ss["Normal"], fontName="Helvetica", fontSize=10,
                      leading=15, textColor=INK, spaceAfter=6)
small = ParagraphStyle("small", parent=body, fontSize=8.5, leading=12, textColor=MUTED)
h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=16,
                    textColor=NAVY, spaceBefore=6, spaceAfter=4)
h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.5,
                    textColor=TEAL, spaceBefore=10, spaceAfter=3)
cell = ParagraphStyle("cell", parent=body, fontSize=9, leading=12, spaceAfter=0)
cellb = ParagraphStyle("cellb", parent=cell, fontName="Helvetica-Bold", textColor=NAVY)
cellw = ParagraphStyle("cellw", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
mono = ParagraphStyle("mono", parent=body, fontName="Courier", fontSize=8.2, leading=11)

story = []


def para(txt, style=body):
    story.append(Paragraph(txt, style))


def bullets(items, style=body):
    story.append(ListFlowable(
        [ListItem(Paragraph(t, style), leftIndent=6, value="•") for t in items],
        bulletType="bullet", bulletColor=TEAL, leftIndent=12, bulletFontSize=8,
    ))
    story.append(Spacer(1, 4))


def section(num, title):
    story.append(Spacer(1, 6))
    tbl = Table([[Paragraph(f"{num}", ParagraphStyle('n', parent=h1, textColor=TEAL)),
                  Paragraph(title, h1)]], colWidths=[1.0*cm, None])
    tbl.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1.1, TEAL),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6))


def sub(title):
    para(title, h2)


def diagram(text):
    t = Table([[Preformatted(text, mono)]], colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#EEF3F6")),
        ("BOX", (0, 0), (-1, -1), 0.6, HexColor("#B9C7D2")),
        ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(Spacer(1, 2))
    story.append(t)
    story.append(Spacer(1, 6))


def callout(title, text, color=AMBER, bg=HexColor("#FBF3E6")):
    inner = [Paragraph(f"<b>{title}</b>", ParagraphStyle('ct', parent=body, textColor=color, spaceAfter=2)),
             Paragraph(text, ParagraphStyle('cx', parent=body, fontSize=9.3, leading=13))]
    t = Table([[inner]], colWidths=[None])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 3, color),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(Spacer(1, 3))
    story.append(t)
    story.append(Spacer(1, 6))


def table(headers, rows, col_widths=None, header_bg=NAVY):
    data = [[Paragraph(h, cellw) for h in headers]]
    for r in rows:
        data.append([Paragraph(c, cell) if not str(c).startswith("§B§") else Paragraph(c[3:], cellb) for c in r])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t.setStyle(TableStyle(style))
    story.append(Spacer(1, 2))
    story.append(t)
    story.append(Spacer(1, 8))


# ===========================================================================
# CONTENT
# ===========================================================================

story.append(NextPageTemplate("body"))
story.append(PageBreak())  # cover is drawn on page 1; content starts page 2

# ---- Table of contents ----
para("Contents", h1)
story.append(Spacer(1, 4))
toc_items = [
    "1  Executive Summary", "2  Objectives & Requirements", "3  Design Principles",
    "4  High-Level Architecture", "5  The Agent Swarm", "6  The Quality Gates",
    "7  Per-Feature Build Loop", "8  Execution Model: Parallel Build & Merge",
    "9  LLM Provider Abstraction", "10  Tools and the MCP Boundary",
    "11  Observability & Artifacts", "12  Configuration",
    "13  Security & Privacy", "14  Alignment with Anthropic Best Practices",
    "15  Limitations & Future Work", "Appendix A  Repository Layout",
    "Appendix B  CLI Reference",
]
for it in toc_items:
    para(it, ParagraphStyle("toc", parent=body, leftIndent=8, spaceAfter=3))
story.append(PageBreak())

# 1
section("1", "Executive Summary")
para("CodeSwarm is a standalone, vendor-neutral framework that automates the full software "
     "development lifecycle using a coordinated <b>swarm of LLM agents</b>. From a one-line idea "
     "or a short spec it produces a working, tested software project: it gathers requirements, "
     "designs an architecture, breaks the work into features, then builds, tests, and reviews each "
     "feature until it passes a strict quality bar.")
para("Its defining property is that <b>quality is verified, not asserted</b>. A feature is only "
     "marked <i>done</i> when its tests actually execute and pass, an independent reviewer approves "
     "the code, and a dedicated security reviewer clears it. Failing features are reported, never "
     "silently shipped.")
para("The framework runs as a plain Python program with <b>no dependency on Claude Code or any "
     "single LLM vendor</b>. It supports BytePlus ModelArk, OpenAI, and Google Gemini through one "
     "OpenAI-compatible client, plus an offline mock provider for demos and CI.")
callout("The core guarantee",
        "For a project with N features, CodeSwarm returns a per-feature table of "
        "tests / review / security outcomes backed by a real test run — turning "
        "\"the model generated some code\" into \"each feature is built and verified.\"")

# 2
section("2", "Objectives & Requirements")
sub("Business objectives")
bullets([
    "Replace manual, step-by-step SDLC execution with a repeatable automated pipeline.",
    "Remove single-vendor lock-in: run the same swarm on BytePlus, OpenAI, or Gemini.",
    "Guarantee that generated features are individually built and tested without bugs.",
    "Be operable by anyone with Python and an API key — no proprietary runtime.",
])
sub("Functional requirements")
bullets([
    "Ingest a product idea (inline or YAML spec) and drive it through requirements → design → "
    "planning → build/test/review → integration.",
    "Enforce automated quality gates per feature with a bounded retry budget.",
    "Persist the artifacts of every phase to disk for inspection and audit.",
    "Expose a simple CLI and a diagnostic command.",
])
sub("Non-functional requirements")
bullets([
    "Provider-agnostic; adding a provider is a small, localized change.",
    "Deterministic offline mode for testing without API keys.",
    "Minimal runtime dependencies; generated projects stay dependency-light.",
    "Transparent, observable execution.",
])

# 3
section("3", "Design Principles")
table(["Principle", "How CodeSwarm applies it"], [
    ["§B§Verify, don't trust", "Tests are executed in a subprocess as an objective gate; a reviewer and a security reviewer add independent judgment."],
    ["§B§Simple core, smart edges", "Orchestration is deterministic Python; intelligence lives in swappable agents, prompts, and tools."],
    ["§B§Vendor neutrality", "One OpenAI-compatible client behind a tiny provider interface; per-role provider/model overrides."],
    ["§B§Isolation for safety", "Parallel features build in isolated workspaces; a merge gate re-verifies the whole."],
    ["§B§Observability by default", "Every phase writes human-readable artifacts as it completes."],
], col_widths=[4.3*cm, None])

# 4
section("4", "High-Level Architecture")
para("CodeSwarm is layered. The CLI parses input and configuration; the Orchestrator runs the "
     "lifecycle; specialist Agents perform each role via an LLM provider; local Tools let agents "
     "read, write and test real files; a Workspace guards file writes; and a Sandbox executes the "
     "generated test-suite.")
diagram(
"""CLI (cli.py)  -- parses args, loads config, .env, prints progress
   |
   v
Orchestrator (pipeline.py :: Swarm)  -- runs the 5 SDLC phases + quality loop
   |
   +-- Agents (agents/)         specialist roles, one responsibility each
   |       |  every agent calls
   |       v
   |     LLM Providers (llm/)    OpenAI-compatible: BytePlus | OpenAI | Gemini | mock
   |
   +-- Tools (tools.py)         local read/write/run/coverage tools (NOT MCP)
   +-- Workspace (workspace.py) guarded file writes + snapshots
   +-- Sandbox (sandbox.py)     executes pytest / coverage  = objective gate
                                     |
                                     v
                        ./output/<project>/   (code, tests, .codeswarm/ artifacts)""")
callout("Why Python", "Python is the native language of LLM tooling and — crucially — lets the "
        "swarm run the tests it writes in-process. That is what makes the quality gate real rather "
        "than cosmetic.", color=TEAL, bg=HexColor("#E8F3F4"))

# 5
section("5", "The Agent Swarm")
para("Each agent is a thin specialist over a provider. Requirements, Architect, Planner, Reviewer, "
     "Security Reviewer and Integrator are single-shot; the Developer and Tester are <b>agentic</b> "
     "— they use tools in a loop to inspect, edit and verify the real project.")
table(["Agent", "Type", "Responsibility"], [
    ["§B§Requirements", "single-shot", "Turn the idea into concrete, testable requirements."],
    ["§B§Architect", "single-shot", "Produce a minimal technical design and file layout."],
    ["§B§Planner", "single-shot", "Break the design into independently testable features + acceptance criteria."],
    ["§B§Developer", "agentic loop", "Read/write files and run tests via tools; self-correct until the feature works."],
    ["§B§Tester", "agentic loop", "Write pytest tests and use coverage to close gaps."],
    ["§B§Reviewer", "single-shot", "Correctness gate — approve only if correct and adequately tested."],
    ["§B§Security Reviewer", "single-shot", "Security gate — injection, unsafe eval, path traversal, secrets, etc."],
    ["§B§Integrator", "single-shot", "Assemble README and requirements for the generated project."],
], col_widths=[3.4*cm, 2.4*cm, None])

# 6
section("6", "The Quality Gates")
para("For every feature the orchestrator runs a build/test/review loop, up to "
     "<b>max_feature_iterations</b> (default 3). A feature is DONE only when <b>all three</b> gates "
     "pass; otherwise the failures are compiled into feedback and fed back for another attempt.")
diagram(
"""  Developer AGENT implements/fixes (reads, writes, runs tests)
            |
            v
  Tester AGENT writes tests + checks coverage
            |
            v
  GATE 1 (objective)   : run pytest        --- fail ----+
            | pass                                       |
            v                                            |
  GATE 2 (correctness) : reviewer agent     -- reject --+
            | approve                                    |
            v                                            |
  GATE 3 (security)    : security agent     -- block ---+
            | clear                                      |
            v                                            v
      Feature = DONE            compile feedback -> next attempt (<= 3)""")
para("If a feature never satisfies all three gates within the retry budget it is marked "
     "<b>FAILED</b> and surfaced in the report — the swarm never ships an unverified feature.")

# 7
section("7", "Per-Feature Build Loop")
para("The Developer is a genuine tool-using agent (mirroring how modern coding agents work) rather "
     "than a one-shot code generator. It is given a toolbox bound to the feature's workspace:")
table(["Tool", "Purpose"], [
    ["§B§list_files", "Enumerate the current project files."],
    ["§B§read_file", "Read a file before changing it."],
    ["§B§write_file", "Create or overwrite a file with full contents."],
    ["§B§run_tests", "Execute pytest and read the output — self-check."],
    ["§B§check_coverage", "(Tester) find uncovered lines to add tests for."],
    ["§B§finish", "Signal the feature is implemented and passing."],
], col_widths=[3.6*cm, None])
para("This design also solves context management: the agent reads only what it needs from disk "
     "rather than being handed the entire codebase as text, which scales far better.")

# 8
section("8", "Execution Model: Parallel Build & Merge")
para("By default, independent features build <b>concurrently</b>, each in its own isolated scratch "
     "workspace (via a thread pool, up to <b>max_parallel_features</b>). Because agents are "
     "stateless per call and the Tester/Reviewer take files as arguments, parallel execution is "
     "race-free. After the barrier, all features are merged into the main workspace and the "
     "<b>full combined suite</b> runs. Any cross-feature regression triggers an integration-repair "
     "loop that puts the agentic developer on the merged project until the whole suite is green.")
diagram(
"""  plan --+--> [feature A]  build/test/review  (isolated dir) --+
         +--> [feature B]  build/test/review  (isolated dir) --+
         +--> [feature C]  build/test/review  (isolated dir) --+
                                                               |
                                                               v
                     merge all --> run FULL pytest suite (regression gate)
                                                               |
                                                               v
              pass   OR   integration-repair loop --> pass""")
callout("Trade-off & safety net",
        "Parallel is faster; sequential (--sequential) lets each feature see prior code as it builds. "
        "Same-path conflicts across parallel features are last-writer-wins — the integration-repair "
        "loop, not a 3-way merge, is the safety net. In practice each feature owns distinct modules.")

# 9
section("9", "LLM Provider Abstraction")
para("All supported providers speak the OpenAI chat + tool-calling protocol, so a single "
     "<b>OpenAICompatibleProvider</b> handles them by swapping base URL and key. Roles can override "
     "provider/model independently — e.g. a stronger model for review, a cheaper one for the "
     "developer loop, or a different model reviewing than writing.")
table(["Provider", "Endpoint style", "Key (env)"], [
    ["§B§BytePlus ModelArk", "ark.ap-southeast.bytepluses.com/api/v3", "ARK_API_KEY"],
    ["§B§OpenAI", "api.openai.com/v1", "OPENAI_API_KEY"],
    ["§B§Google Gemini", "…/v1beta/openai/ (OpenAI-compat)", "GEMINI_API_KEY"],
    ["§B§mock", "in-process, offline", "— (none)"],
], col_widths=[3.8*cm, 7.2*cm, None])
para("The interface is a single method, so a new provider is one small class. The provider layer "
     "also sanitizes keys and makes <b>.env authoritative</b> over stale shell exports.", small)

# 10
section("10", "Tools and the MCP Boundary")
para("The Developer/Tester tools are <b>local, in-process Python functions</b> bound to the "
     "workspace — deliberately not MCP. The inner build loop runs on the same machine, so wrapping "
     "it in an external protocol would only add latency and failure surface.")
para("<b>MCP is reserved for external systems</b> the code must be grounded in — live API docs, a "
     "real database or vector-DB schema, ticketing systems, GitHub, or a staging environment. Such "
     "a capability is added as an extra tool whose handler wraps an MCP client call; the agent loop "
     "treats it identically to a local tool. For typical application logic the swarm needs no "
     "external connection to design, write and test the code.")

# 11
section("11", "Observability & Artifacts")
para("Every phase writes its output to the project's <b>.codeswarm/</b> folder <i>as it completes</i>, "
     "so progress can be inspected (or tailed) during a run, not only at the end. A --verbose flag "
     "also streams requirements, design and acceptance criteria to the console.")
table(["Artifact", "Written after", "Contents"], [
    ["§B§requirements.md / .json", "Phase 1", "Testable functional & non-functional requirements."],
    ["§B§design.md", "Phase 2", "The architecture and module layout the swarm chose."],
    ["§B§plan.md / .json", "Phase 3", "Feature breakdown with acceptance criteria."],
    ["§B§report.json", "every phase", "Requirements, features, per-feature attempts and gate results."],
    ["§B§app/ , tests/", "Phase 4", "The generated source and its test-suite."],
], col_widths=[4.6*cm, 2.6*cm, None])

# 12
section("12", "Configuration")
para("A single YAML file (config/default.yaml) drives everything; CLI flags override it. Key knobs:")
bullets([
    "<b>provider</b> / <b>providers</b> — default provider and each backend's base_url, key env, model.",
    "<b>agents</b> — optional per-role provider / model / temperature overrides.",
    "<b>swarm</b> — max_feature_iterations, developer_max_steps, parallel_features & "
    "max_parallel_features, run_tests, test_timeout_seconds, temperature, output_dir, target_language.",
])

# 13
section("13", "Security & Privacy")
bullets([
    "<b>Secrets stay out of prompts:</b> API keys are used only as the HTTP auth header, never placed "
    "in any message sent to a model. .env is git-ignored and never committed.",
    "<b>Key hygiene:</b> keys are sanitized (whitespace/quotes/Bearer); .env overrides stale shell "
    "exports; auth errors show a masked fingerprint, never the secret.",
    "<b>Generated-code execution:</b> the test sandbox runs generated code in a subprocess with a "
    "timeout. For untrusted specs, run inside a container or disposable VM.",
    "<b>Security gate:</b> a dedicated reviewer inspects each feature for common vulnerability classes.",
])

# 14
section("14", "Alignment with Anthropic Best Practices")
para("CodeSwarm's spine follows Anthropic's published guidance on building effective agents and "
     "multi-agent systems.")
table(["Practice", "Status", "In CodeSwarm"], [
    ["§B§Prompt chaining with gates", "Yes", "requirements → design → plan → build, gated between steps."],
    ["§B§Evaluator–optimizer loop", "Yes", "developer generates; tests + reviewers evaluate and feed back."],
    ["§B§Ground-truth feedback", "Yes", "pytest is really executed as the objective gate."],
    ["§B§Orchestrator–workers", "Yes", "orchestrator delegates features to isolated workers."],
    ["§B§Parallel subagents", "Yes", "independent features build concurrently, then merge."],
    ["§B§Tool-using agent loop", "Yes", "developer/tester inspect, edit and test via tools."],
    ["§B§Independent review", "Yes", "reviewer/security can run on a different model than the writer."],
], col_widths=[5.0*cm, 1.8*cm, None])

# 15
section("15", "Limitations & Future Work")
bullets([
    "Parallel same-file merges are last-writer-wins; a true 3-way merge is future work.",
    "No durable checkpoint/resume yet — a crashed run restarts (state is serializable, so this is tractable).",
    "Python is the only target language wired to the test runner; other languages generate code but skip execution.",
    "Reviewer rubric is prose; explicit multi-dimension rubrics and a performance gate are candidates.",
    "No token-budget accounting; multi-agent runs are token-intensive by nature.",
])

# Appendix A
section("A", "Appendix — Repository Layout")
diagram(
"""codeswarm/
  cli.py         command-line interface (build, doctor)
  config.py      layered configuration loading
  pipeline.py    orchestrator + per-feature quality loop   (core)
  models.py      Feature / ProjectState dataclasses
  workspace.py   guarded file writes + snapshots
  sandbox.py     runs pytest + coverage (objective gate)
  tools.py       local dev/tester tools (read/write/run/coverage)
  utils.py       JSON + file-block parsing
  llm/           provider abstraction + tool-calling
  agents/        specialist roles + prompts
config/default.yaml   examples/   scripts/run_eval.sh   docs/   tests/""")

# Appendix B
section("B", "Appendix — CLI Reference")
table(["Command", "Purpose"], [
    ["§B§codeswarm doctor", "Check config, API key (masked), connectivity, and tool-calling."],
    ["§B§codeswarm build --idea \"…\"", "Build from a one-line idea."],
    ["§B§codeswarm build --spec f.yaml", "Build from a YAML spec."],
    ["§B§  --provider / --model", "Choose backend and model."],
    ["§B§  --sequential / --max-parallel N", "Control feature concurrency."],
    ["§B§  --max-iterations N", "Retry budget per feature."],
    ["§B§  --verbose / -v", "Stream requirements, design, and criteria live."],
    ["§B§  --dry-run", "Offline mock provider (no API key)."],
], col_widths=[6.2*cm, None])
story.append(Spacer(1, 10))
para("© 2026 Ankur Srivastava · CodeSwarm is released under the MIT License. "
     "This document describes the design as implemented at version 0.2.0 (draft).", small)


# ===========================================================================
# PAGE TEMPLATES
# ===========================================================================

def draw_cover(canvas, doc):
    w, h = A4
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, h - 8.6 * cm, w, 8.6 * cm, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, h - 8.85 * cm, w, 0.25 * cm, fill=1, stroke=0)
    # title
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 40)
    canvas.drawString(2.2 * cm, h - 4.2 * cm, TITLE)
    canvas.setFont("Helvetica", 17)
    canvas.drawString(2.2 * cm, h - 5.3 * cm, SUBTITLE)
    canvas.setFont("Helvetica-Oblique", 10.5)
    canvas.setFillColor(HexColor("#C9D6E0"))
    canvas.drawString(2.2 * cm, h - 6.2 * cm,
                      "A provider-agnostic swarm of LLM agents that builds, tests, and reviews software.")
    # meta box
    y = h - 11.0 * cm
    canvas.setFillColor(INK)
    for label, value in META:
        canvas.setFont("Helvetica-Bold", 10)
        canvas.setFillColor(TEAL)
        canvas.drawString(2.2 * cm, y, f"{label}")
        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(INK)
        canvas.drawString(5.4 * cm, y, value)
        y -= 0.72 * cm
    # footer rule
    canvas.setStrokeColor(GRID)
    canvas.line(2.2 * cm, 2.2 * cm, w - 2.2 * cm, 2.2 * cm)
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(2.2 * cm, 1.7 * cm, "CodeSwarm — Solution Design Document")
    canvas.drawRightString(w - 2.2 * cm, 1.7 * cm, "Confidential · Internal")
    canvas.restoreState()


def draw_footer(canvas, doc):
    w, h = A4
    canvas.saveState()
    canvas.setStrokeColor(GRID)
    canvas.line(2.0 * cm, 1.5 * cm, w - 2.0 * cm, 1.5 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(2.0 * cm, 1.1 * cm, "CodeSwarm — Solution Design")
    canvas.drawRightString(w - 2.0 * cm, 1.1 * cm, f"Page {doc.page - 1}")
    canvas.restoreState()


frame_cover = Frame(0, 0, A4[0], A4[1], id="cover")
frame_body = Frame(2.0 * cm, 2.0 * cm, A4[0] - 4.0 * cm, A4[1] - 4.0 * cm, id="body")

doc = BaseDocTemplate(OUT, pagesize=A4,
                      pageTemplates=[
                          PageTemplate(id="cover", frames=[frame_cover], onPage=draw_cover),
                          PageTemplate(id="body", frames=[frame_body], onPage=draw_footer),
                      ])
doc.build(story)
print("WROTE", OUT)
