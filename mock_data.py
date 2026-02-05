"""Mock responses for testing without API calls."""

MOCK_RESPONSE = """
Gemini's Response:
🐛 **Bugs:** `ZeroDivisionError` if `numbers` is empty.
🔒 **Security:** No direct security vulnerabilities.
⚡ **Perf:** Efficient for its purpose, but could be slightly optimized if performance is critical for very large lists by avoiding the intermediate `total` variable (though `sum` is highly optimized).
📐 **PEP8:** Good. Function name is descriptive and follows snake_case.

💡 **Fix:**

```python
def calculate_average(numbers):
    if not numbers:
        return 0  # Or raise an error, depending on desired behavior for empty lists
    total = sum(numbers)
    return total / len(numbers)
```
"""