# PRLens 🔍

An AI-powered Pull Request review agent that automatically analyzes code changes and posts feedback on GitHub.

## What It Does

When a PR is created, PRLens:
1. **Fetches** the PR diff from GitHub
2. **Analyzes** code changes with three specialised AI reviewers running in parallel
3. **Merges & deduplicates** findings across reviewers
4. **Posts** a review directly on the PR (if issues are found)

## Architecture

PRLens uses **LangGraph** to orchestrate the review workflow as a state machine with parallel execution:

```
                         ┌──────────────┐
                         │    START     │
                         └──────┬───────┘
                                ▼
                       ┌────────────────┐
                       │ fetch_pr_data  │
                       └───┬────┬────┬──┘
                           │    │    │        ← parallel fan-out
                ┌──────────┘    │    └──────────┐
                ▼               ▼               ▼
        ┌──────────────┐ ┌────────────┐ ┌──────────────┐
        │   security   │ │  quality   │ │   general    │
        │   reviewer   │ │  reviewer  │ │   reviewer   │
        └──────┬───────┘ └─────┬──────┘ └──────┬───────┘
               └───────────────┼───────────────┘
                               ▼              ← join
                      ┌────────────────┐
                      │ merge_findings │
                      └───────┬────────┘
                              ▼
                       has issues?
                      ╱            ╲
                    YES             NO
                     ▼               ▼
              ┌─────────────┐    ┌───────┐
              │ post_review │    │  END  │
              └──────┬──────┘    └───────┘
                     ▼
                  ┌───────┐
                  │  END  │
                  └───────┘
```

## Project Structure

```
PRLens/
├── agent.py              # LangGraph workflow (state, nodes, edges)
├── config.py             # Shared config, cached clients, retry, JSON parsing
├── github_client.py      # GitHub API (fetch PRs, post reviews)
├── diff_parser.py        # Parse unified diffs, filter files
├── reviewer.py           # Gemini-powered code review (general, security, quality)
├── main.py               # Simple CLI entry point for quick analysis
├── models.py             # Pydantic models (Finding, ReviewResult)
├── prompts.py            # Prompt templates for each reviewer
├── mock_data.py          # Mock responses for offline testing
├── pyproject.toml        # Dependencies & tool config
└── .env                  # API keys (GITHUB_TOKEN, GEMINI_API_KEY)
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

4. **Install pre-commit hooks** (optional):
   ```bash
   uv run pre-commit install
   ```

## Tech Stack

- **Python 3.12+**
- **LangGraph** — Workflow orchestration with parallel execution
- **Google Gemini** — AI code analysis (security, quality, general)
- **PyGithub** — GitHub API client
- **Pydantic** — Data validation
- **Ruff** — Linting & formatting

## License

MIT

