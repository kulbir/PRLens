"""Data models for code review findings."""

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """Structure for a single review finding."""
    severity: str = Field(default="MEDIUM", description="CRITICAL, HIGH, MEDIUM, LOW")
    category: str = Field(default="bug", description="bug, security, performance, pep8")
    line: int | None = Field(default=None, description="Line number")
    description: str = Field(description="What the issue is")
    fix: str = Field(default="", description="Suggested fix or code snippet")


class ReviewResult(BaseModel):
    """Structure for complete review output."""
    findings: list[Finding] = Field(default_factory=list)
    summary: str = Field(default="", description="Brief overall summary")

