"""Mock responses for testing without API calls."""

# Based on actual Gemini API response (2026-02-05)
MOCK_RESPONSE = """{
  "findings": [
    {
      "severity": "LOW",
      "category": "bug",
      "line": 3,
      "description": "ZeroDivisionError if list is empty",
      "fix": "if not numbers: return 0"
    },
    {
      "severity": "LOW",
      "category": "style",
      "line": 1,
      "description": "Missing module docstring",
      "fix": "Add module docstring at top of file"
    },
    {
      "severity": "LOW",
      "category": "style",
      "line": 2,
      "description": "Missing function docstring",
      "fix": "Add docstring: Calculate the average of a list of numbers."
    }
  ],
  "summary": "3 issues found"
}"""
