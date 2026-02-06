"""Prompt templates for code analysis."""

# =============================================================================
# GENERAL REVIEWER - Catches bugs, performance, style issues
# =============================================================================

REVIEW_PROMPT = (
    "Review this code for bugs, security, performance, and style issues.\n"
    "\n"
    "```\n"
    "{code}\n"
    "```\n"
    "\n"
    "Respond with ONLY valid JSON. No markdown, no explanation, no extra text.\n"
    "\n"
    "Required format:\n"
    '{{"findings":[{{"severity":"CRITICAL|HIGH|MEDIUM|LOW",'
    '"category":"bug|security|performance|style",'
    '"line":1,"description":"issue","fix":"solution"}}],'
    '"summary":"one line"}}\n'
    "\n"
    "Example:\n"
    '{{"findings":[{{"severity":"HIGH","category":"bug","line":3,'
    '"description":"ZeroDivisionError if list empty",'
    '"fix":"if not nums: return 0"}}],"summary":"1 bug found"}}'
)


# =============================================================================
# SECURITY REVIEWER - Focused ONLY on security vulnerabilities
# =============================================================================

SECURITY_PROMPT = (
    "You are a SECURITY EXPERT. Review this code for security"
    " vulnerabilities ONLY.\n"
    "\n"
    "Focus on these security issues:\n"
    "- SQL Injection (string concatenation in queries)\n"
    "- Command Injection (os.system, subprocess with user input)\n"
    "- XSS (Cross-Site Scripting)\n"
    "- Hardcoded secrets (passwords, API keys, tokens)\n"
    "- Insecure deserialization (pickle, yaml.load)\n"
    "- Path traversal (user input in file paths)\n"
    "- SSRF (Server-Side Request Forgery)\n"
    "- Weak cryptography (MD5, SHA1 for passwords)\n"
    "- Missing authentication/authorization checks\n"
    "- Sensitive data exposure in logs\n"
    "\n"
    "IGNORE: code style, naming conventions, minor bugs, performance.\n"
    "\n"
    "```\n"
    "{code}\n"
    "```\n"
    "\n"
    "Respond with ONLY valid JSON. No markdown, no explanation, no extra text.\n"
    "If no security issues found, return: "
    '{{"findings":[],"summary":"No security issues found"}}\n'
    "\n"
    "Required format:\n"
    '{{"findings":[{{"severity":"CRITICAL|HIGH|MEDIUM|LOW",'
    '"category":"security","line":1,'
    '"description":"security issue","fix":"secure solution"}}],'
    '"summary":"one line"}}\n'
    "\n"
    "Example:\n"
    '{{"findings":[{{"severity":"CRITICAL","category":"security","line":5,'
    '"description":"SQL Injection",'
    '"fix":"Use parameterized query"}}],'
    '"summary":"1 critical security issue"}}'
)


# =============================================================================
# QUALITY REVIEWER - Focused on code quality and maintainability
# =============================================================================

QUALITY_PROMPT = (
    "You are a CODE QUALITY EXPERT. Review this code for quality"
    " and maintainability ONLY.\n"
    "\n"
    "Focus on these quality issues:\n"
    "- Function/class too long or complex (>20 lines, cyclomatic complexity)\n"
    "- Poor naming (unclear variable/function names)\n"
    "- Code duplication\n"
    "- Missing or inadequate error handling\n"
    "- Tight coupling / poor separation of concerns\n"
    "- Magic numbers/strings (should be constants)\n"
    "- Missing type hints\n"
    "- Inconsistent code style\n"
    "- Dead code or unused variables\n"
    "- Poor API design\n"
    "\n"
    "IGNORE: security vulnerabilities, performance optimizations.\n"
    "\n"
    "```\n"
    "{code}\n"
    "```\n"
    "\n"
    "Respond with ONLY valid JSON. No markdown, no explanation, no extra text.\n"
    "If no quality issues found, return: "
    '{{"findings":[],"summary":"Code quality looks good"}}\n'
    "\n"
    "Required format:\n"
    '{{"findings":[{{"severity":"MEDIUM|LOW","category":"quality","line":1,'
    '"description":"quality issue","fix":"improvement suggestion"}}],'
    '"summary":"one line"}}\n'
    "\n"
    "Example:\n"
    '{{"findings":[{{"severity":"MEDIUM","category":"quality","line":10,'
    '"description":"Function too long",'
    '"fix":"Extract into smaller functions"}}],'
    '"summary":"1 quality issue found"}}'
)
