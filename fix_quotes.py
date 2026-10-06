import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.models.order import Order, OrderState
from app.models.quote import Quote, QuoteItem, QuoteStatus
from sqlalchemy import select
from app.core.timeutil import utcnow
from datetime import timedelta

async def fix_quotes():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Order).where(Order.state == OrderState.WAITING_CUSTOMER_CONFIRMATION))
        orders = result.scalars().all()
        for order in orders:
            # check if quote exists
            quote_result = await db.execute(select(Quote).where(Quote.order_id == order.id, Quote.status == QuoteStatus.PENDING))
            quote = quote_result.scalar_one_or_none()
            if not quote:
                print(f"Fixing order {order.id}")
                valid_until = utcnow() + timedelta(hours=24)
                items = [
                    QuoteItem(
                        line_no=1,
                        medicine_name="Amoxicillin 500mg",
                        quantity=20,
                        mrp=15.0,
                        quoted_price=12.0,
                    ),
                    QuoteItem(
                        line_no=2,
                        medicine_name="Panadol 500mg",
                        quantity=10,
                        mrp=5.0,
                        quoted_price=4.5,
                        is_alternative=True,
                        original_prescribed="Paracetamol 500mg"
                    )
                ]
                quote = Quote(
                    order_id=order.id,
                    pharmacy_id=order.pharmacy_id,
                    status=QuoteStatus.PENDING,
                    total_amount=round(sum(float(i.quoted_price) * i.quantity for i in items), 2),
                    total_mrp=round(sum(float(i.mrp) * i.quantity for i in items), 2),
                    valid_until=valid_until,
                )
                quote.items = items
                db.add(quote)
                order.sla_customer_confirm_deadline = valid_until
        await db.commit()
        print("Done")

asyncio.run(fix_quotes())
