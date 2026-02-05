"""Prompt templates for code analysis."""

REVIEW_PROMPT = """Review this Python code for bugs, security, performance, and PEP8.

```python
{code}
```

Respond with ONLY valid JSON. No markdown, no explanation, no extra text.

Required format:
{{"findings":[{{"severity":"CRITICAL|HIGH|MEDIUM|LOW","category":"bug|security|performance|pep8","line":1,"description":"issue","fix":"solution"}}],"summary":"one line"}}

Example:
{{"findings":[{{"severity":"HIGH","category":"bug","line":3,"description":"ZeroDivisionError if list empty","fix":"if not nums: return 0"}}],"summary":"1 bug found"}}"""

