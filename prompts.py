"""Prompt templates for code analysis."""

REVIEW_PROMPT = """Review this Python code. Return ONLY valid JSON, no markdown.

```python
{code}
```

Output format:
{{
  "findings": [
    {{
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "category": "bug|security|performance|pep8",
      "line": <line_number or null>,
      "description": "<what is wrong>",
      "fix": "<code fix or suggestion>"
    }}
  ],
  "summary": "<one line summary>"
}}"""

