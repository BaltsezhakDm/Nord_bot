'''
Создание моделей и обьектов локальной БД,
и функции работы с ней
'''

from sqlalchemy import create_engine, Column, MetaData, Table, Integer, DateTime, String, Boolean
from sqlalchemy import select, insert

engine = create_engine('sqlite:///customer.db')

meta_data = MetaData()

customer= Table(
    'customer',
    meta_data,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('telegram_id', Integer),
    Column('qresto_id', Integer),
    Column('name', String, nullable=True),
    Column('phone_number', Integer, nullable=True),
    Column('news', Boolean, nullable=True)
    )

try:
    meta_data.create_all(engine)
except:
    pass


def add_customer(telegram_id, qresto_id, name = None, news=False, phone_number=None):
    '''Cоздания пользователя'''
    with engine.connect() as conn:
        stmt = insert(customer).values(
            telegram_id=telegram_id,
            qresto_id=qresto_id,
            name=name,
            phone_number=phone_number,
            news=news
            )
        conn.execute(stmt)
        conn.commit()

def find_customer(telegram_id):
    '''Поиск пользователя по telegram_id'''
    with engine.connect() as conn:
        stmt = select(customer).where(customer.c.telegram_id==telegram_id)
        exec = conn.execute(stmt)
        return exec.all()