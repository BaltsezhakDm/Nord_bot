from sqlalchemy import select, BigInteger
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy.ext.asyncio import AsyncSession


from db import Base


class Customers(Base):

    __tablename__ = 'customers'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger) 
    qresto_id: Mapped[int]
    name: Mapped[str] = mapped_column(nullable=True)
    phone_number: Mapped[int] = mapped_column(BigInteger, nullable=True)
    news: Mapped[bool] = mapped_column(default=False)

    @staticmethod
    async def create(db: AsyncSession, telegram_id: int, qresto_id: int, name = None, news=False, phone_number=None):
        async with db.begin():
            customer = Customers(
                telegram_id=telegram_id,
                qresto_id=qresto_id,
                name=name,
                phone_number=phone_number,
                news=news)
            db.add(customer)
        await db.commit()
        await db.refresh(customer)
        return customer

    @staticmethod
    async def find(telegram_id: int, db: AsyncSession):
        async with db.begin():
            result = await db.execute(select(Customers).filter(Customers.telegram_id == telegram_id))
            user = result.scalar_one_or_none()
            return user

    
