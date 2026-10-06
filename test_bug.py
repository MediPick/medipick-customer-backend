import asyncio
from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.services.order_service import order_service
from app.models.order import OrderState
from sqlalchemy import select

async def test():
    async with AsyncSessionLocal() as db:
        from app.models.order import Order
        order = (await db.execute(select(Order).where(Order.order_number == '#MP340662'))).scalars().first()
        if not order:
            print("Order not found")
            return
            
        customer = (await db.execute(select(Customer).where(Customer.id == order.customer_id))).scalars().first()
        
        try:
            await order_service.set_state(db, customer, order.id, OrderState.WAITING_CUSTOMER_CONFIRMATION)
            await db.commit()
            print("Success")
        except Exception as e:
            import traceback
            traceback.print_exc()

asyncio.run(test())
