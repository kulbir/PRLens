"""Data models for code review findings."""

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]
Category = Literal["bug", "security", "performance", "style", "pep8", "quality"]


class Finding(BaseModel):
    """A single review finding."""

    severity: Severity = Field(
        default="MEDIUM", description="CRITICAL, HIGH, MEDIUM, LOW"
    )
    category: Category = Field(
        default="bug",
        description="bug, security, performance, style, pep8, quality",
    )
    line: int | None = Field(default=None, description="Line number in the file")
    description: str = Field(description="What the issue is")
    fix: str = Field(default="", description="Suggested fix or code snippet")
    path: str | None = Field(
        default=None, description="File path (populated during review)"
    )


class ReviewResult(BaseModel):
    """Complete review output from a single reviewer."""

    findings: list[Finding] = Field(default_factory=list)
    summary: str = Field(default="", description="Brief overall summary")
