"""
MediPick — Issue Pydantic Schemas
Field names match src/api/issuesApi.ts.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.issue import Issue, IssueStatus, IssueType


class IssueOut(BaseModel):
    id: str
    orderId: str
    issueType: IssueType
    description: str
    evidenceFileKeys: list[str]
    status: IssueStatus
    resolution: str | None
    createdAt: datetime
    updatedAt: datetime

    @staticmethod
    def from_issue(i: Issue) -> "IssueOut":
        return IssueOut(
            id=str(i.id),
            orderId=str(i.order_id),
            issueType=i.issue_type,
            description=i.description,
            evidenceFileKeys=list(i.evidence_file_keys or []),
            status=i.status,
            resolution=i.resolution,
            createdAt=i.created_at,
            updatedAt=i.updated_at,
        )


class ReportIssueBody(BaseModel):
    orderId: uuid.UUID
    issueType: IssueType
    description: str = Field(..., min_length=5, max_length=2000)
    evidenceFileKeys: list[str] = Field(default_factory=list, max_length=5)
