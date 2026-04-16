import os
import yaml
import json
import asyncio
import logging
import aiohttp
from pathlib import Path
from typing import Optional

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.deep_linking import create_start_link
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import FSInputFile, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from PIL import Image
import fitz

from api import CRM, Office, load_cookies
from model import Customers, Places, LogEntry
from fsm import Form, AskForm, MessageForm, UpdateMenuStates
from utils import encode_user_id, encode_json, check_referal, get_connector
from keyboards import (
    keyboard_main, keyboard_back, keyboard_menu,
    keyboard_social, keyboard_review, clean_keyboard,
    key_menu, keyboard_confirm, key_borodinskaya, key_komendantskaya, kb
)
from db import r
from settings import settings

logger = logging.getLogger(__name__)
router = Router(name=__name__)

# Загрузка сообщений
try:
    with open('app/messages.yaml', 'r', encoding='utf-8') as f:
        messages = yaml.safe_load(f)
except Exception as e:
    logger.error(f"Failed to load messages.yaml: {e}")
    messages = {}

# Ресурсы
MENUS_DIR = Path("files/menus")
PHOTO_NORD = FSInputFile('files/nord.webp')
MENU_IMG = FSInputFile('files/menu.webp')
ABOUT_IMG = FSInputFile('files/about.webp')
REFERAL_IMG = FSInputFile('files/referal.webp')
ADDRESS_IMG = FSInputFile('files/address.webp')
SOCIAL_IMG = FSInputFile('files/about.webp')
REVIEW_IMG = FSInputFile('files/review.webp')
QUESTION_IMG = FSInputFile('files/question.webp')
BALANCE_IMG = FSInputFile('files/balance.webp')

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

MENU_UPLOAD_LOCKS: dict[str, asyncio.Lock] = {}

# Глобальные сессии будут инициализированы в middleware или при первом запросе
# Но лучше передавать их явно. Для простоты будем использовать одну сессию на бота
# или создавать временные. В данном случае, так как бот асинхронный,
# мы добавим создание сессии CRM/Office в роутеры.

async def notify_admins_about_referral(bot, user_id):
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f'Пополнить бонусы для пользователя ID: {user_id}'
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id} about referral: {e}")


async def get_api_clients():
    session = aiohttp.ClientSession(connector=get_connector())
    api_client = CRM(login=settings.LOGIN_API, password=settings.PASSWORD_API, session=session)
    lk_client = Office(login=settings.LOGIN_LK, password=settings.PASSWORD_LK, session=session)
    await load_cookies(session, lk_client.cookie_file)
    return api_client, lk_client, session

# Вспомогательные функции для меню
def ensure_place_dir(place_slug: str) -> Path:
    d = MENUS_DIR / place_slug
    d.mkdir(parents=True, exist_ok=True)
    return d

def list_pages(place_slug: str) -> list[Path]:
    d = ensure_place_dir(place_slug)
    return sorted(d.glob("*.webp"))

def build_menu_nav_kb(place_slug: str, page: int, total: int) -> InlineKeyboardMarkup:
    prev_page = total if page <= 1 else (page - 1)
    next_page = 1 if page >= total else (page + 1)

    left = InlineKeyboardButton(text="◀️", callback_data=f"menu_view:{place_slug}:{prev_page}")
    mid  = InlineKeyboardButton(text=f"{page}/{total}", callback_data="_")
    right= InlineKeyboardButton(text="▶️", callback_data=f"menu_view:{place_slug}:{next_page}")

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

# Обработчики
@router.message(CommandStart())
@check_referal
async def start_message(message: types.Message, session: AsyncSession, state: FSMContext, referal_data: dict):
    await state.set_state(Form.ref)
    await state.update_data(**referal_data)

    client = await Customers.find(message.chat.id, db=session)

    if client:
        await state.clear()
        await message.answer(f'С возвращением, {message.chat.first_name}!', reply_markup=clean_keyboard)
        await message.bot.send_photo(
            message.chat.id,
            caption='Выберите раздел',
            photo=PHOTO_NORD,
            reply_markup=keyboard_main,
            parse_mode='HTML',
        )
    else:
        button_phone = types.KeyboardButton(text="Телефон", request_contact=True)
        keyboard = types.ReplyKeyboardMarkup(keyboard=[[button_phone]], resize_keyboard=True)
        
        text = messages.get('start_text_1', "").format(username=message.chat.first_name)
        text += '\n' + messages.get('start_text_2', "")
        text += '\n\n' + messages.get('start_text_3', "")

        await message.bot.send_photo(
            message.chat.id,
            caption=text,
            photo=PHOTO_NORD,
            reply_markup=keyboard,
            parse_mode='HTML',
        )

@router.message(F.contact)
async def contact(message: types.Message, session: AsyncSession, state: FSMContext):
    if not message.contact:
        return

    await state.set_state(Form.number)
    data = await state.get_data()
    phone_number = int(message.contact.phone_number[-10:])

    async with aiohttp.ClientSession(connector=get_connector()) as http_session:
        api_client = CRM(settings.LOGIN_API, settings.PASSWORD_API, http_session)
        lk_client = Office(settings.LOGIN_LK, settings.PASSWORD_LK, http_session)
        await load_cookies(http_session, lk_client.cookie_file)

        client = await api_client.find_client(phone_number)
        if client:
            await Customers.create(
                session,
                message.chat.id,
                int(client['id']),
                f"{client.get('firstName', '')} {client.get('lastName', '')}".strip(),
                phone_number=phone_number,
                place_id=data.get('place_id'),
                referal_id=data.get('user_id'),
            )
            tokens = client.get('tokens', [])
            if not tokens or str(phone_number) not in [token.get('key') for token in tokens]:
                await lk_client.create_token(client.get('id'), phone_number)

            await state.clear()
            await message.answer(text='Ваш номер уже зарегистрирован!', reply_markup=clean_keyboard)
            await message.bot.send_photo(
                chat_id=message.chat.id,
                photo=PHOTO_NORD,
                caption='Выберите раздел:',
                reply_markup=keyboard_main
            )
        else:
            full_name = f'{message.from_user.first_name} {message.from_user.last_name or ""}'.strip()
            client_db = await Customers.find(message.chat.id, session)
            if not client_db:
                new_client = await api_client.create(full_name, phone_number, message.chat.id)
                if new_client and 'id' in new_client:
                    await Customers.create(
                        session,
                        message.chat.id,
                        new_client.get('id'),
                        full_name,
                        phone_number=phone_number,
                        place_id=data.get('place_id'),
                        referal_id=data.get('user_id'),
                    )
                    await lk_client.create_token(new_client.get('id'), phone_number)
                    await lk_client.add_credit(new_client.get('id'), 100)

                    if data.get('user_id'):
                        asyncio.create_task(notify_admins_about_referral(message.bot, data.get('user_id')))

            await state.clear()
            await message.answer('Успешная регистрация!', reply_markup=clean_keyboard)
            await message.bot.send_photo(
                chat_id=message.chat.id,
                photo=PHOTO_NORD,
                caption='Выберите раздел:',
                reply_markup=keyboard_main
            )

@router.callback_query(F.data == "back")
async def back_to_main(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_media(
        types.InputMediaPhoto(media=PHOTO_NORD, caption='Выберите новый раздел'),
        reply_markup=keyboard_main,
    )

@router.callback_query(F.data == "about")
async def show_about(call: types.CallbackQuery):
    await call.message.edit_media(
        types.InputMediaPhoto(media=ABOUT_IMG, caption=messages.get('about', ""), parse_mode='HTML'),
        reply_markup=keyboard_back
    )

@router.callback_query(F.data == "menu")
async def show_menu_categories(call: types.CallbackQuery):
    await call.message.edit_media(
        types.InputMediaPhoto(media=MENU_IMG, caption='Выберите кофейню:'),
        reply_markup=keyboard_menu,
    )

@router.callback_query(F.data.startswith("menu_place:"))
async def show_menu_place_cb(call: types.CallbackQuery):
    place_slug = call.data.split(":", 1)[1]
    await render_menu(call, place_slug, page=1)

@router.callback_query(F.data.startswith("menu_view:"))
async def show_menu_page_cb(call: types.CallbackQuery):
    _, place_slug, page_s = call.data.split(":")
    await render_menu(call, place_slug, page=int(page_s))

@router.callback_query(F.data.in_(["menu_borodinskaya", "menu_komendantskaya", "menu_aptekarskaya"]))
async def legacy_menu_place_cb(call: types.CallbackQuery):
    place_slug = PLACE_SLUG_BY_CB.get(call.data)
    if place_slug:
        await render_menu(call, place_slug, page=1)

@router.callback_query(F.data == 'qr')
async def show_qr_cb(call: types.CallbackQuery, session: AsyncSession):
    client = await Customers.find(call.from_user.id, session)
    if not client: return

    async with aiohttp.ClientSession(connector=get_connector()) as http_session:
        api_client = CRM(settings.LOGIN_API, settings.PASSWORD_API, http_session)
        qr = api_client.qr_code(client.phone_number)
        await call.message.edit_media(
            types.InputMediaPhoto(media=qr, caption='Ваш QR-код'),
            reply_markup=keyboard_back,
        )

@router.callback_query(F.data == 'balance')
async def show_balance_cb(call: types.CallbackQuery, session: AsyncSession):
    client = await Customers.find(call.from_user.id, session)
    if not client: return

    async with aiohttp.ClientSession(connector=get_connector()) as http_session:
        api_client = CRM(settings.LOGIN_API, settings.PASSWORD_API, http_session)
        balance = await api_client.get_balance(client.phone_number)
        await call.message.edit_media(
            types.InputMediaPhoto(media=BALANCE_IMG, caption=f'Ваш баланс: {balance} баллов'),
            reply_markup=keyboard_back,
        )

@router.callback_query(F.data.startswith('history'))
async def show_history_cb(call: types.CallbackQuery, session: AsyncSession):
    client = await Customers.find(call.from_user.id, session)
    if not client: return

    history_key = f'history:{client.id}'
    history_raw = r.get(history_key)
    if history_raw:
        history = json.loads(history_raw)
    else:
        async with aiohttp.ClientSession(connector=get_connector()) as http_session:
            api_client = CRM(settings.LOGIN_API, settings.PASSWORD_API, http_session)
            history = await api_client.get_history(client.phone_number)
            r.set(history_key, json.dumps(history), ex=120)

    page_command = call.data.split('&page=')
    page = int(page_command[1]) if len(page_command) == 2 else 1

    if history and isinstance(history, list) and len(history) > 6:
        pages_count = (len(history) + 5) // 6
        page = max(1, min(page, pages_count))

        left = page - 1 if page > 1 else pages_count
        right = page + 1 if page < pages_count else 1

        buttons = types.InlineKeyboardMarkup(inline_keyboard=[
            [
                types.InlineKeyboardButton(text="←", callback_data=f'history&page={left}'),
                types.InlineKeyboardButton(text=f"{page}/{pages_count}", callback_data='_'),
                types.InlineKeyboardButton(text="→", callback_data=f'history&page={right}'),
            ],
            [key_menu]
        ])

        history_text = ''.join(history[(page-1)*6:page*6])
        await call.message.edit_media(
            types.InputMediaPhoto(media=BALANCE_IMG, caption=history_text or "Транзакции отсутствуют"),
            reply_markup=buttons,
        )
    else:
        history_text = ''.join(history) if history else "Транзакции отсутствуют"
        await call.message.edit_media(
            types.InputMediaPhoto(media=BALANCE_IMG, caption=history_text),
            reply_markup=keyboard_back,
        )

@router.callback_query(F.data == 'invite')
async def ref_account_cb(call: types.CallbackQuery, session: AsyncSession):
    client = await Customers.find(call.from_user.id, session)
    if not client: return

    user_id_encoded = encode_user_id(int(client.id))
    link = await create_start_link(call.bot, user_id_encoded)

    await call.message.edit_media(
        types.InputMediaPhoto(
            media=REFERAL_IMG,
            caption=f'Пригласи друга и после его первой покупки получи 100 бонусов!\n<b><code>{link}</code></b>',
            parse_mode='HTML',
        ),
        reply_markup=keyboard_back,
    )

@router.callback_query(F.data == 'address')
async def address_cb(call: types.CallbackQuery):
    await call.message.edit_media(
        types.InputMediaPhoto(media=ADDRESS_IMG, caption=messages.get('address', ""), parse_mode='HTML'),
        reply_markup=keyboard_back,
    )

@router.callback_query(F.data == 'ask')
async def ask_cb(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AskForm.ask)
    await call.message.edit_media(
        types.InputMediaPhoto(media=QUESTION_IMG, caption='Напишите ваш вопрос:'),
        reply_markup=keyboard_back,
    )

@router.message(AskForm.ask)
async def ask_run(message: types.Message, session: AsyncSession, state: FSMContext):
    client = await Customers.find(message.chat.id, session)
    if not client: return

    for admin_id in settings.ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                f'Получен вопрос от {client.name} (контакт: {client.phone_number}):\n{message.text}'
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

    await state.clear()
    await message.answer('Ваш вопрос принят! Пожалуйста, ожидайте ответа.', reply_markup=keyboard_back)

@router.callback_query(F.data == 'social')
async def social_cb(call: types.CallbackQuery):
    await call.message.edit_media(
        types.InputMediaPhoto(media=SOCIAL_IMG, caption="<b>Социальные сети:</b>", parse_mode='HTML'),
        reply_markup=keyboard_social,
    )

@router.callback_query(F.data == 'review')
async def review_cb(call: types.CallbackQuery):
    await call.message.edit_media(
        types.InputMediaPhoto(media=REVIEW_IMG, caption="<b>Оставить отзыв:</b>", parse_mode='HTML'),
        reply_markup=keyboard_review,
    )

@router.message(Command('placeQR'))
async def place_qr_cmd(message: types.Message, session: AsyncSession):
    places = await session.scalars(select(Places))
    for place in places.all():
        crypt = encode_json({'place': place.id})
        link = await create_start_link(message.bot, crypt, encode=False)
        await message.answer(text=f"{place.name}: {link}")

@router.message(Command('sendMessage'))
async def send_message_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    await state.set_state(MessageForm.message)
    await message.answer('Введите текст рассылки:')

@router.message(MessageForm.message)
async def message_text_run(message: types.Message, state: FSMContext):
    await state.update_data(message_text=message.text)
    await message.answer(f'Подтвердите текст рассылки:\n{message.text}', reply_markup=keyboard_confirm)
    await state.set_state(MessageForm.confirm)

@router.callback_query(MessageForm.confirm)
async def confirm_message_cb(call: types.CallbackQuery, session: AsyncSession, state: FSMContext):
    data = await state.get_data()
    text = data.get("message_text", "")

    if call.data == 'yes':
        await call.message.answer(f'Рассылка запущена.')
        users = await session.scalars(select(Customers))
        for user in users.all():
            try:
                await call.bot.send_message(user.telegram_id, text)
            except Exception as e:
                logger.error(f"Error sending to {user.telegram_id}: {e}")
        await state.clear()
    elif call.data == 'no':
        await call.message.answer('Введите текст рассылки снова:')
        await state.set_state(MessageForm.message)
    else:
        await call.message.answer('Рассылка отменена')
        await state.clear()
    await call.answer()

@router.message(Command("update_menu"))
async def cmd_update_menu(message: types.Message, state: FSMContext):
    if message.from_user.id not in settings.ADMIN_IDS:
        return
    await state.clear()
    await message.answer("Выберите, какое меню хотите обновить:", reply_markup=kb)
    await state.set_state(UpdateMenuStates.choosing)

@router.message(StateFilter(UpdateMenuStates.choosing), F.text.in_(["Аптекарский", "Коменданский", "Бородинская"]))
async def process_menu_choice(message: types.Message, state: FSMContext):
    choice = message.text
    await state.update_data(menu_choice=choice)

    place_map = {"Аптекарский": "aptekarskaya", "Коменданский": "komendantskaya", "Бородинская": "borodinskaya"}
    place_slug = place_map[choice]

    place_dir = ensure_place_dir(place_slug)
    for p in place_dir.glob("*.webp"):
        p.unlink()

    await message.answer(
        f"Вы выбрали «{choice}». Пришлите фото или PDF. По окончании нажмите «✅ Готово».",
        reply_markup=kb_menu_upload
    )
    await state.set_state(UpdateMenuStates.waiting_file)

@router.message(StateFilter(UpdateMenuStates.waiting_file), F.content_type.in_({"photo", "document"}))
async def process_new_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    choice = data.get("menu_choice")
    place_map = {"Аптекарский": "aptekarskaya", "Коменданский": "komendantskaya", "Бородинская": "borodinskaya"}
    place_slug = place_map.get(choice)

    if not place_slug: return

    out_dir = str(ensure_place_dir(place_slug))
    is_pdf = False
    if message.photo:
        file_id = message.photo[-1].file_id
        ext = "jpg"
    else:
        doc = message.document
        file_id = doc.file_id
        is_pdf = (doc.mime_type == "application/pdf" or doc.file_name.lower().endswith(".pdf"))
        ext = "pdf" if is_pdf else "img"

    tmp_path = f"tmp/{file_id}.{ext}"
    os.makedirs("tmp", exist_ok=True)

    file = await message.bot.get_file(file_id)
    await message.bot.download_file(file.file_path, tmp_path)

    lock = MENU_UPLOAD_LOCKS.setdefault(place_slug, asyncio.Lock())
    async with lock:
        existing = list_pages(place_slug)
        next_index = len(existing) + 1
        if is_pdf:
            added = pdf_to_webp_pages(tmp_path, out_dir, next_index)
        else:
            dst = os.path.join(out_dir, f"{next_index:03d}.webp")
            save_image_as_webp(tmp_path, dst)
            added = 1

    os.remove(tmp_path)
    await message.answer(f"Добавлено страниц: {added}. Всего: {len(list_pages(place_slug))}")

@router.message(StateFilter(UpdateMenuStates.waiting_file), F.text == "✅ Готово")
async def finish_menu_upload(message: types.Message, state: FSMContext):
    data = await state.get_data()
    choice = data.get("menu_choice")
    place_map = {"Аптекарский": "aptekarskaya", "Коменданский": "komendantskaya", "Бородинская": "borodinskaya"}
    place_slug = place_map.get(choice)
    pages = list_pages(place_slug)

    await state.clear()
    await message.answer("Обновление завершено", reply_markup=types.ReplyKeyboardRemove())

    if pages:
        await message.answer_photo(
            FSInputFile(str(pages[0])),
            caption=f"Меню {choice}",
            reply_markup=build_menu_nav_kb(place_slug, 1, len(pages))
        )

@router.callback_query(F.data == "back")
async def back_cb(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_media(
        types.InputMediaPhoto(media=PHOTO_NORD, caption='Выберите раздел'),
        reply_markup=keyboard_main
    )
