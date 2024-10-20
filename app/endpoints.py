import os
import yaml

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.deep_linking import create_start_link
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api import CRM, Office
from model import Customers, Places
from fsm import Form, AskForm
from utils import encode_user_id, encode_json, check_referal
from logger import setup_logger
from auth import login_required_callback, login_required
from keyboards import keyboard_main, keyboard_back, keyboard_menu, keyboard_social, keyboard_review, clean_keyboard


logger = setup_logger()
router = Router(name=__name__)

with open('app/messages.yaml', 'r', encoding='utf-8') as f:
    messages = yaml.safe_load(f)

photo_nord = FSInputFile('files/nord.webp')

api = CRM(login=os.getenv('login_api'), password=os.getenv('password_api'))
lk = Office(login=os.getenv('login_lk'), password=os.getenv('password_lk'))


@router.message(CommandStart())
@check_referal
async def start_message(message: types.Message, session: AsyncSession, state: FSMContext, referal_data: dict):
    '''Сообщение при старте бота'''
    await state.set_state(Form.ref)
    await state.update_data(**referal_data)
    
    client = await Customers.find(message.chat.id, db=session)
    if client:
        await state.clear()
        await message.answer(text=f'С возвращением, {message.chat.first_name}!', reply_markup=keyboard_main)
    else:
        button_phone = types.KeyboardButton(text="Телефон",
                                            request_contact=True)
        keyboard = types.ReplyKeyboardMarkup(keyboard=[[button_phone]],
                                             resize_keyboard=True)
        await message.answer(text=messages.get('start_text_1').format(username=message.chat.first_name))
        await message.answer(text=messages.get('start_text_2') + '\n' + messages.get('start_text_3'), 
                             reply_markup=keyboard, parse_mode='HTML')


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
            await message.answer('Ваш номер уже зарегистрирован!', reply_markup=clean_keyboard)
            await message.answer('Выбрете раздел:', reply_markup=keyboard_main)
        else:
            full_name = f'{message.from_user.first_name} {message.from_user.last_name or ""}'
            client_db = await Customers.find(message.chat.id, session)
            if not client_db:
                new_client = api.create(
                    full_name, phone_number, message.chat.id)

                await Customers.create(
                    session, message.chat.id, new_client.get('id'), full_name,
                    phone_number=phone_number, place_id=data.get('place_id'), referal_id=data.get('user_id'))

                lk.create_token(new_client.get('id'), phone_number)
                lk.add_credit(new_client.get('id'), 100)

            await state.clear()
            await message.answer('Успешная регистрация!', reply_markup=clean_keyboard)
            await message.answer('Выбрете раздел:', reply_markup=keyboard_main)
    await state.clear()


@router.callback_query(F.data == "back")
@login_required_callback
async def show_menu(call: types.CallbackQuery, session: AsyncSession, client: Customers, state: FSMContext, *args, **kwargs):
    await state.clear()
    await call.message.delete()
    await call.message.answer('Выбрете новый раздел', reply_markup=keyboard_main)


@router.callback_query(F.data == "about")
async def show_about(call: types.CallbackQuery, *args, **kwargs):
    await call.message.delete()
    await call.message.answer(text=messages.get('about'), reply_markup=keyboard_back, parse_mode='HTML')



@router.callback_query(F.data == "menu")
@login_required_callback
async def show_menu(call: types.CallbackQuery, *args, **kwargs):
    await call.message.delete()
    await call.message.answer_photo(
        photo=photo_nord, caption='Выберите кофейню:', reply_markup=keyboard_menu,
    )
    # await call.message.edit_text('Выберите кофейню:', reply_markup=keyboard_menu)


@router.callback_query(F.data == 'qr')
@login_required_callback
async def show_qr(call: types.CallbackQuery, session: AsyncSession, client: Customers, *args, **kwargs):
    qr = api.qr_code(client.phone_number)

    await call.message.delete()
    await call.message.answer_photo(photo=qr, reply_markup=keyboard_back)


@router.callback_query(F.data == 'balance')
@login_required_callback
async def show_balance(call: types.CallbackQuery, session: AsyncSession, client: Customers, *args, **kwargs):
    balance = api.get_balance(client.phone_number)

    await call.message.delete()
    await call.message.answer_photo(photo=photo_nord, caption=f'Ваш баланс: {balance} баллов', reply_markup=keyboard_back)


@router.callback_query(F.data == 'invite')
@login_required_callback
async def ref_account(call: types.CallbackQuery, session: AsyncSession, client: Customers):
    user_id = encode_user_id(int(client.id))
    link = await create_start_link(call.bot, user_id)
    await call.message.delete()
    await call.message.answer_photo(
        photo=photo_nord,
        caption=f'Ссылка для приглашения!\n<b><code>{link}</code></b>\n(нажмите на ссылку, чтобы скопировать)', 
        reply_markup=keyboard_back, parse_mode='HTML')


@router.callback_query(F.data == 'how_to_collect')
@login_required_callback
async def how_to_collect(call: types.CallbackQuery, *args, **kwargs):
    await call.message.delete()
    await call.message.answer(
        messages.get('start_text_1').format(username=call.message.chat.first_name) \
            + '\n' + messages.get('start_text_2'), 
        reply_markup=keyboard_back, parse_mode='HTML')


@router.callback_query(F.data == 'address')
async def address(call: types.CallbackQuery, *args, **kwargs):
    await call.message.delete()
    await call.message.answer_photo(photo=photo_nord, 
                                    caption=messages.get('address'), reply_markup=keyboard_back, parse_mode='HTML')


@router.callback_query(F.data == 'ask')
@login_required_callback
async def ask(call: types.CallbackQuery, *args,  state: FSMContext, **kwargs):
    await state.set_state(AskForm.ask)
    await call.message.delete()

    await call.message.answer_photo(photo=photo_nord, caption='Напишите ваш вопрос:', reply_markup=keyboard_back)


@router.message(AskForm.ask)
@login_required
async def ask_run(message: types.Message, session: AsyncSession, client: Customers, state: FSMContext, *args, **kwargs):
    admin = await Customers.find_by_phone_number(9969290700, session)
    await message.bot.send_message(
        admin.telegram_id, 
        f'Получен вопрос от {client.name} (контакт: {client.phone_number}):\n{message.text}')
    await state.clear()
    await message.answer('Ваш вопрос принят!')
    await message.answer('Пожалуйста, ожидайте ответа', reply_markup=keyboard_back)



@router.callback_query(F.data == 'social')
async def social(call: types.CallbackQuery, *args, **kwargs):
    text = "<b>Социальные сети:</b>"
    await call.message.delete()
    await call.message.answer_photo(photo=photo_nord, caption=text, reply_markup=keyboard_social, parse_mode='HTML')

@router.callback_query(F.data == 'review')
@login_required_callback
async def review(call: types.CallbackQuery, *args, **kwargs):
    text = "<b>Оставить отзыв:</b>"
    await call.message.delete()
    await call.message.answer_photo(photo=photo_nord, caption=text, reply_markup=keyboard_review, parse_mode='HTML')


@router.message(Command('placeQR'))
async def place_qr(message: types.Message, session: AsyncSession):
    
    places = await session.scalars(select(Places))
    for place in places.all():
        await message.answer(text=place.name)
        crypt = encode_json({'place': place.id})
        link = await create_start_link(message.bot, '')
        await message.answer(text=link + crypt)