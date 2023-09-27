import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.utils import executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage

import config
import api
from model import find_customer, add_customer

logging.basicConfig(level=logging.INFO)

bot = Bot(token=config.TOKEN)
admin_bot = Bot(token=config.adminTOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


key1 = types.KeyboardButton(text='Баланс')
key2 = types.KeyboardButton(text='История')
key3 = types.KeyboardButton(text='QR код')
keyboard_main = types.ReplyKeyboardMarkup().add(key1, key2, key3)
keyboard_main.resize_keyboard = True


@dp.message_handler(commands=['start'])
async def show_hello(message: types.Message):
    '''Сообщение при старте бота'''

    # поиск в локальной БД гостя по telegram_id
    if find_customer(message.chat.id):
        await message.answer(text='С возвращением, {}'.format(message.chat.first_name), reply_markup=keyboard_main)
    else:
        key1 = types.KeyboardButton(
            text='Новости + бонусы за них', callback_data='set_news')
        key2 = types.KeyboardButton(
            text='Только система лояльности', callback_data='only_bonuses')
        button_phone = types.KeyboardButton(text="Телефон",
                                            request_contact=True)
        keyboard = types.ReplyKeyboardMarkup(
            resize_keyboard=True).add(button_phone)
        text_first = '''Здравствуйте, {}!
Мы рады знакомству с тобой!
Добро пожаловать в систему лояльности кофейни KOS.PLACE.'''
        text_second = '''Мы начисляем 5% с каждого чека на ваш бонусный счет и в дальнейшем можем списать до 50% суммы чека из ваших бонусов.
В данном чате вы будете видеть зачисления\списания бонусов и ваш баланс.
<b>Нажмите на кнопку "Телефон" для входа или регистрации.</b>'''
        # text_thrid = '''Также, в этом чате мы будем награждать вас бонусами и отправлять для вас только полезную информацию'''
        await message.answer(text=text_first.format(message.chat.first_name))
        await message.answer(text=text_second, reply_markup=keyboard, parse_mode='HTML')
        # await message.answer(text=text_thrid, reply_markup=keyboard)


@dp.message_handler(content_types=['contact'])
async def contact(message: types.Message):
    if message.contact is not None:
        phone_number = message.contact.phone_number
        guest = api.CustomerOperation()
        get_guest = guest.getCustomer(phone_number=phone_number[1:])
        if 'errorCode' in get_guest.keys():
            customer = guest.createCustomer(firstName=message.chat.first_name, telegram_id=message.chat.id, phone_number=phone_number[1:])
            add_customer(telegram_id=message.chat.id, qresto_id=customer['customer']['id'], 
                         name=message.chat.first_name, phone_number=phone_number[1:], news=False)
            await message.answer('Успешная регистрация!', reply_markup=keyboard_main)
        else:
            tokens = guest.filterCustomer(phone_number[1:])['customers'][0]['tokens']
            if len(tokens) == 0 or phone_number[1:] not in [token['key'] for token in tokens]:
                guest.addToken(get_guest['id'], phone_number[1:])
            add_customer(telegram_id=message.chat.id,
                qresto_id=get_guest['id'], name=message.chat.first_name, news=False, phone_number=phone_number[1:])
            await message.answer('Ваш номер уже зарегистрирован!', reply_markup=keyboard_main)


@dp.message_handler(lambda message: message.text == '/history' or message.text == 'История')
async def show_history(message: types.Message, page=1, previous_message=None):
    '''Вывод истории транзакций пользователя'''

    # поиск в локальной БД гостя по telegram_id
    customer = find_customer(message.chat.id)
    if customer:
        # создание объекта гость с данными из QuickResto
        guest = api.Crm_info()
        history = guest.client_history(customer[0].phone_number)
        if len(history) > 6 and type(history) == type(list()):
            pages_count = len(history) // 6 + 1
            buttons = types.InlineKeyboardMarkup()
            left = page-1 if page != 1 else pages_count
            right = page+1 if page != pages_count else 1
            left_button = types.InlineKeyboardButton(
                "←", callback_data=f'to {left}')
            page_button = types.InlineKeyboardButton(
                f"{str(page)}/{str(pages_count)}", callback_data='_')
            right_button = types.InlineKeyboardButton(
                "→", callback_data=f'to {right}')
            buttons.add(left_button, page_button, right_button)
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


@dp.message_handler(lambda message: message.text == '/balance' or message.text == 'Баланс')
async def show_balance(message: types.Message):
    '''Вывод актуального баланса пользователя'''

    # поиск в локальной БД гостя по telegram_id
    customer = find_customer(message.chat.id)
    if customer:
        # создание объекта гость с данными из QuickResto
        guest = api.Crm_info()
        await message.answer(text='{}, у вас {} баллов'.format(customer[0].name, guest.client_balance(customer[0].phone_number)))
    else:
        await message.answer(text='Вы не вошли. Введите команду /start')


@dp.message_handler(lambda message: message.text == '/qr' or message.text == 'QR код')
async def show_qr(message: types.Message):
    '''Вывод QR кода пользователя для его индетификации в программе лояльности'''

    # создание объекта гость с данными из QuickResto
    customer = find_customer(message.chat.id)
    if customer:
        # базовая информация о госте
        guest = api.Crm_info()
        await message.answer_photo(photo=guest.qr_code(customer[0].phone_number))
    else:
        await message.answer(text='Вы не вошли. Введите команду /start')


@dp.callback_query_handler(lambda call: call.data)
async def call_info(call: types.CallbackQuery):
    '''Захват нажатие кнопки после старта бота, регистрация или вход'''

    if 'to' in call.data:
        page = int(call.data.split(' ')[1])
        await show_history(call.message, page=page, previous_message=call.message)
        await bot.answer_callback_query(call.id)

    if call.data == 'set_news':
        guest = api.CustomerOperation()
        if 'errorCode' in guest.getCustomer(telegram_id=call.from_user.id).keys():
            customer = guest.createCustomer(
                firstName=call.from_user.first_name, telegram_id=call.from_user.id)
            add_customer(telegram_id=call.from_user.id,
                         qresto_id=customer['customer']['id'], name=call.from_user.first_name, news=True)
            await bot.answer_callback_query(call.id)
        else:
            customer = guest.getCustomer(telegram_id=call.from_user.id)
            add_customer(telegram_id=call.from_user.id,
                         qresto_id=customer['id'], name=call.from_user.first_name, news=True)
            await bot.answer_callback_query(call.id)

    if call.data == 'only_bonuses':
        guest = api.CustomerOperation()
        if 'errorCode' in guest.getCustomer(telegram_id=call.from_user.id).keys():
            customer = guest.createCustomer(
                firstName=call.from_user.first_name, telegram_id=call.from_user.id)
            add_customer(telegram_id=call.from_user.id,
                         qresto_id=customer['customer']['id'], name=call.from_user.first_name, news=False)
            await bot.answer_callback_query(call.id)
        else:
            customer = guest.getCustomer(telegram_id=call.from_user.id)
            add_customer(telegram_id=call.from_user.id,
                         qresto_id=customer['id'], name=call.from_user.first_name, news=False)
            await bot.answer_callback_query(call.id)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
