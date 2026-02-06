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
    
    # AI analysis results
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
        "findings": all_findings,
        "summary": summary,
    }


# =============================================================================
# GRAPH CONSTRUCTION
# =============================================================================

def build_review_graph() -> StateGraph:
    """
    Build the review workflow graph.
    
    Current flow (minimal):
        START → fetch_pr_data → analyze_code → END
    
    Future flow (full):
        START → fetch_pr_data → analyze_code → post_review → END
                                     ↓
                              (if no findings)
                                     ↓
                                   END
    """
    # Create the graph with our state type
    graph = StateGraph(ReviewState)
    
    # Add nodes (the functions that do work)
    graph.add_node("fetch_pr_data", fetch_pr_data)
    graph.add_node("analyze_code", analyze_code)
    
    # Add edges (the flow between nodes)
    graph.add_edge(START, "fetch_pr_data")      # Start → Node 1
    graph.add_edge("fetch_pr_data", "analyze_code")  # Node 1 → Node 2
    graph.add_edge("analyze_code", END)         # Node 2 → End
    
    return graph


def create_agent():
    """Create and compile the review agent."""
    graph = build_review_graph()
    return graph.compile()


# =============================================================================
# MAIN - Test the minimal graph
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 PRLens Agent - LangGraph Review Agent")
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
    print("Running graph...")
    print("-" * 60 + "\n")
    
    # Run the graph
    final_state = agent.invoke(initial_state)
    
    print("\n" + "-" * 60)
    print("Graph complete!")
    print("-" * 60)
    
    # Final state is returned as a dict by LangGraph
    print("\n📋 Final State:")
    files = final_state.get("files_to_review", [])
    findings = final_state.get("findings", [])
    summary = final_state.get("summary", "")
    error = final_state.get("error")
    
    print(f"   files_to_review: {len(files)} file(s)")
    print(f"   findings: {len(findings)} found")
    print(f"   summary: {summary}")
    
    if error:
        print(f"\n❌ Error: {error}")
    
    if findings:
        print("\n🔍 Findings:")
        for i, finding in enumerate(findings, 1):
            # Handle both Finding objects and dicts
            if hasattr(finding, 'severity'):
                print(f"   {i}. [{finding.severity}] Line {finding.line}: {finding.description}")
            else:
                print(f"   {i}. [{finding['severity']}] Line {finding['line']}: {finding['description']}")

