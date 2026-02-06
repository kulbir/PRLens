"""
PRLens Agent - LangGraph-based PR Review Agent

This module implements the review workflow as a state machine using LangGraph.
Three specialised reviewers (security, quality, general) run in parallel,
their findings are merged and deduplicated, then optionally posted to GitHub.
"""

import logging
from dataclasses import dataclass, field

from langgraph.graph import END, START, StateGraph

import config as _config  # noqa: F401 — ensures env & logging are initialised
from diff_parser import (
    FileDiff,
    filter_files,
    get_review_content,
    parse_diff,
)
from github_client import (
    ReviewSubmission,
    fetch_raw_diff,
    post_review,
)
from models import Finding

logger = logging.getLogger(__name__)


# =============================================================================
# STATE DEFINITION
# =============================================================================
@dataclass
class ReviewState:
    """
    State that flows through the review graph.

    Each node can read any field and return updates to specific fields.
    LangGraph automatically merges the updates into the state.
    """

    # Input (required)
    repo: str  # e.g., "kulbir/PRLens"
    pr_number: int  # e.g., 1

    # Intermediate data (populated by nodes)
    diff: str = ""  # Raw diff content
    files_to_review: list[FileDiff] = field(default_factory=list)

    # Results from specialised reviewers (each reviewer writes to its own field)
    security_findings: list[Finding] = field(default_factory=list)
    quality_findings: list[Finding] = field(default_factory=list)
    general_findings: list[Finding] = field(default_factory=list)

    # Merged AI analysis results (populated by merge_findings node)
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""

    # Output
    review_posted: bool = False  # Whether we posted to GitHub
    review_id: int | None = None  # GitHub review ID if posted
    error: str | None = None  # Error message if something failed


# =============================================================================
# NODE FUNCTIONS
# =============================================================================
def fetch_pr_data(state: ReviewState) -> dict:
    """
    Node 1: Fetch PR diff from GitHub.

    Reads: repo, pr_number
    Updates: diff, files_to_review, error
    """
    repo = state.repo
    pr_number = state.pr_number

    logger.info("📥 Fetching PR #%d from %s...", pr_number, repo)

    try:
        raw_diff = fetch_raw_diff(repo, pr_number)
        all_files = parse_diff(raw_diff)
        files_to_review = filter_files(all_files)

        logger.info(
            "   Found %d files, %d to review",
            len(all_files),
            len(files_to_review),
        )

        return {
            "diff": raw_diff,
            "files_to_review": files_to_review,
        }

    except Exception as e:
        logger.error("Failed to fetch PR: %s", e)
        return {
            "error": str(e),
            "diff": "",
            "files_to_review": [],
        }


# ---------------------------------------------------------------------------
# Generic reviewer helper
# ---------------------------------------------------------------------------
def _run_reviewer(
    state: ReviewState,
    review_fn,
    findings_key: str,
    label: str,
) -> dict:
    """
    Run *review_fn* over every reviewable file and collect findings.

    Args:
        state: Current graph state
        review_fn: Callable(code: str, filename: str) -> ReviewResult | None
        findings_key: State key to write the results to
        label: Emoji / text prefix used in log messages
    """
    files = state.files_to_review

    if state.error or not files:
        return {findings_key: []}

    logger.info("%s Analysing %d file(s)...", label, len(files))

    all_findings: list[Finding] = []

    for file in files:
        review_content = get_review_content(file)
        code = review_content["code"]

        if not code.strip():
            continue

        try:
            result = review_fn(code, file.filename)
            if result and result.findings:
                for finding in result.findings:
                    finding.path = file.filename
                all_findings.extend(result.findings)
        except Exception as e:
            logger.warning("   %s failed for %s: %s", label, file.filename, e)

    logger.info("   %s Found %d issue(s)", label, len(all_findings))
    return {findings_key: all_findings}


# =============================================================================
# SPECIALISED REVIEWER NODES
# =============================================================================
def security_reviewer(state: ReviewState) -> dict:
    """
    Security Reviewer Node: Focuses ONLY on security vulnerabilities.

    Reads: files_to_review
    Writes: security_findings
    """
    from reviewer import security_review

    return _run_reviewer(state, security_review, "security_findings", "🔒")


def quality_reviewer(state: ReviewState) -> dict:
    """
    Quality Reviewer Node: Focuses ONLY on code quality / maintainability.

    Reads: files_to_review
    Writes: quality_findings
    """
    from reviewer import quality_review

    return _run_reviewer(state, quality_review, "quality_findings", "📐")


def general_reviewer(state: ReviewState) -> dict:
    """
    General Reviewer Node: Catches bugs, performance, and style issues.

    Reads: files_to_review
    Writes: general_findings
    """
    from reviewer import analyze_code

    return _run_reviewer(state, analyze_code, "general_findings", "🔍")


# =============================================================================
# MERGE NODE
# =============================================================================
def merge_findings(state: ReviewState) -> dict:
    """
    Merge Node: Combines findings from all reviewers.

    Reads: security_findings, quality_findings, general_findings
    Writes: findings, summary

    This node:
    1. Combines all findings
    2. Removes duplicates (same line + similar description)
    3. Sorts by severity
    """
    logger.info("🔀 Merging findings from all reviewers...")

    # Combine all findings
    all_findings = (
        list(state.security_findings)
        + list(state.quality_findings)
        + list(state.general_findings)
    )

    # Simple deduplication: remove findings with same line and similar description
    seen: set[tuple[int | None, str]] = set()
    unique_findings: list[Finding] = []

    for finding in all_findings:
        key = (
            finding.line,
            finding.description[:50] if finding.description else "",
        )
        if key not in seen:
            seen.add(key)
            unique_findings.append(finding)

    # Sort by severity (CRITICAL > HIGH > MEDIUM > LOW)
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    unique_findings.sort(key=lambda f: severity_order.get(f.severity, 4))

    # Generate summary
    security_count = len(state.security_findings)
    quality_count = len(state.quality_findings)
    general_count = len(state.general_findings)

    summary_parts: list[str] = []
    if security_count:
        summary_parts.append(f"🔒 {security_count} security")
    if quality_count:
        summary_parts.append(f"📐 {quality_count} quality")
    if general_count:
        summary_parts.append(f"🔍 {general_count} general")

    if unique_findings:
        summary = f"Found {len(unique_findings)} issue(s): " + ", ".join(summary_parts)
    else:
        summary = "No issues found. Code looks good! ✨"

    logger.info("   %s", summary)

    return {
        "findings": unique_findings,
        "summary": summary,
    }


# =============================================================================
# FORMATTING & POSTING
# =============================================================================
def format_findings_markdown(state: ReviewState) -> str:
    """Format all findings as a detailed markdown report."""
    lines: list[str] = []
    lines.append("## 🤖 PRLens Review\n")
    lines.append(f"**{state.summary}**\n")

    # Security findings
    if state.security_findings:
        lines.append("\n### 🔒 Security Issues\n")
        lines.append("| Severity | File | Line | Issue | Fix |")
        lines.append("|----------|------|------|-------|-----|")
        for f in state.security_findings:
            desc = (
                (f.description[:60] + "...")
                if len(f.description) > 60
                else f.description
            )
            fix = (f.fix[:40] + "...") if f.fix and len(f.fix) > 40 else (f.fix or "-")
            path = f.path or "-"
            lines.append(
                f"| **{f.severity}** | {path} | {f.line or '-'} | {desc} | {fix} |"
            )

    # Quality findings
    if state.quality_findings:
        lines.append("\n### 📐 Quality Issues\n")
        lines.append("| Severity | File | Line | Issue | Fix |")
        lines.append("|----------|------|------|-------|-----|")
        for f in state.quality_findings:
            desc = (
                (f.description[:60] + "...")
                if len(f.description) > 60
                else f.description
            )
            fix = (f.fix[:40] + "...") if f.fix and len(f.fix) > 40 else (f.fix or "-")
            path = f.path or "-"
            lines.append(
                f"| {f.severity} | {path} | {f.line or '-'} | {desc} | {fix} |"
            )

    # General findings
    if state.general_findings:
        lines.append("\n### 🔍 General Issues (Bugs, Performance, Style)\n")
        lines.append("| Severity | File | Line | Category | Issue |")
        lines.append("|----------|------|------|----------|-------|")
        for f in state.general_findings:
            desc = (
                (f.description[:60] + "...")
                if len(f.description) > 60
                else f.description
            )
            path = f.path or "-"
            lines.append(
                f"| {f.severity} | {path} | {f.line or '-'} | {f.category} | {desc} |"
            )

    lines.append("\n---")
    lines.append("*Generated by [PRLens](https://github.com/kulbir/PRLens) 🤖*")

    return "\n".join(lines)


def post_review_node(state: ReviewState) -> dict:
    """
    Node 3: Post review comments to GitHub.

    Reads: repo, pr_number, findings, summary, *_findings
    Updates: review_posted, review_id, error
    """
    logger.info("📝 Posting review to GitHub...")

    try:
        review_body = format_findings_markdown(state)

        review = ReviewSubmission(
            body=review_body,
            event="COMMENT",
            comments=[],  # Inline comments can be added later
        )

        review_id = post_review(state.repo, state.pr_number, review)

        logger.info("   ✅ Posted review #%d", review_id)

        return {
            "review_posted": True,
            "review_id": review_id,
        }

    except Exception as e:
        logger.error("   ❌ Failed to post review: %s", e)
        return {
            "review_posted": False,
            "error": str(e),
        }


# =============================================================================
# DECISION FUNCTIONS (for conditional edges)
# =============================================================================
def should_post_review(state: ReviewState) -> str:
    """
    Decide whether to post a review or end.

    Returns:
        "post_review" if there are findings
        "end" if no findings (code looks good)
    """
    # Defensive: LangGraph may pass state as dict or dataclass
    findings = state.get("findings", []) if isinstance(state, dict) else state.findings

    if findings:
        logger.info("🔀 Decision: %d issues found → posting review", len(findings))
        return "post_review"

    logger.info("🔀 Decision: No issues found → ending")
    return "end"


# =============================================================================
# GRAPH CONSTRUCTION
# =============================================================================
def build_review_graph() -> StateGraph:
    """Build the review workflow graph with PARALLEL reviewers."""
    graph = StateGraph(ReviewState)

    # Add nodes
    graph.add_node("fetch_pr_data", fetch_pr_data)
    graph.add_node("security_reviewer", security_reviewer)
    graph.add_node("quality_reviewer", quality_reviewer)
    graph.add_node("general_reviewer", general_reviewer)
    graph.add_node("merge_findings", merge_findings)
    graph.add_node("post_review", post_review_node)

    # Edges
    graph.add_edge(START, "fetch_pr_data")

    # fetch → ALL reviewers (parallel execution)
    graph.add_edge("fetch_pr_data", "security_reviewer")
    graph.add_edge("fetch_pr_data", "quality_reviewer")
    graph.add_edge("fetch_pr_data", "general_reviewer")

    # ALL reviewers → merge (waits for all to complete)
    graph.add_edge("security_reviewer", "merge_findings")
    graph.add_edge("quality_reviewer", "merge_findings")
    graph.add_edge("general_reviewer", "merge_findings")

    # Conditional edge: after merge, decide what to do
    graph.add_conditional_edges(
        "merge_findings",
        should_post_review,
        {
            "post_review": "post_review",
            "end": END,
        },
    )

    # After posting review, we're done
    graph.add_edge("post_review", END)

    return graph


def create_agent():
    """Create and compile the review agent."""
    graph = build_review_graph()
    return graph.compile()


# =============================================================================
# MAIN - Test the multi-reviewer graph
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 PRLens Agent - Multi-Reviewer LangGraph Agent")
    print("=" * 60)

    # Create the agent
    agent = create_agent()

    # Define initial state using the dataclass
    initial_state = ReviewState(
        repo="kulbir/PRLens",
        pr_number=1,
    )

    print("\n📋 Initial State:")
    print(f"   repo: {initial_state.repo}")
    print(f"   pr_number: {initial_state.pr_number}")

    print("\n" + "-" * 60)
    print("Running graph with 3 parallel reviewers...")
    print("-" * 60 + "\n")

    # Run the graph
    final_state = agent.invoke(initial_state)

    print("\n" + "-" * 60)
    print("Graph complete!")
    print("-" * 60)

    # Final state is returned as a dict by LangGraph
    print("\n📋 Final State:")
    files = final_state.get("files_to_review", [])
    security_findings = final_state.get("security_findings", [])
    quality_findings = final_state.get("quality_findings", [])
    general_findings = final_state.get("general_findings", [])
    merged_findings = final_state.get("findings", [])
    summary = final_state.get("summary", "")
    error = final_state.get("error")
    review_posted = final_state.get("review_posted", False)
    review_id = final_state.get("review_id")

    print(f"   files_to_review: {len(files)} file(s)")
    print("\n   📊 Findings by Reviewer:")
    print(f"      🔒 Security: {len(security_findings)}")
    print(f"      📐 Quality:  {len(quality_findings)}")
    print(f"      🔍 General:  {len(general_findings)}")
    print("      ─────────────────")
    print(f"      📋 Merged:   {len(merged_findings)} (after dedup)")

    print(f"\n   summary: {summary}")
    print(f"   review_posted: {review_posted}")
    if review_id:
        print(f"   review_id: {review_id}")

    if error:
        print(f"\n❌ Error: {error}")

    if merged_findings:
        print("\n🔍 Top Findings (first 10):")
        for i, finding in enumerate(merged_findings[:10], 1):
            # Handle both Finding objects and dicts
            if hasattr(finding, "severity"):
                sev = finding.severity
                line = finding.line
                desc = finding.description
                cat = finding.category
            else:
                sev = finding["severity"]
                line = finding["line"]
                desc = finding["description"]
                cat = finding.get("category", "?")

            icon = {"security": "🔒", "quality": "📐"}.get(cat, "🔍")
            print(f"   {i}. {icon} [{sev}] Line {line}: {desc[:60]}...")

        if len(merged_findings) > 10:
            print(f"\n   ... and {len(merged_findings) - 10} more findings")
