"""Mock responses for testing without API calls."""

# Actual response from Gemini API (2026-02-05)
MOCK_RESPONSE = """```json
{
  "findings": [
    {
      "severity": "MEDIUM",
      "category": "bug",
      "line": 3,
      "description": "The `calculate_average` function will raise a `ZeroDivisionError` if an empty list is passed as input, as `len(numbers)` will be 0.",
      "fix": "Add a check for an empty list and return 0 or raise a more specific error if appropriate."
    }
  ],
  "summary": "The `calculate_average` function lacks error handling for empty input lists."
}
```"""