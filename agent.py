"""
PRLens Agent - LangGraph-based PR Review Agent

This module implements the review workflow as a state machine using LangGraph.
"""

import logging
from dataclasses import dataclass, field
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END

# Import our existing modules
from github_client import (
    fetch_raw_diff,
    post_review,
    ReviewComment,
    ReviewSubmission,
)
from diff_parser import (
    parse_diff,
    filter_files,
    get_review_content,
    build_line_mapping,
    FileDiff,
)
from models import ReviewResult, Finding

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
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
    repo: str                                    # e.g., "kulbir/PRLens"
    pr_number: int                               # e.g., 1
    
    # Intermediate data (populated by nodes)
    diff: str = ""                               # Raw diff content
    files_to_review: list[FileDiff] = field(default_factory=list)
    
    # Results from specialized reviewers (each reviewer writes to its own field)
    security_findings: list[Finding] = field(default_factory=list)  # From security_reviewer
    quality_findings: list[Finding] = field(default_factory=list)   # From quality_reviewer
    general_findings: list[Finding] = field(default_factory=list)   # From general_reviewer
    
    # Merged AI analysis results (populated by merge_findings node)
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""
    
    # Output
    review_posted: bool = False                  # Whether we posted to GitHub
    review_id: int | None = None                 # GitHub review ID if posted
    error: str | None = None                     # Error message if something failed


# =============================================================================
# NODE FUNCTIONS
# =============================================================================

def fetch_pr_data(state: ReviewState) -> dict:
    """
    Node 1: Fetch PR diff from GitHub.
    
    This node reads: repo, pr_number
    This node updates: diff, files_to_review, error
    """
    repo = state.repo
    pr_number = state.pr_number
    
    logger.info(f"📥 Fetching PR #{pr_number} from {repo}...")
    
    try:
        # Fetch the raw diff from GitHub
        raw_diff = fetch_raw_diff(repo, pr_number)
        
        # Parse and filter files
        all_files = parse_diff(raw_diff)
        files_to_review = filter_files(all_files)
        
        logger.info(f"   Found {len(all_files)} files, {len(files_to_review)} to review")
        
        return {
            "diff": raw_diff,
            "files_to_review": files_to_review,
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch PR: {e}")
        return {
            "error": str(e),
            "diff": "",
            "files_to_review": [],
        }


def analyze_code(state: ReviewState) -> dict:
    """
    Node 2: Analyze the code with AI and produce findings.
    
    This node reads: files_to_review
    This node updates: findings, summary, error
    """
    files = state.files_to_review
    
    # Skip if previous node failed
    if state.error:
        logger.warning("Skipping analysis due to previous error")
        return {}
    
    if not files:
        logger.info("No files to review")
        return {
            "findings": [],
            "summary": "No code changes to review.",
        }
    
    logger.info(f"🔍 Analyzing {len(files)} file(s)...")
    
    # Import here to avoid circular imports
    from main import analyze_code as ai_analyze
    
    all_findings: list[Finding] = []
    
    for file in files:
        logger.info(f"   Reviewing: {file.filename}")
        
        # Get the code content for this file
        review_content = get_review_content(file)
        code = review_content["code"]
        
        if not code.strip():
            continue
        
        try:
            # Call the AI to analyze this file
            result = ai_analyze(code)
            
            if result and result.findings:
                # Add filename to each finding for context
                for finding in result.findings:
                    # Store the path with the finding for later use
                    finding_dict = finding.model_dump()
                    finding_dict["path"] = file.filename
                    all_findings.append(Finding(**{k: v for k, v in finding_dict.items() if k != "path"}))
                    # We'll handle path separately when posting
                    
        except Exception as e:
            logger.warning(f"   Failed to analyze {file.filename}: {e}")
    
    # Generate summary
    if all_findings:
        summary = f"Found {len(all_findings)} issue(s) across {len(files)} file(s)."
    else:
        summary = "No issues found. Code looks good! ✨"
    
    logger.info(f"   {summary}")
    
    return {
        "general_findings": all_findings,  # Changed: write to general_findings
    }


# =============================================================================
# SPECIALIZED REVIEWER NODES
# =============================================================================

def security_reviewer(state: ReviewState) -> dict:
    """
    Security Reviewer Node: Focuses ONLY on security vulnerabilities.
    
    Reads: files_to_review
    Writes: security_findings
    """
    from reviewer import security_review
    
    files = state.files_to_review
    
    if state.error or not files:
        return {"security_findings": []}
    
    logger.info(f"🔒 Security Reviewer: Analyzing {len(files)} file(s)...")
    
    all_findings: list[Finding] = []
    
    for file in files:
        review_content = get_review_content(file)
        code = review_content["code"]
        
        if not code.strip():
            continue
        
        try:
            result = security_review(code, file.filename)
            if result and result.findings:
                all_findings.extend(result.findings)
        except Exception as e:
            logger.warning(f"   Security review failed for {file.filename}: {e}")
    
    logger.info(f"   🔒 Found {len(all_findings)} security issue(s)")
    
    return {"security_findings": all_findings}


def quality_reviewer(state: ReviewState) -> dict:
    """
    Quality Reviewer Node: Focuses ONLY on code quality/maintainability.
    
    Reads: files_to_review
    Writes: quality_findings
    """
    from reviewer import quality_review
    
    files = state.files_to_review
    
    if state.error or not files:
        return {"quality_findings": []}
    
    logger.info(f"📐 Quality Reviewer: Analyzing {len(files)} file(s)...")
    
    all_findings: list[Finding] = []
    
    for file in files:
        review_content = get_review_content(file)
        code = review_content["code"]
        
        if not code.strip():
            continue
        
        try:
            result = quality_review(code, file.filename)
            if result and result.findings:
                all_findings.extend(result.findings)
        except Exception as e:
            logger.warning(f"   Quality review failed for {file.filename}: {e}")
    
    logger.info(f"   📐 Found {len(all_findings)} quality issue(s)")
    
    return {"quality_findings": all_findings}


def general_reviewer(state: ReviewState) -> dict:
    """
    General Reviewer Node: Catches bugs, performance, and style issues.
    
    This is a renamed version of analyze_code that writes to general_findings.
    
    Reads: files_to_review
    Writes: general_findings
    """
    # Reuse the existing analyze_code logic
    return analyze_code(state)


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
        list(state.security_findings) +
        list(state.quality_findings) +
        list(state.general_findings)
    )
    
    # Simple deduplication: remove findings with same line and similar description
    seen = set()
    unique_findings = []
    
    for finding in all_findings:
        key = (finding.line, finding.description[:50] if finding.description else "")
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
    
    summary_parts = []
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
    
    logger.info(f"   {summary}")
    
    return {
        "findings": unique_findings,
        "summary": summary,
    }


def post_review_node(state: ReviewState) -> dict:
    """
    Node 3: Post review comments to GitHub.
    
    This node reads: repo, pr_number, findings, summary
    This node updates: review_posted, review_id, error
    """
    logger.info("📝 Posting review to GitHub...")
    
    try:
        # Build review comments from findings
        # Note: For now we post summary only, since findings don't have file path
        review = ReviewSubmission(
            body=f"## 🤖 PRLens Review\n\n{state.summary}",
            event="COMMENT",
            comments=[],  # We'll add inline comments later when we track file paths
        )
        
        review_id = post_review(state.repo, state.pr_number, review)
        
        logger.info(f"   ✅ Posted review #{review_id}")
        
        return {
            "review_posted": True,
            "review_id": review_id,
        }
        
    except Exception as e:
        logger.error(f"   ❌ Failed to post review: {e}")
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
    
    This is called by LangGraph after analyze_code to determine the next node.
    
    Returns:
        "post_review" if there are findings
        "end" if no findings (code looks good)
    """
    findings = state.get("findings", []) if isinstance(state, dict) else state.findings
    
    if findings and len(findings) > 0:
        logger.info(f"🔀 Decision: {len(findings)} issues found → posting review")
        return "post_review"
    else:
        logger.info("🔀 Decision: No issues found → ending")
        return "end"


# =============================================================================
# GRAPH CONSTRUCTION
# =============================================================================

def build_review_graph() -> StateGraph:
    """
    Build the review workflow graph with PARALLEL reviewers.
    
    Flow:
        START → fetch_pr_data → [PARALLEL REVIEWERS] → merge_findings → [DECISION]
                                       │                                    │
                        ┌──────────────┼──────────────┐         ┌───────────┴───────────┐
                        │              │              │         │                       │
                        ▼              ▼              ▼    (has issues)           (no issues)
                   security       quality        general        │                       │
                   reviewer       reviewer       reviewer       ▼                       ▼
                        │              │              │    post_review                 END
                        └──────────────┼──────────────┘         │
                                       │                        ▼
                                       ▼                       END
                                merge_findings
    """
    # Create the graph with our state type
    graph = StateGraph(ReviewState)
    
    # Add nodes (the functions that do work)
    graph.add_node("fetch_pr_data", fetch_pr_data)
    
    # Specialized reviewers (will run in parallel)
    graph.add_node("security_reviewer", security_reviewer)
    graph.add_node("quality_reviewer", quality_reviewer)
    graph.add_node("general_reviewer", general_reviewer)
    
    # Merge findings from all reviewers
    graph.add_node("merge_findings", merge_findings)
    
    # Post review
    graph.add_node("post_review", post_review_node)
    
    # =========================================================================
    # EDGES: Define the flow
    # =========================================================================
    
    # Start → fetch
    graph.add_edge(START, "fetch_pr_data")
    
    # fetch → ALL reviewers (parallel execution)
    # When a node has multiple outgoing edges, LangGraph runs them in parallel
    graph.add_edge("fetch_pr_data", "security_reviewer")
    graph.add_edge("fetch_pr_data", "quality_reviewer")
    graph.add_edge("fetch_pr_data", "general_reviewer")
    
    # ALL reviewers → merge (waits for all to complete)
    graph.add_edge("security_reviewer", "merge_findings")
    graph.add_edge("quality_reviewer", "merge_findings")
    graph.add_edge("general_reviewer", "merge_findings")
    
    # Conditional edge: after merge, decide what to do
    graph.add_conditional_edges(
        "merge_findings",    # From this node...
        should_post_review,  # Run this function to decide...
        {                    # Map return values to next nodes:
            "post_review": "post_review",  # If has issues → post review
            "end": END,                     # If no issues → end
        }
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
    print(f"\n   📊 Findings by Reviewer:")
    print(f"      🔒 Security: {len(security_findings)}")
    print(f"      📐 Quality:  {len(quality_findings)}")
    print(f"      🔍 General:  {len(general_findings)}")
    print(f"      ─────────────────")
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
            if hasattr(finding, 'severity'):
                sev = finding.severity
                line = finding.line
                desc = finding.description
                cat = finding.category
            else:
                sev = finding['severity']
                line = finding['line']
                desc = finding['description']
                cat = finding.get('category', '?')
            
            icon = {"security": "🔒", "quality": "📐"}.get(cat, "🔍")
            print(f"   {i}. {icon} [{sev}] Line {line}: {desc[:60]}...")
        
        if len(merged_findings) > 10:
            print(f"\n   ... and {len(merged_findings) - 10} more findings")

