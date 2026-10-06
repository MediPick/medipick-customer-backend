import asyncio
import httpx

async def test():
    async with httpx.AsyncClient() as client:
        # We need a valid token. Let's get a token for the customer.
        from app.database import AsyncSessionLocal
        from app.models.customer import Customer
        from app.models.user import User
        from app.models.order import Order
        from app.core.security import create_access_token
        from sqlalchemy import select
        
        async with AsyncSessionLocal() as db:
            order = (await db.execute(select(Order).where(Order.order_number == '#MP340662'))).scalars().first()
            customer = (await db.execute(select(Customer).where(Customer.id == order.customer_id))).scalars().first()
            user = (await db.execute(select(User).where(User.id == customer.user_id))).scalars().first()
            token = create_access_token(user.id, user.phone_number)
            
            headers = {"Authorization": f"Bearer {token}"}
            res = await client.patch(f"http://127.0.0.1:8000/api/v1/orders/{order.id}/payment-method", json={"paymentMethod": "ONLINE"}, headers=headers)
            print(res.status_code)
            print(res.text)

asyncio.run(test())
