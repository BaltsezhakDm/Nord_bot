import os
import yaml
import json

import asyncio
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.deep_linking import create_start_link
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import FSInputFile, InputMediaPhoto

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from PIL import Image
import fitz

from api import CRM, Office
from model import Customers, Places, LogEntry
from fsm import Form, AskForm, MessageForm, UpdateMenuStates
from utils import encode_user_id, encode_json, check_referal
from logger import setup_logger
from auth import login_required_callback, login_required, admin_required
from tasks import send_to_queue
from keyboards import (
    keyboard_main, keyboard_back, keyboard_menu,
    keyboard_social, keyboard_review, clean_keyboard,
    key_menu, keyboard_confirm, key_borodinskaya, key_komendantskaya, kb
)
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pathlib import Path
from db import r

MENUS_DIR = Path("files/menus")

MENU_UPLOAD_LOCKS: dict[str, asyncio.Lock] = {}


PLACE_SLUG_BY_CB = {
    "menu_borodinskaya": "borodinskaya",
    "menu_komendantskaya": "komendantskaya",
    "menu_aptekarskaya": "aptekarskaya",
}

PLACE_TITLE = {
    "borodinskaya": "Бородинская",
    "komendantskaya": "Комендантский",
    "aptekarskaya": "Аптекарский",
}

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
menu_b = FSInputFile('files/menu_b.webp')
menu_k = FSInputFile('files/menu_k.webp')
menu_a = FSInputFile('files/menu_a.webp')

api = CRM(login=os.getenv('login_api'), password=os.getenv('password_api'))
lk = Office(login=os.getenv('login_lk'), password=os.getenv('password_lk'))


def ensure_place_dir(place_slug: str) -> Path:
    d = MENUS_DIR / place_slug
    d.mkdir(parents=True, exist_ok=True)
    return d

def list_pages(place_slug: str) -> list[Path]:
    d = ensure_place_dir(place_slug)
    pages = sorted(d.glob("*.webp"))
    # на случай старой схемы — если папка пустая, можно попробовать подтянуть старый файл:
    # (опционально) миграция: files/menu_b.webp -> files/menus/borodinskaya/001.webp
    return pages

def page_path(place_slug: str, page: int) -> Path:
    # 1 -> 001.webp
    return ensure_place_dir(place_slug) / f"{page:03d}.webp"


def build_menu_nav_kb(place_slug: str, page: int, total: int) -> InlineKeyboardMarkup:
    prev_page = total if page <= 1 else (page - 1)
    next_page = 1 if page >= total else (page + 1)

    # callback_data формата: menu_view:{place}:{page}
    left = InlineKeyboardButton(text="◀️", callback_data=f"menu_view:{place_slug}:{prev_page}")
    mid  = InlineKeyboardButton(text=f"{page}/{total}", callback_data="_")
    right= InlineKeyboardButton(text="▶️", callback_data=f"menu_view:{place_slug}:{next_page}")

    # кнопки переключения кофейни (как было у тебя через key_* можно оставить, но проще так)
    switch_row = [
        InlineKeyboardButton(text="Бородинская", callback_data="menu_place:borodinskaya"),
        InlineKeyboardButton(text="Комендантский", callback_data="menu_place:komendantskaya"),
        InlineKeyboardButton(text="Аптекарский", callback_data="menu_place:aptekarskaya"),
    ]

    return InlineKeyboardMarkup(inline_keyboard=[
        [left, mid, right],
        switch_row,
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu")],
    ])

kb_menu_upload = types.ReplyKeyboardMarkup(
    keyboard=[[types.KeyboardButton(text="✅ Готово"), types.KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)

def save_image_as_webp(src_path: str, dst_path: str) -> None:
    img = Image.open(src_path).convert("RGB")
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    img.save(dst_path, format="WEBP", quality=85)

def pdf_to_webp_pages(pdf_path: str, out_dir: str, start_index: int) -> int:
    """
    Рендерит ВСЕ страницы PDF в out_dir как 001.webp, 002.webp...
    Возвращает сколько страниц добавили.
    """
    pdf_doc = fitz.open(pdf_path)
    added = 0
    try:
        for i in range(pdf_doc.page_count):
            page = pdf_doc.load_page(i)
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            tmp_png = pdf_path.rsplit(".", 1)[0] + f"_{i}.png"
            pix.save(tmp_png)

            dst = os.path.join(out_dir, f"{start_index + added:03d}.webp")
            save_image_as_webp(tmp_png, dst)
            os.remove(tmp_png)
            added += 1
    finally:
        pdf_doc.close()
    return added

async def render_menu(call: types.CallbackQuery, place_slug: str, page: int = 1):
    pages = list_pages(place_slug)
    if not pages:
        await call.answer("Меню ещё не загружено", show_alert=True)
        return

    total = len(pages)
    page = max(1, min(page, total))
    path: Path = pages[page - 1]

    await call.message.edit_media(
        InputMediaPhoto(
            media=FSInputFile(str(path)),
            caption=f"Меню кофейни {PLACE_TITLE.get(place_slug, place_slug)}",
        ),
        reply_markup=build_menu_nav_kb(place_slug, page, total),
    )

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

# @router.callback_query(F.data.contains("menu_"))
# @login_required_callback
# async def show_menu_place(call: types.CallbackQuery, *args, **kwargs):
    
#     if call.data == 'menu_borodinskaya':
#         keyboard = types.InlineKeyboardMarkup(inline_keyboard = [[key_komendantskaya, key_menu]])

#         await call.message.edit_media(
#             types.InputMediaPhoto(
#                 media=menu_b,
#                 caption='Меню кофейни Бородинская',
#                 parse_mode='HTML',
#             ),
#             reply_markup=keyboard
#         )
#     if call.data == 'menu_komendantskaya':
#         keyboard = types.InlineKeyboardMarkup(inline_keyboard = [[key_borodinskaya, key_menu]])
#         await call.message.edit_media(
#             types.InputMediaPhoto(
#                 media=menu_k,
#                 caption='Меню кофейни Комендантский',
#                 parse_mode='HTML',
#             ),
#             reply_markup=keyboard
#         )
#     if call.data == 'menu_aptekarskaya':
#         keyboard = types.InlineKeyboardMarkup(inline_keyboard = [[key_borodinskaya, key_menu]])
#         await call.message.edit_media(
#             types.InputMediaPhoto(
#                 media=menu_a,
#                 caption='Меню кофеини Аптекарский',
#                 parse_mode='HTML',
#             ),
#             reply_markup=keyboard
#         )

@router.callback_query(F.data.startswith("menu_place:"))
@login_required_callback
async def show_menu_place(call: types.CallbackQuery, *args, **kwargs):
    place_slug = call.data.split(":", 1)[1]
    await render_menu(call, place_slug, page=1)


@router.callback_query(F.data.startswith("menu_view:"))
@login_required_callback
async def show_menu_page(call: types.CallbackQuery, *args, **kwargs):
    # menu_view:{place}:{page}
    _, place_slug, page_s = call.data.split(":")
    await render_menu(call, place_slug, page=int(page_s))


@router.callback_query(F.data.in_(["menu_borodinskaya", "menu_komendantskaya", "menu_aptekarskaya"]))
@login_required_callback
async def legacy_menu_place(call: types.CallbackQuery, *args, **kwargs):
    place_slug = PLACE_SLUG_BY_CB.get(call.data)
    if not place_slug:
        await call.answer("Неизвестная кофейня", show_alert=True)
        return
    await render_menu(call, place_slug, page=1)


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


@router.message(Command("update_menu"))
@admin_required
async def cmd_update_menu(message: types.Message, session: AsyncSession, client: Customers, state: FSMContext, *args, **kwargs):
    """
    Шаг 1. Пользователь вводит /update_menu — показываем кнопки выбора меню.
    """
    await state.clear()
    
    await message.answer(
        "Выберите, какое меню хотите обновить:",
        reply_markup=kb,
    )
    await state.set_state(UpdateMenuStates.choosing)


# @router.message(StateFilter(UpdateMenuStates.choosing), F.text.in_(["Аптекарский", "Коменданский", "Бородинская"]))
# async def process_menu_choice(message: types.Message, state: FSMContext):
#     """
#     Шаг 2. Пользователь нажал на одну из кнопок — запомним выбор и попросим прислать файл.
#     """
#     choice = message.text  # будет ровно один из трёх
#     # Сохраним в FSMContext выбор пользователя, чтобы потом понять, куда сохранять
#     await state.update_data(menu_choice=choice)

#     # Сними клавиатуру, больше не нужна
#     await message.answer(
#         f"Вы выбрали «{choice}». Пришлите, пожалуйста, файл с новым меню (jpg или png).",
#         reply_markup=types.ReplyKeyboardRemove(),
#     )
#     await state.set_state(UpdateMenuStates.waiting_file)


@router.message(StateFilter(UpdateMenuStates.choosing), F.text.in_(["Аптекарский", "Коменданский", "Бородинская"]))
async def process_menu_choice(message: types.Message, state: FSMContext):
    choice = message.text
    await state.update_data(menu_choice=choice)

    place_map = {
        "Аптекарский": "aptekarskaya",
        "Коменданский": "komendantskaya",
        "Бородинская": "borodinskaya",
    }
    place_slug = place_map[choice]

    # ✅ ОЧИСТКА старых страниц (чтобы новое меню начиналось с 001)
    place_dir = ensure_place_dir(place_slug)
    for p in place_dir.glob("*.webp"):
        p.unlink()

    await message.answer(
        f"Вы выбрали «{choice}».\n"
        f"Пришлите фото (jpg/png) или один/несколько PDF.\n"
        f"Можно отправлять много сообщений подряд.\n"
        f"Когда закончите — нажмите «✅ Готово».",
        reply_markup=kb_menu_upload,
    )
    await state.set_state(UpdateMenuStates.waiting_file)


@router.message(StateFilter(UpdateMenuStates.choosing))
async def invalid_choice(message: types.Message):
    """
    Если пользователь ввёл текст не из списка, попросим выбрать снова.
    """
    await message.answer("Нужно выбрать одну из кнопок: Аптекарский, Коменданский или Бородинская.")

# @router.message(StateFilter(UpdateMenuStates.waiting_file), F.content_type.in_({"photo", "document"}))
# async def process_new_file(message: types.Message, state: FSMContext):
#     """
#     Шаг 3. Пользователь прислал файл. Если это картинка (jpg/png) — конвертим и сохраняем.
#     Если это PDF — рендерим первую страницу и сохраняем как webp.
#     """
#     data = await state.get_data()
#     choice: str = data.get("menu_choice")  # выбор пользователя

#     # Словарь, куда сохраняем в зависимости от выбора:
#     mapping = {
#         "Аптекарский": "files/menu_a.webp",
#         "Коменданский": "files/menu_k.webp",
#         "Бородинская": "files/menu_b.webp",
#     }
#     target_path = mapping.get(choice)
#     if not target_path:
#         await message.answer("Не удалось определить, куда сохранять файл. Попробуйте ещё раз.")
#         await state.clear()
#         return

#     # 5.1) Решаем, что именно прислали:
#     is_pdf = False
#     if message.photo:
#         # Это обычная картинка
#         file_id = message.photo[-1].file_id
#         orig_filename = f"{file_id}.jpg"
#     else:
#         # Это document. Проверяем MIME и расширение
#         doc = message.document
#         mime = doc.mime_type or ""
#         name = doc.file_name or ""
#         # Если PDF (mime application/pdf или имя заканчивается на .pdf)
#         if mime == "application/pdf" or name.lower().endswith(".pdf"):
#             is_pdf = True
#             file_id = doc.file_id
#             orig_filename = name if name.lower().endswith(".pdf") else f"{file_id}.pdf"
#         else:
#             # Если не PDF и не картинка изначально (PNG/JPEG)
#             if not mime.startswith("image/"):
#                 await message.answer("Нужно прислать изображение (jpg/png) или PDF-файл.")
#                 return
#             file_id = doc.file_id
#             orig_filename = name

#     # 5.2) Скачиваем файл во временную папку tmp/
#     os.makedirs("tmp", exist_ok=True)
#     tmp_path = os.path.join("tmp", orig_filename)

#     file = await message.bot.get_file(file_id)
#     await message.bot.download_file(file.file_path, destination=tmp_path)

#     # 5.3) Конвертация
#     try:
#         # Если это PDF, рендерим первую страницу через PyMuPDF
#         if is_pdf:
#             # Открываем PDF
#             pdf_doc = fitz.open(tmp_path)
#             if pdf_doc.page_count < 1:
#                 raise RuntimeError("PDF пустой или не удалось прочитать страницы")
#             page = pdf_doc.load_page(0)  # первая страница (индекс 0)
#             # Рендерим страницу в pixmap (по умолчанию 72 DPI)
#             mat = fitz.Matrix(2, 2)  # можно увеличить DPI, например, 144; здесь увеличиваем в 2 раза
#             pix = page.get_pixmap(matrix=mat, alpha=False)
#             # Сохраняем временный PNG: fitz может отдавать .png-байты
#             tmp_img_path = tmp_path.rsplit(".", 1)[0] + ".png"
#             pix.save(tmp_img_path)

#             # Теперь открываем через PIL и конвертируем в WebP
#             img = Image.open(tmp_img_path).convert("RGB")
#             os.makedirs(os.path.dirname(target_path), exist_ok=True)
#             img.save(target_path, format="WEBP", quality=85)

#             # Удаляем промежуточный PNG
#             os.remove(tmp_img_path)
#             pdf_doc.close()

#         else:
#             # Обычное изображение (jpg/png)
#             img = Image.open(tmp_path).convert("RGB")
#             os.makedirs(os.path.dirname(target_path), exist_ok=True)
#             img.save(target_path, format="WEBP", quality=85)

#     except Exception as e:
#         await message.answer(f"Не удалось сконвертировать файл: {e}")
#         # Чистим временный файл
#         try:
#             os.remove(tmp_path)
#         except:
#             pass
#         await state.clear()
#         return

#     # 5.4) Удаляем временный файл PDF или исходное изображение
#     try:
#         os.remove(tmp_path)
#     except:
#         pass

#     # 5.5) Подтверждаем и показываем получившийся WebP (опционально)
#     await message.answer(f"Меню «{choice}» обновлено успешно! Вот как оно теперь выглядит:")
#     await message.answer_photo(FSInputFile(target_path))

#     # Сбрасываем состояние
#     await state.clear()

@router.message(StateFilter(UpdateMenuStates.waiting_file), F.content_type.in_({"photo", "document"}))
async def process_new_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    choice: str = data.get("menu_choice")

    place_map = {
        "Аптекарский": "aptekarskaya",
        "Коменданский": "komendantskaya",
        "Бородинская": "borodinskaya",
    }
    place_slug = place_map.get(choice)
    if not place_slug:
        await message.answer("Не удалось определить кофейню. Начните заново: /update_menu",
                             reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
        return

    out_dir = str(ensure_place_dir(place_slug))

    # определить file_id + тип
    is_pdf = False
    if message.photo:
        file_id = message.photo[-1].file_id
        orig_filename = f"{file_id}.jpg"
    else:
        doc = message.document
        mime = doc.mime_type or ""
        name = doc.file_name or ""
        if mime == "application/pdf" or name.lower().endswith(".pdf"):
            is_pdf = True
            file_id = doc.file_id
            orig_filename = name if name.lower().endswith(".pdf") else f"{file_id}.pdf"
        else:
            if not mime.startswith("image/"):
                await message.answer("Нужно прислать изображение (jpg/png) или PDF.")
                return
            file_id = doc.file_id
            orig_filename = name or f"{file_id}.img"

    os.makedirs("tmp", exist_ok=True)
    tmp_path = os.path.join("tmp", orig_filename)

    file = await message.bot.get_file(file_id)
    await message.bot.download_file(file.file_path, destination=tmp_path)

    # ✅ LOCK на конкретную кофейню, чтобы next_index не считался параллельно
    lock = MENU_UPLOAD_LOCKS.setdefault(place_slug, asyncio.Lock())

    try:
        async with lock:
            existing = list_pages(place_slug)
            next_index = len(existing) + 1

            if is_pdf:
                added = pdf_to_webp_pages(tmp_path, out_dir=out_dir, start_index=next_index)
            else:
                dst = os.path.join(out_dir, f"{next_index:03d}.webp")
                save_image_as_webp(tmp_path, dst)
                added = 1

            total_now = len(list_pages(place_slug))

        await message.answer(f"Добавлено страниц: {added}. Всего страниц сейчас: {total_now}.")
    except Exception as e:
        await message.answer(f"Не удалось обработать файл: {e}")
    finally:
        try:
            os.remove(tmp_path)
        except:
            pass



@router.message(StateFilter(UpdateMenuStates.waiting_file), F.text == "✅ Готово")
async def finish_menu_upload(message: types.Message, state: FSMContext):
    data = await state.get_data()
    choice: str = data.get("menu_choice")

    place_map = {
        "Аптекарский": "aptekarskaya",
        "Коменданский": "komendantskaya",
        "Бородинская": "borodinskaya",
    }
    place_slug = place_map.get(choice)
    pages = list_pages(place_slug) if place_slug else []

    await state.clear()
    await message.answer("Готово ✅", reply_markup=types.ReplyKeyboardRemove())

    if not pages:
        await message.answer("Но страниц меню не найдено (ничего не загрузили).")
        return

    # показываем первую страницу
    await message.answer_photo(
        FSInputFile(str(pages[0])),
        caption=f"Меню кофейни {PLACE_TITLE.get(place_slug, place_slug)}",
        reply_markup=build_menu_nav_kb(place_slug, 1, len(pages))
    )

@router.message(StateFilter(UpdateMenuStates.waiting_file), F.text == "❌ Отмена")
async def cancel_menu_upload(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=types.ReplyKeyboardRemove())



@router.message(StateFilter(UpdateMenuStates.waiting_file))
async def invalid_file(message: types.Message):
    await message.answer("Пожалуйста, пришлите фото (jpg/png) или PDF. Затем нажмите «✅ Готово».")
