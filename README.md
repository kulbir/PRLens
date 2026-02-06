# PRLens 🔍

An AI-powered Pull Request review agent that automatically analyzes code changes and posts feedback on GitHub.

## What It Does

When a PR is created, PRLens:
1. **Fetches** the PR diff from GitHub
2. **Analyzes** code changes using Google Gemini AI
3. **Decides** if there are issues worth reporting
4. **Posts** review comments directly on the PR

```
PR Created → Fetch Diff → AI Analysis → Post Comments (if issues found)
```

## Architecture

PRLens uses **LangGraph** to orchestrate the review workflow as a state machine:

```
START → fetch_pr_data → analyze_code → [has issues?]
                                            │
                                  ┌─────────┴─────────┐
                                  │                   │
                                 YES                  NO
                                  │                   │
                            post_review              END
                                  │
                                 END
```

## Project Structure

```
PRLens/
├── agent.py          # LangGraph workflow (State, Nodes, Edges)
├── github_client.py  # GitHub API (fetch PRs, post comments)
├── diff_parser.py    # Parse unified diffs
├── main.py           # Gemini AI code analysis
├── models.py         # Data models (Finding, ReviewResult)
├── prompts.py        # AI prompts for code review
└── .env              # API keys (GITHUB_TOKEN, GEMINI_API_KEY)
```

## Setup

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Configure API keys** in `.env`:
   ```
   GITHUB_TOKEN=ghp_your_token_here
   GEMINI_API_KEY=your_gemini_key_here
   ```

3. **Run the agent:**
   ```bash
   uv run python agent.py
   ```

## Tech Stack

- **Python 3.12+**
- **LangGraph** — Workflow orchestration
- **Google Gemini** — AI code analysis
- **PyGithub** — GitHub API client
- **Pydantic** — Data validation

## License

MIT

