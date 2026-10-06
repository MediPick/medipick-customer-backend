"""
MediPick — Issue Service (A12)
Customers report a problem with an order after picking it up. Evidence files
are uploaded through the same signed-URL flow as prescriptions and referenced
by file key; only the reporter's own uploads are accepted.
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.exceptions import MediPickException
from app.models.customer import Customer
from app.models.issue import Issue, IssueStatus
from app.models.notification import NotificationType
from app.models.order import OrderState
from app.models.user import User
from app.schemas.issue import ReportIssueBody
from app.services.notification_service import notification_service
from app.services.order_fsm import order_fsm
from app.services.order_service import order_service

# ISSUE_REPORTED is accepted too: OrderContext flags the order via PATCH first.
REPORTABLE_STATES = {OrderState.COMPLETED, OrderState.ISSUE_REPORTED}


class IssueService:

    # ── A12.1 ─────────────────────────────────────────────────────────────────

    async def list(self, db: AsyncSession, customer: Customer, page: int, limit: int) -> tuple[list[Issue], int]:
        condition = Issue.customer_id == customer.id
        total = (await db.execute(select(func.count()).select_from(Issue).where(condition))).scalar_one()
        result = await db.execute(
            select(Issue).where(condition).order_by(Issue.created_at.desc()).offset((page - 1) * limit).limit(limit)
        )
        return list(result.scalars().all()), total

    # ── A12.2 ─────────────────────────────────────────────────────────────────

    async def get(self, db: AsyncSession, customer: Customer, issue_id: uuid.UUID) -> Issue:
        issue = (await db.execute(
            select(Issue).where(Issue.id == issue_id, Issue.customer_id == customer.id)
        )).scalar_one_or_none()
        if issue is None:
            raise MediPickException("ISSUE_NOT_FOUND", 404, "Issue not found.")
        return issue

    # ── A12.3 ─────────────────────────────────────────────────────────────────

    async def report(self, db: AsyncSession, user: User, customer: Customer, body: ReportIssueBody) -> Issue:
        order = await order_service.load_order(db, body.orderId, customer_id=customer.id, for_update=True)
        if order.state not in REPORTABLE_STATES:
            raise MediPickException("ORDER_NOT_COMPLETED", 409, "Issues can only be reported after pickup.")
        if (await db.execute(select(Issue.id).where(Issue.order_id == order.id))).first() is not None:
            raise MediPickException("ISSUE_ALREADY_REPORTED", 409, "An issue has already been reported for this order.")

        for key in body.evidenceFileKeys:
            if (
                not storage.is_valid_file_key(key)
                or storage.owner_id_from_key(key) != str(user.id)
                or not storage.file_exists(key)
            ):
                raise MediPickException("INVALID_EVIDENCE", 400, f"Evidence file '{key}' wasn't uploaded by you.")

        issue = Issue(
            order_id=order.id,
            customer_id=customer.id,
            issue_type=body.issueType,
            description=body.description.strip(),
            evidence_file_keys=list(dict.fromkeys(body.evidenceFileKeys)),
            status=IssueStatus.OPEN,
        )
        db.add(issue)
        await order_fsm.transition(db, order, OrderState.ISSUE_REPORTED)
        await notification_service.notify_customer(
            db, customer.id, NotificationType.SYSTEM, "We received your report",
            f"Our team will look into the problem with order {order.order_number} and get back to you.",
            order_id=order.id,
        )
        await db.flush()
        return issue


issue_service = IssueService()
