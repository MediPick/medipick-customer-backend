import asyncio
from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.services.order_service import order_service
from app.models.order import PaymentMethod
from sqlalchemy import select

async def test():
    async with AsyncSessionLocal() as db:
        from app.models.order import Order
        order = (await db.execute(select(Order).where(Order.order_number == '#MP340662'))).scalars().first()
        customer = (await db.execute(select(Customer).where(Customer.id == order.customer_id))).scalars().first()
        
        try:
            await order_service.update_payment_method(db, customer, order.id, PaymentMethod.ONLINE)
            print("Success")
        except Exception as e:
            import traceback
            traceback.print_exc()

asyncio.run(test())
