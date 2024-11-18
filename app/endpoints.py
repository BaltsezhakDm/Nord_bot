import os
import yaml
import json

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.deep_linking import create_start_link
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api import CRM, Office
from model import Customers, Places, LogEntry
from fsm import Form, AskForm, MessageForm
from utils import encode_user_id, encode_json, check_referal
from logger import setup_logger
from auth import login_required_callback, login_required, admin_required
from tasks import send_to_queue
from keyboards import (
    keyboard_main, keyboard_back, keyboard_menu,
    keyboard_social, keyboard_review, clean_keyboard,
    key_menu, keyboard_confirm,
)
from db import r

logger = setup_logger()
router = Router(name=__name__)

with open('app/messages.yaml', 'r', encoding='utf-8') as f:
    messages = yaml.safe_load(f)

photo_nord = FSInputFile('files/nord.webp')
menu_img = FSInputFile('files/menu.webp')
about_img = FSInputFile('files/about.webp')
referal_img = FSInputFile('files/referal.webp')
address_img = FSInputFile('files/address.webp')
social_img = FSInputFile('files/about.webp')
review_img = FSInputFile('files/review.webp')
question_img = FSInputFile('files/question.webp')
balance_img = FSInputFile('files/balance.webp')

api = CRM(login=os.getenv('login_api'), password=os.getenv('password_api'))
lk = Office(login=os.getenv('login_lk'), password=os.getenv('password_lk'))


@router.message(CommandStart())
@check_referal
async def start_message(message: types.Message, session: AsyncSession, state: FSMContext, referal_data: dict):
    '''Сообщение при старте бота'''
    await state.set_state(Form.ref)
    await state.update_data(**referal_data)
    await state.update_data(message_id=message.message_id)

    client = await Customers.find(message.chat.id, db=session)

    if client:
        await state.clear()
        message = await message.answer(
            f'С возвращением, {message.chat.first_name}!',
            reply_markup=clean_keyboard,
            )
        await message.bot.send_photo(
            message.chat.id,
            caption=f'Выберите раздел',
            photo=photo_nord,
            reply_markup=keyboard_main,
            parse_mode='HTML',
        )
    else:
        button_phone = types.KeyboardButton(text="Телефон",
                                            request_contact=True)
        keyboard = types.ReplyKeyboardMarkup(keyboard=[[button_phone]],
                                             resize_keyboard=True)
        
        text = messages.get('start_text_1').format(username=message.chat.first_name)
        text += '\n' + messages.get('start_text_2')
        text += '\n\n' + messages.get('start_text_3')

        await message.bot.send_photo(
            message.chat.id,
            caption=text,
            photo=photo_nord,
            reply_markup=keyboard,
            parse_mode='HTML',
        )

#kos place tg anal
@router.message(F.contact)
async def contact(message: types.Message, session: AsyncSession, state: FSMContext):
    if message.contact:
        await state.set_state(Form.number)

        data = await state.get_data()
        print(data)

        phone_number = int(message.contact.phone_number[-10:])
        client = api.find_client(phone_number)
        if client:
            await Customers.create(
                session,
                message.chat.id,
                int(client['id']),
                f"{client.get('firstName')} {client.get('lastName')}",
                phone_number=phone_number,
                place_id=data.get('place_id'),
                referal_id=data.get('user_id'),
            )
            if client['tokens'] == [] or str(phone_number) not in [token['key'] for token in client['tokens']]:
                lk.create_token(client.get('id'), phone_number)

            await state.clear()
            await message.answer(text='Ваш номер уже зарегистрирован!', reply_markup=clean_keyboard)
            await message.bot.send_photo(
                chat_id=message.chat.id,
                photo=photo_nord,
                caption='Выбрете раздел:',
                reply_markup=keyboard_main
            )

        else:
            full_name = f'{message.from_user.first_name} {message.from_user.last_name or ""}'
            client_db = await Customers.find(message.chat.id, session)
            if not client_db:
                new_client = api.create(
                    full_name,
                    phone_number,
                    message.chat.id,
                )

                await Customers.create(
                    session,
                    message.chat.id,
                    new_client.get('id'),
                    full_name,
                    phone_number=phone_number,
                    place_id=data.get('place_id'),
                    referal_id=data.get('user_id'),
                )

                lk.create_token(new_client.get('id'), phone_number)
                lk.add_credit(new_client.get('id'), 100)

                log_entry = LogEntry.create_log(
                    user_id=message.chat.id,
                    command='register new customer in qresto',
                    status='Success',
                    error_message=None
                )

                if data.get('user_id'):
                    send_to_queue(data.get('user_id'))
                    log_entry.command = f'register new customer in qresto with referal {data.get("user_id")}'

                session.add(log_entry)
                await session.commit()

            await state.clear()
            await message.answer('Успешная регистрация!', reply_markup=clean_keyboard)
            await message.bot.send_photo(
                chat_id=message.chat.id,
                photo=photo_nord,
                caption='Выбрете раздел:',
                reply_markup=keyboard_main
            )
    await state.clear()


@router.callback_query(F.data == "back")
@login_required_callback
async def show_menu(call: types.CallbackQuery, session: AsyncSession, client: Customers, state: FSMContext, *args, **kwargs):
    await state.clear()

    await call.message.edit_media(
        types.InputMediaPhoto(
            media=photo_nord,
            caption='Выберете новый раздел',
            parse_mode='HTML',
        ),
        reply_markup=keyboard_main,
    )


@router.callback_query(F.data == "about")
async def show_about(call: types.CallbackQuery, *args, **kwargs):

    await call.message.edit_media(
        types.InputMediaPhoto(
            media=about_img,
            caption=messages.get('about'),
            parse_mode='HTML',
        ),
        reply_markup=keyboard_back
    )


@router.callback_query(F.data == "menu")
@login_required_callback
async def show_menu(call: types.CallbackQuery, *args, **kwargs):

    await call.message.edit_media(
        types.InputMediaPhoto(
            media=menu_img,
            caption='Выберите кофейню:',
            parse_mode='HTML',
        ),
        reply_markup=keyboard_menu,
    )


@router.callback_query(F.data == 'qr')
@login_required_callback
async def show_qr(call: types.CallbackQuery, session: AsyncSession, client: Customers, *args, **kwargs):
    qr = api.qr_code(client.phone_number)

    await call.message.edit_media(
        types.InputMediaPhoto(
            media=qr,
            caption='Qr код',
            parse_mode='HTML',
        ),
        reply_markup=keyboard_back,
    )


@router.callback_query(F.data == 'balance')
@login_required_callback
async def show_balance(call: types.CallbackQuery, session: AsyncSession, client: Customers, *args, **kwargs):
    balance = api.get_balance(client.phone_number)

    await call.message.edit_media(
        types.InputMediaPhoto(
            media=balance_img,
            caption=f'Ваш баланс: {balance} баллов',
            parse_mode='HTML',
        ),
        reply_markup=keyboard_back,
    )


@router.callback_query(F.data.contains('history'))
@login_required_callback
async def show_history(call: types.CallbackQuery, session: AsyncSession, client: Customers, *args, **kwargs):
    '''Вывод истории транзакций пользователя'''

    if r.get(f'history:{client.id}'):
        history = json.loads(r.get(f'history:{client.id}'))
    else:
        history = api.get_history(client.phone_number)
        r.set(f'history:{client.id}', json.dumps(history), ex=120)
    page_command = call.data.split('&page=')
    page = int(page_command[1]) if len(page_command) == 2 else 1

    if len(history) > 6 and isinstance(history, list):
        pages_count = len(history) // 6 + 1
        left = page-1 if page != 1 else pages_count
        right = page+1 if page != pages_count else 1
        left_button = types.InlineKeyboardButton(
            text="←", callback_data=f'history&page={left}')
        page_button = types.InlineKeyboardButton(
            text=f"{str(page)}/{str(pages_count)}", callback_data='_')
        right_button = types.InlineKeyboardButton(
            text="→", callback_data=f'history&page={right}')
        buttons = types.InlineKeyboardMarkup(
            inline_keyboard=[(left_button, page_button, right_button), [key_menu]])

        if page == 1:
            await call.message.edit_media(
                types.InputMediaPhoto(
                    media=balance_img,
                    caption='{}'.format(''.join(history[(page-1)*6:page*6])),
                    parse_mode='HTML',
                ),
                reply_markup=buttons,
            )
        else:
            await call.message.edit_caption(
                caption='{}'.format(''.join(history[(page-2)*6:page*6])),
                parse_mode='HTML',
                reply_markup=buttons,
            )

    else:
        await call.message.edit_media(
            types.InputMediaPhoto(
                media=balance_img,
                caption='{}'.format(''.join(history)),
                parse_mode='HTML',
            ),
            reply_markup=keyboard_back,
        )


@router.callback_query(F.data == 'invite')
@login_required_callback
async def ref_account(call: types.CallbackQuery, session: AsyncSession, client: Customers):
    user_id = encode_user_id(int(client.id))
    link = await create_start_link(call.bot, user_id)

    await call.message.edit_media(
        types.InputMediaPhoto(
            media=referal_img,
            caption=f'Пригласи друга и после его первой покупки получи 100 бонусов (начисление происходит в течение 12 часов)!\n<b><code>{link}</code></b>\n(нажмите на ссылку, чтобы скопировать)',
            parse_mode='HTML',
        ),
        reply_markup=keyboard_back,
    )


@router.callback_query(F.data == 'how_to_collect')
@login_required_callback
async def how_to_collect(call: types.CallbackQuery, *args, **kwargs):
    message = messages.get('start_text_1').format(username=call.message.chat.first_name) \
        + '\n' + messages.get('start_text_2')

    await call.message.edit_media(
        types.InputMediaPhoto(
            media=referal_img,
            caption=message,
            parse_mode='HTML',
        ),
        reply_markup=keyboard_back,
    )


@router.callback_query(F.data == 'address')
async def address(call: types.CallbackQuery, *args, **kwargs):

    await call.message.edit_media(
        types.InputMediaPhoto(
            media=address_img,
            caption=messages.get('address'),
            parse_mode='HTML',
        ),
        reply_markup=keyboard_back,
    )


@router.callback_query(F.data == 'ask')
@login_required_callback
async def ask(call: types.CallbackQuery, *args,  state: FSMContext, **kwargs):
    await state.set_state(AskForm.ask)


    await call.message.edit_media(
        types.InputMediaPhoto(
            media=question_img,
            caption='Напишите ваш вопрос:',
            parse_mode='HTML',
        ),
        reply_markup=keyboard_back,
    )


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

    await call.message.edit_media(
        types.InputMediaPhoto(
            media=social_img,
            caption=text,
            parse_mode='HTML',
        ),
        reply_markup=keyboard_social,
    )


@router.callback_query(F.data == 'review')
@login_required_callback
async def review(call: types.CallbackQuery, *args, **kwargs):
    text = "<b>Оставить отзыв:</b>"

    await call.message.edit_media(
        types.InputMediaPhoto(
            media=review_img,
            caption=text,
            parse_mode='HTML',
        ),
        reply_markup=keyboard_review,
    )


@router.message(Command('placeQR'))
async def place_qr(message: types.Message, session: AsyncSession):

    places = await session.scalars(select(Places))
    for place in places.all():
        await message.answer(text=place.name)
        crypt = encode_json({'place': place.id})
        link = await create_start_link(message.bot, '')
        await message.answer(text=link + crypt)


@router.message(Command('sendMessage'))
@admin_required
async def test(message: types.Message, session: AsyncSession, client: Customers, state: FSMContext, *args, **kwargs):
    await state.set_state(MessageForm.message)  # Устанавливаем состояние
    await message.answer('Введите текст рассылки:')


@router.message(MessageForm.message)
async def test_run(message: types.Message, session: AsyncSession, state: FSMContext, *args, **kwargs):
    # Сохраняем текст рассылки в FSM
    await state.update_data(message_text=message.text)

    await message.answer(
        'Подтвердите текст рассылки:\n' + message.text,
        parse_mode='HTML',
        reply_markup=keyboard_confirm,
    )

    # Переходим в состояние подтверждения
    await state.set_state(MessageForm.confirm)


@router.callback_query(MessageForm.confirm)
async def confirm_run(call: types.CallbackQuery, session: AsyncSession, state: FSMContext, *args, **kwargs):
    # Получаем данные из состояния FSM
    data = await state.get_data()
    message_text = data.get("message_text", "")

    if call.data == 'yes':
        await call.message.answer(
            f'Рассылка отправлена. Текст: \n{message_text}',
            parse_mode='HTML',
            reply_markup=keyboard_back,
        )
        for user in await session.scalars(select(Customers)):
            try:
                await call.bot.send_message(user.telegram_id, message_text)
            except Exception as e:
                logger.error(
                    f"Error sending message to user {user.telegram_id}: {e}")

        await state.clear()  # Завершаем FSM
    elif call.data == 'no':
        await call.message.answer(
            'Введите текст рассылки снова:',
            parse_mode='HTML',
            reply_markup=clean_keyboard,
        )
        # Возвращаемся в состояние ввода
        await state.set_state(MessageForm.message)
    else:  # Если нажали "Отменить"
        await call.message.answer(
            'Рассылка отменена',
            parse_mode='HTML',
            reply_markup=keyboard_back,
        )
        await state.clear()  # Завершаем FSM
    await call.answer()
