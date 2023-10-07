'''
Создание моделей и обьектов локальной БД,
и функции работы с ней
'''

import sqlalchemy as models
from sqlalchemy import create_engine, Column
from sqlalchemy.orm import declarative_base, Session
import os

user_db = os.getenv('user_db')
password_db = os.getenv('password_db')
database = os.getenv('database')
host_db = os.getenv('host_db')

SQLALCHEMY_DATABASE_URL = f'postgresql://{user_db}:{password_db}@{host_db}/{database}'

engine = create_engine(SQLALCHEMY_DATABASE_URL)
Base = declarative_base()


class Customers(Base):

    __tablename__ = 'customers'

    id = Column(models.BigInteger,primary_key=True)
    telegram_id = Column(models.String)
    qresto_id = Column(models.Integer)
    name = Column(models.String, nullable=True)
    phone_number = Column(models.String, nullable=True)
    news = Column(models.Boolean, nullable=True)



def add_customer(telegram_id, qresto_id, name = None, news=False, phone_number=None):
    '''Cоздания пользователя'''
    with Session(engine) as session:
        customer = Customers(telegram_id=str(telegram_id),
            qresto_id=qresto_id,
            name=name,
            phone_number=str(phone_number),
            news=news)
        session.add(customer)
        session.commit()


def find_customer(telegram_id):
    '''Поиск пользователя по telegram_id'''
    with Session(engine) as session:
        return session.query(Customers).filter(Customers.telegram_id==str(telegram_id)).all()