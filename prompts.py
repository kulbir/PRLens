"""Prompt templates for code analysis."""

# =============================================================================
# GENERAL REVIEWER - Catches bugs, performance, style issues
# =============================================================================

REVIEW_PROMPT = """Review this Python code for bugs, security, performance, and PEP8.

```python
{code}
```

Respond with ONLY valid JSON. No markdown, no explanation, no extra text.

Required format:
{{"findings":[{{"severity":"CRITICAL|HIGH|MEDIUM|LOW","category":"bug|security|performance|pep8","line":1,"description":"issue","fix":"solution"}}],"summary":"one line"}}

Example:
{{"findings":[{{"severity":"HIGH","category":"bug","line":3,"description":"ZeroDivisionError if list empty","fix":"if not nums: return 0"}}],"summary":"1 bug found"}}"""


# =============================================================================
# SECURITY REVIEWER - Focused ONLY on security vulnerabilities
# =============================================================================

SECURITY_PROMPT = """You are a SECURITY EXPERT. Review this code for security vulnerabilities ONLY.

Focus on these security issues:
- SQL Injection (string concatenation in queries)
- Command Injection (os.system, subprocess with user input)
- XSS (Cross-Site Scripting)
- Hardcoded secrets (passwords, API keys, tokens)
- Insecure deserialization (pickle, yaml.load)
- Path traversal (user input in file paths)
- SSRF (Server-Side Request Forgery)
- Weak cryptography (MD5, SHA1 for passwords)
- Missing authentication/authorization checks
- Sensitive data exposure in logs

IGNORE: code style, naming conventions, minor bugs, performance.

```python
{code}
```

Respond with ONLY valid JSON. No markdown, no explanation, no extra text.
If no security issues found, return: {{"findings":[],"summary":"No security issues found"}}

Required format:
{{"findings":[{{"severity":"CRITICAL|HIGH|MEDIUM|LOW","category":"security","line":1,"description":"security issue","fix":"secure solution"}}],"summary":"one line"}}

Example:
{{"findings":[{{"severity":"CRITICAL","category":"security","line":5,"description":"SQL Injection","fix":"Use parameterized query"}}],"summary":"1 critical security issue"}}"""


# =============================================================================
# QUALITY REVIEWER - Focused on code quality and maintainability
# =============================================================================

QUALITY_PROMPT = """You are a CODE QUALITY EXPERT. Review this code for quality and maintainability ONLY.

Focus on these quality issues:
- Function/class too long or complex (>20 lines, cyclomatic complexity)
- Poor naming (unclear variable/function names)
- Code duplication
- Missing or inadequate error handling
- Tight coupling / poor separation of concerns
- Magic numbers/strings (should be constants)
- Missing type hints
- Inconsistent code style
- Dead code or unused variables
- Poor API design

IGNORE: security vulnerabilities, performance optimizations.

```python
{code}
```

Respond with ONLY valid JSON. No markdown, no explanation, no extra text.
If no quality issues found, return: {{"findings":[],"summary":"Code quality looks good"}}

Required format:
{{"findings":[{{"severity":"MEDIUM|LOW","category":"quality","line":1,"description":"quality issue","fix":"improvement suggestion"}}],"summary":"one line"}}

Example:
{{"findings":[{{"severity":"MEDIUM","category":"quality","line":10,"description":"Function too long","fix":"Extract into smaller functions"}}],"summary":"1 quality issue found"}}"""
