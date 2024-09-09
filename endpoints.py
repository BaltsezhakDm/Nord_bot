from aiogram import types, F
import logging
from functools import wraps
from aiogram.utils.deep_linking import create_start_link
from aiogram.filters import CommandStart
from aiogram.filters import Command
from api import CRM, Office
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from aiogram.fsm.context import FSMContext
import os
from utils import encode_user_id, decode_user_id, encode_json, decode_json
from fsm import Form
from logger import setup_logger

from model import Customers, Places

from aiogram import Router

login_api = os.getenv('login_api')
password_api = os.getenv('password_api')
login_lk = os.getenv('login_lk')
password_lk = os.getenv('password_lk')

logger = setup_logger()
router = Router(name=__name__)

api = CRM(login=login_api, password=password_api)
lk = Office(login=login_lk, password=password_lk)


key1 = types.KeyboardButton(text='Баланс')
key2 = types.KeyboardButton(text='История')
key3 = types.KeyboardButton(text='QR код')
# key4 = types.KeyboardButton(text='Подписаться на канал')
keyboard_main = types.ReplyKeyboardMarkup(
    keyboard=[[key1, key2, key3]], resize_keyboard=True)

start_text_1 = \
    '''Здравствуйте, {}!
Мы рады знакомству с тобой!
Добро пожаловать в систему лояльности кофейни KOS.PLACE.'''

start_text_2 = \
    '''Мы начисляем 5% с каждого чека на ваш бонусный счет и в дальнейшем можем списать до 50% суммы чека из ваших бонусов.
В данном чате вы будете видеть зачисления\списания бонусов и ваш баланс.
<b>Нажмите на кнопку "Телефон" для входа или регистрации.</b>'''


def login_required(func):
    @wraps(func)
    async def wrapper(message: types.Message, session: AsyncSession, *args, **kwargs):
        client = await Customers.find(message.chat.id, session)
        if client:
            return await func(message, session, client, *args, **kwargs)
        else:
            await message.answer(text='Вы не вошли. Введите команду /start')
    return wrapper


@router.message(CommandStart())
async def show_hello(message: types.Message, session: AsyncSession, state: FSMContext):
    '''Сообщение при старте бота'''
    await state.set_state(Form.ref)
    start_link = message.md_text.split()
    if len(start_link) == 2:
        logger.debug(f'Ref link: {start_link[1]}')
        try:
            place = decode_json(str(start_link[1]))
            if isinstance(place, dict):
                place = place['place']
            logger.debug(f'(place): {place}')
            await state.update_data(place_id=place, user_id=None)
        except:
            user_id = decode_user_id(str(start_link[1]))
            logger.debug(f'(user): {user_id}')
            await state.update_data(place_id=None, user_id=user_id)


    client = await Customers.find(message.chat.id, db=session)
    if client:
        await state.clear()
        await message.answer(text=f'С возвращением, {message.chat.first_name}!', reply_markup=keyboard_main)
    else:
        button_phone = types.KeyboardButton(text="Телефон",
                                            request_contact=True)
        keyboard = types.ReplyKeyboardMarkup(keyboard=[[button_phone]],
                                             resize_keyboard=True)
        await message.answer(text=start_text_1.format(message.chat.first_name))
        await message.answer(text=start_text_2, reply_markup=keyboard, parse_mode='HTML')


@router.message(F.contact)
async def contact(message: types.Message, session: AsyncSession, state: FSMContext):
    if message.contact:
        logger.debug(f'Contact: {message.contact.phone_number}')
        await state.set_state(Form.number)
        data = await state.get_data()
        logger.debug(f'Data: {data}')
        phone_number = int(message.contact.phone_number[-10:])
        client = api.find_client(phone_number)
        if client:
            await Customers.create(
                session, message.chat.id, int(client['id']),
                f"{client.get('firstName')} {client.get('lastName')}",
                phone_number=phone_number, place_id=data.get('place_id'), referal_id=data.get('user_id'))
            if client['tokens'] == [] or str(phone_number) not in [token['key'] for token in client['tokens']]:
                lk.create_token(client.get('id'), phone_number)

            await state.clear()
            await message.answer('Ваш номер уже зарегистрирован!', reply_markup=keyboard_main)
        else:
            full_name = f'{message.from_user.first_name} {message.from_user.last_name}'
            client_db = await Customers.find(message.chat.id, session)
            if not client_db:
                new_client = api.create(
                    full_name, phone_number, message.chat.id)

                await Customers.create(
                    session, message.chat.id, new_client.get('id'), full_name,
                    phone_number=phone_number, place_id=data.get('place_id'), referal_id=data.get('user_id'))

                lk.create_token(new_client.get('id'), phone_number)

            await state.clear()
            await message.answer('Успешная регистрация!', reply_markup=keyboard_main)
    await state.clear()


@router.message(Command('ref'))
@router.message(F.text == 'ref')
@login_required
async def ref_account(message: types.Message, session: AsyncSession, client: Customers):
    user_id = encode_user_id(int(client.id))
    link = await create_start_link(message.bot, user_id)
    await message.answer(f'Ссылка для приглашения! {link}')


@router.message(Command('history'))
@router.message(F.text == 'История')
@login_required
async def show_history(message: types.Message, session: AsyncSession, client: Customers, page=1, previous_message=None):
    '''Вывод истории транзакций пользователя'''

    history = api.get_history(client.phone_number)
    if len(history) > 6 and type(history) == type(list()):
        pages_count = len(history) // 6 + 1
        left = page-1 if page != 1 else pages_count
        right = page+1 if page != pages_count else 1
        left_button = types.InlineKeyboardButton(
            text="←", callback_data=f'to {left}')
        page_button = types.InlineKeyboardButton(
            text=f"{str(page)}/{str(pages_count)}", callback_data='_')
        right_button = types.InlineKeyboardButton(
            text="→", callback_data=f'to {right}')
        buttons = types.InlineKeyboardMarkup(
            inline_keyboard=[(left_button, page_button, right_button)])
        try:
            if page == 1 and not previous_message:
                await message.answer(text='{}'.format(''.join(history[(page-1)*6:page*6])), reply_markup=buttons)
            else:
                await message.edit_text(text='{}'.format(''.join(history[(page-1)*6:page*6])), reply_markup=buttons)
        except:
            pass
    else:
        await message.answer(text='{}'.format(''.join(history)))


@router.message(Command('balance'))
@router.message(F.text == 'Баланс')
@login_required
async def show_balance(message: types.Message, session: AsyncSession, client: Customers):
    '''Вывод актуального баланса пользователя'''

    balance = api.get_balance(client.phone_number)
    await message.answer(text='{}, у вас {} баллов'.format(client.name, balance))


@router.message(Command('placeQR'))
async def place_qr(message: types.Message, session: AsyncSession):
    
    places = await session.scalars(select(Places))
    for place in places.all():
        await message.answer(text=place.name)
        crypt = encode_json({'place': place.id})
        link = await create_start_link(message.bot, '')
        await message.answer(text=link + crypt)


@router.message(Command('qr'))
@router.message(F.text == 'QR код')
@login_required
async def show_qr(message: types.Message, session: AsyncSession, client: Customers):
    '''Вывод QR кода пользователя для его индетификации в программе лояльности'''

    await message.answer_photo(photo=api.qr_code(client.phone_number))


@router.callback_query()
async def call_info(call: types.CallbackQuery, session: AsyncSession):
    '''Захват нажатие кнопки после старта бота, регистрация или вход'''

    if 'to' in call.data:
        page = int(call.data.split(' ')[1])
        await show_history(call.message, session, page=page, previous_message=call.message)
        await call.answer()
