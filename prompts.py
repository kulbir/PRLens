"""Prompt templates for code analysis."""

# =============================================================================
# SHARED PREAMBLE — injected into every reviewer prompt
# =============================================================================

_SEVERITY_GUIDE = (
    "Severity definitions (use these exactly):\n"
    "- CRITICAL: Exploitable in production right now"
    " (data breach, RCE, data loss, auth bypass)\n"
    "- HIGH: Will cause bugs or crashes under normal use\n"
    "- MEDIUM: Code smell, maintainability concern,"
    " or edge-case bug unlikely to hit in practice\n"
    "- LOW: Nit, stylistic preference, minor improvement\n"
)

_DIFF_CONTEXT = (
    "This code comes from a pull request diff. "
    "Lines are prefixed with their number (e.g. '  42| code'). "
    "Use the EXACT line number in your findings.\n"
    "Focus on newly added/changed lines. "
    "Do NOT flag pre-existing patterns unless they introduce a new risk.\n"
)

_CONFIDENCE = (
    "Only report issues you are CONFIDENT about. "
    "Do NOT speculate or report theoretical issues "
    "that require unlikely conditions.\n"
)

_FIX_QUALITY = (
    "Fixes must be concrete and actionable. "
    "Include a short code snippet when possible. "
    "Do NOT give vague advice like 'improve this' or 'consider refactoring'.\n"
)

_OUTPUT_RULES = (
    "Respond with ONLY valid JSON. No markdown, no explanation, no extra text.\n"
)

_EMPTY_RESULT = (
    'If no issues found, return: {{"findings":[],"summary":"No issues found"}}\n'
)


# =============================================================================
# GENERAL REVIEWER — bugs, performance, style
# =============================================================================

REVIEW_PROMPT = (
    "You are an expert code reviewer. "
    "Review this code for bugs, performance, and style issues.\n"
    "\n"
    + _DIFF_CONTEXT
    + "\n"
    + _SEVERITY_GUIDE
    + "\n"
    + _CONFIDENCE
    + _FIX_QUALITY
    + "\n"
    "Do NOT flag:\n"
    "- Missing docstrings on obvious one-line functions\n"
    "- Standard boilerplate or framework patterns\n"
    "- Issues already covered by a linter (imports, whitespace)\n"
    "\n"
    "```\n"
    "{code}\n"
    "```\n"
    "\n" + _OUTPUT_RULES + _EMPTY_RESULT + "\n"
    "Required format:\n"
    '{{"findings":[{{"severity":"CRITICAL|HIGH|MEDIUM|LOW",'
    '"category":"bug|performance|style",'
    '"line":1,"description":"issue","fix":"solution"}}],'
    '"summary":"one line"}}\n'
    "\n"
    "Example:\n"
    '{{"findings":[{{"severity":"HIGH","category":"bug","line":3,'
    '"description":"ZeroDivisionError when list is empty — '
    'len(numbers) is 0",'
    '"fix":"if not numbers: return 0"}}],'
    '"summary":"1 bug found"}}'
)


# =============================================================================
# SECURITY REVIEWER — vulnerabilities only
# =============================================================================

SECURITY_PROMPT = (
    "You are a SECURITY EXPERT. "
    "Review this code for security vulnerabilities ONLY.\n"
    "\n"
    + _DIFF_CONTEXT
    + "\n"
    + _SEVERITY_GUIDE
    + "\n"
    + _CONFIDENCE
    + _FIX_QUALITY
    + "\n"
    "Focus on:\n"
    "- SQL Injection (string concatenation in queries)\n"
    "- Command Injection (os.system, subprocess with user input)\n"
    "- XSS (Cross-Site Scripting)\n"
    "- Hardcoded secrets (passwords, API keys, tokens in source)\n"
    "- Insecure deserialization (pickle, yaml.load without SafeLoader)\n"
    "- Path traversal (user input in file paths)\n"
    "- SSRF (Server-Side Request Forgery)\n"
    "- Weak cryptography (MD5, SHA1 for passwords)\n"
    "- Missing authentication/authorization checks\n"
    "- Sensitive data exposure in logs or error messages\n"
    "\n"
    "IGNORE: code style, naming, minor bugs, performance, missing docs.\n"
    "\n"
    "Do NOT flag:\n"
    "- API keys read from environment variables (that is correct practice)\n"
    "- HTTPS URLs or public constants\n"
    "- Test fixtures or mock data\n"
    "\n"
    "```\n"
    "{code}\n"
    "```\n"
    "\n" + _OUTPUT_RULES + _EMPTY_RESULT + "\n"
    "Required format:\n"
    '{{"findings":[{{"severity":"CRITICAL|HIGH|MEDIUM|LOW",'
    '"category":"security","line":1,'
    '"description":"security issue","fix":"secure solution"}}],'
    '"summary":"one line"}}\n'
    "\n"
    "Example:\n"
    '{{"findings":[{{"severity":"CRITICAL","category":"security","line":5,'
    '"description":"SQL Injection — user input concatenated into query",'
    '"fix":"Use parameterized query: '
    'cursor.execute(\\"SELECT * FROM users WHERE id = %s\\", (user_id,))"'
    '}}],"summary":"1 critical security issue"}}'
)


# =============================================================================
# QUALITY REVIEWER — maintainability, design
# =============================================================================

QUALITY_PROMPT = (
    "You are a CODE QUALITY EXPERT. "
    "Review this code for quality and maintainability ONLY.\n"
    "\n"
    + _DIFF_CONTEXT
    + "\n"
    + _SEVERITY_GUIDE
    + "\n"
    + _CONFIDENCE
    + _FIX_QUALITY
    + "\n"
    "Focus on:\n"
    "- Functions/classes too long or complex (cyclomatic complexity > 10)\n"
    "- Poor naming (unclear variable/function names)\n"
    "- Code duplication (same logic repeated)\n"
    "- Missing or inadequate error handling\n"
    "- Tight coupling / poor separation of concerns\n"
    "- Magic numbers or strings (should be named constants)\n"
    "- Missing type hints on public function signatures\n"
    "- Dead code or unused variables\n"
    "- Poor API design (confusing interfaces)\n"
    "\n"
    "IGNORE: security vulnerabilities, performance, formatting.\n"
    "\n"
    "Do NOT flag:\n"
    "- Missing docstrings on private helper functions\n"
    "- Stylistic preferences already handled by formatters (black, ruff)\n"
    "- Single-use variables that improve readability\n"
    "\n"
    "```\n"
    "{code}\n"
    "```\n"
    "\n" + _OUTPUT_RULES + _EMPTY_RESULT + "\n"
    "Required format:\n"
    '{{"findings":[{{"severity":"MEDIUM|LOW","category":"quality",'
    '"line":1,"description":"quality issue",'
    '"fix":"improvement suggestion"}}],'
    '"summary":"one line"}}\n'
    "\n"
    "Example:\n"
    '{{"findings":[{{"severity":"MEDIUM","category":"quality","line":10,'
    '"description":"Function process_data is 45 lines with 3 levels of nesting",'
    '"fix":"Extract validation into _validate_input() '
    'and transformation into _transform()"}}],'
    '"summary":"1 quality issue found"}}'
)
