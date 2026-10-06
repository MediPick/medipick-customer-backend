"""
MediPick — Issues Endpoints (A12.1 → A12.3). All require a customer token.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_customer_user
from app.database import get_db
from app.models.customer import Customer
from app.models.user import User
from app.schemas.common import PaginatedResponse, PaginationMeta, SuccessResponse
from app.schemas.issue import IssueOut, ReportIssueBody
from app.services.issue_service import issue_service

router = APIRouter(prefix="/issues", tags=["Issues"])


@router.get("", response_model=PaginatedResponse[list[IssueOut]], summary="A12.1 — List my issues")
async def list_issues(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    issues, total = await issue_service.list(db, customer, page, limit)
    return PaginatedResponse(data=[IssueOut.from_issue(i) for i in issues], meta=PaginationMeta.build(page, limit, total))


@router.get("/{issue_id}", response_model=SuccessResponse[IssueOut], summary="A12.2 — Issue detail")
async def get_issue(
    issue_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    _, customer = current
    return SuccessResponse(data=IssueOut.from_issue(await issue_service.get(db, customer, issue_id)))


@router.post(
    "", status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[IssueOut], summary="A12.3 — Report an issue",
)
async def report_issue(
    body: ReportIssueBody,
    db: AsyncSession = Depends(get_db),
    current: tuple[User, Customer] = Depends(get_current_customer_user),
):
    user, customer = current
    return SuccessResponse(data=IssueOut.from_issue(await issue_service.report(db, user, customer, body)))
