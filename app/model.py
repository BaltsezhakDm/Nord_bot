from sqlalchemy import select, BigInteger, ForeignKey, Text
from sqlalchemy.orm import mapped_column, Mapped, relationship
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

try:
    from db import Base
except:
    from app.db import Base


class Customers(Base):

    __tablename__ = 'customers'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger) 
    qresto_id: Mapped[int]
    name: Mapped[str] = mapped_column(nullable=True)
    phone_number: Mapped[int] = mapped_column(BigInteger, nullable=True)
    referal_id: Mapped[int] = mapped_column(ForeignKey('customers.id'), nullable=True)
    news: Mapped[bool] = mapped_column(default=False)
    place_id: Mapped[int] = mapped_column(ForeignKey('places.id'), nullable=True)

    place: Mapped['Places'] = relationship("Places", back_populates='customers')
    referal: Mapped['Customers'] = relationship("Customers", remote_side=[id], back_populates='referals')
    referals: Mapped[list['Customers']] = relationship("Customers", back_populates='referal')

    @staticmethod
    async def create(db: AsyncSession, telegram_id: int, 
                     qresto_id: int, name = None, news=False, 
                     phone_number=None, place_id=None, referal_id=None ):
        customer = Customers(
            telegram_id=telegram_id,
            qresto_id=qresto_id,
            name=name,
            phone_number=phone_number,
            news=news,
            place_id=place_id,
            referal_id=referal_id
            )
        
        log = LogEntry(
            user_id=telegram_id,
            command='register new customer in tg bot',
            status='Success',
            error_message=None
        )
        db.add_all((customer, log))
        await db.commit()
        await db.refresh(customer)
        return customer

    @staticmethod
    async def find(telegram_id: int, db: AsyncSession):
        async with db.begin():
            result = await db.execute(select(Customers).filter(Customers.telegram_id == telegram_id))
            user = result.scalar_one_or_none()
            return user

    @staticmethod
    async def find_by_phone_number(phone_number: int, db: AsyncSession):
        async with db.begin():
            result = await db.execute(select(Customers).filter(Customers.phone_number == phone_number))
            user = result.scalar_one_or_none()
            return user


class LogEntry(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    command: Mapped[str] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(default=datetime.now, onupdate=datetime.now)

    @staticmethod
    def create_log(user_id, command, status="Processing", error_message=None):
        new_log = LogEntry(
            user_id=user_id,
            command=command,
            status=status,
            error_message=error_message,
            timestamp=datetime.now(),
        )
        return new_log
    
class Places(Base):

    __tablename__ = 'places'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(unique=True)

    customers: Mapped[list['Customers']] = relationship('Customers', back_populates='place')


    @staticmethod
    async def create(db: AsyncSession, name: str):
        async with db.begin():
            place = Places(name=name)
            db.add(place)
            try:
                await db.commit()
            except:
                await db.rollback()
