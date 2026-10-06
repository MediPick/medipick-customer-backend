"""
MediPick — Stock Service
Reserves pharmacy inventory when an order is placed and gives it back when the
order is cancelled. Inventory rows are locked (SELECT ... FOR UPDATE) so two
customers ordering the last unit at the same moment can't both get it.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_item import InventoryItem
from app.models.order import OrderItem


class StockService:

    async def lock_inventory(
        self, db: AsyncSession, pharmacy_id: uuid.UUID, medicine_id: uuid.UUID
    ) -> InventoryItem | None:
        result = await db.execute(
            select(InventoryItem)
            .where(InventoryItem.pharmacy_id == pharmacy_id, InventoryItem.medicine_id == medicine_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def try_reserve(
        self, db: AsyncSession, pharmacy_id: uuid.UUID, item: OrderItem
    ) -> bool:
        """Best-effort reservation for an item whose price is already decided
        (e.g. from a pharmacist's quote). Never fails — just doesn't reserve."""
        if item.medicine_id is None:
            return False
        inventory = await self.lock_inventory(db, pharmacy_id, item.medicine_id)
        if inventory is None or inventory.stock_quantity < item.quantity:
            return False
        inventory.stock_quantity -= item.quantity
        item.inventory_item_id = inventory.id
        return True

    async def release(self, db: AsyncSession, items: list[OrderItem]) -> None:
        """Returns reserved units for every item that actually reserved some."""
        for item in items:
            if item.inventory_item_id is None:
                continue
            result = await db.execute(
                select(InventoryItem).where(InventoryItem.id == item.inventory_item_id).with_for_update()
            )
            inventory = result.scalar_one_or_none()
            if inventory is not None:
                inventory.stock_quantity += item.quantity
            item.inventory_item_id = None


stock_service = StockService()
