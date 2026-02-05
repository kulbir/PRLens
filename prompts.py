"""Prompt templates for code analysis."""

REVIEW_PROMPT = """Review this Python code for: bugs, security, performance, PEP8.
Be concise. Use format: 🐛Bugs 🔒Security ⚡Perf 📐PEP8 💡Fix

```python
{code}
```"""

