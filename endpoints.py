from aiogram import types, F
from aiogram.filters import Command
from api import CRM, Office
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
import os

from model import Customers

from aiogram import Router

login_api = os.getenv('login_api')
password_api = os.getenv('password_api')
login_lk = os.getenv('login_lk')
password_lk = os.getenv('password_lk')


HISTORY = dict()


router = Router(name=__name__)

api = CRM(login=login_api, password=password_api)
lk = Office(login=login_lk, password=password_lk)


key1 = types.KeyboardButton(text='Баланс')
key2 = types.KeyboardButton(text='История')
key3 = types.KeyboardButton(text='QR код')
# key4 = types.KeyboardButton(text='Подписаться на канал')
keyboard_main = types.ReplyKeyboardMarkup(keyboard=[[key1, key2, key3]], resize_keyboard=True)

start_text_1 = \
'''Здравствуйте, {}!
Мы рады знакомству с тобой!
Добро пожаловать в систему лояльности кофейни KOS.PLACE.'''

start_text_2 = \
'''Мы начисляем 5% с каждого чека на ваш бонусный счет и в дальнейшем можем списать до 50% суммы чека из ваших бонусов.
В данном чате вы будете видеть зачисления\списания бонусов и ваш баланс.
<b>Нажмите на кнопку "Телефон" для входа или регистрации.</b>'''

@router.message(Command('start'))
async def show_hello(message: types.Message, session: AsyncSession):
    '''Сообщение при старте бота'''

    # поиск в локальной БД гостя по telegram_id
    client = await Customers.find(message.chat.id, db=session)
    if client:
        await message.answer(text=f'С возвращением, {message.chat.first_name}', reply_markup=keyboard_main)
    else:
        key1 = types.KeyboardButton(
            text='Новости + бонусы за них', callback_data='set_news')
        key2 = types.KeyboardButton(
            text='Только система лояльности', callback_data='only_bonuses')
        button_phone = types.KeyboardButton(text="Телефон",
                                            request_contact=True)
        keyboard = types.ReplyKeyboardMarkup(keyboard=[[button_phone]],
            resize_keyboard=True)
        await message.answer(text=start_text_1.format(message.chat.first_name))
        await message.answer(text=start_text_2, reply_markup=keyboard, parse_mode='HTML')

@router.message(F.contact)
async def contact(message: types.Message, session: AsyncSession):
    if message.contact:
        phone_number = int(message.contact.phone_number[-10:])
        client = api.find_client(phone_number)
        if client:
            await Customers.create(
                session, message.chat.id, int(client['id']),
                f"{client.get('firstName')} {client.get('lastName')}",
                phone_number=phone_number)
            if client['tokens'] == [] or str(phone_number) not in [token['key'] for token in client['tokens']]:
                lk.create_token(client.get('id'), phone_number)

            await message.answer('Ваш номер уже зарегистрирован!', reply_markup=keyboard_main)
        else:
            full_name = f'{message.from_user.first_name} {message.from_user.last_name}'
            client_db = await Customers.find(message.chat.id, session)
            if not client_db:
                new_client = api.create( full_name, phone_number, message.chat.id)
            
                await Customers.create(
                    session, message.chat.id, new_client.get('id'), full_name,
                    phone_number=phone_number)
            
                lk.create_token(new_client.get('id'), phone_number)
            await message.answer('Успешная регистрация!', reply_markup=keyboard_main)

@router.message(Command('history'))
@router.message(F.text == 'История')
async def show_history(message: types.Message, session: AsyncSession, page=1, previous_message=None):
    '''Вывод истории транзакций пользователя'''

    client = await Customers.find(message.chat.id, session)
    if client:
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
            buttons = types.InlineKeyboardMarkup(inline_keyboard=[(left_button, page_button, right_button)])
            try:
                if page == 1 and not previous_message:
                    await message.answer(text='{}'.format(''.join(history[(page-1)*6:page*6])), reply_markup=buttons)
                else:
                    await message.edit_text(text='{}'.format(''.join(history[(page-1)*6:page*6])), reply_markup=buttons)
            except:
                pass
        else:
            await message.answer(text='{}'.format(''.join(history)))
    else:
        await message.answer(text='Вы не вошли. Введите команду /start')

@router.message(Command('balance'))
@router.message(F.text == 'Баланс')
async def show_balance(message: types.Message, session: AsyncSession):
    '''Вывод актуального баланса пользователя'''

    client = await Customers.find(message.chat.id, session)
    if client:
        balance = api.get_balance(client.phone_number)
        await message.answer(text='{}, у вас {} баллов'.format(client.name, balance))
    else:
        await message.answer(text='Вы не вошли. Введите команду /start')


@router.message(Command('qr'))
@router.message(F.text == 'QR код')
async def show_qr(message: types.Message, session: AsyncSession):
    '''Вывод QR кода пользователя для его индетификации в программе лояльности'''

    client = await Customers.find(message.chat.id, session)
    if client:
        await message.answer_photo(photo=api.qr_code(client.phone_number))
    else:
        await message.answer(text='Вы не вошли. Введите команду /start')

@router.callback_query()
async def call_info(call: types.CallbackQuery, session: AsyncSession):
    '''Захват нажатие кнопки после старта бота, регистрация или вход'''

    if 'to' in call.data:
        page = int(call.data.split(' ')[1])
        await show_history(call.message, session, page=page, previous_message=call.message)
        await call.answer()
