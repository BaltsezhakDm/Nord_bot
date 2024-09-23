from aiogram import types


key1 = types.InlineKeyboardButton(text='О нас', callback_data='about')
key2 = types.InlineKeyboardButton(text='Меню', callback_data='menu')


key3 = types.InlineKeyboardButton(text='Показать QR', callback_data='qr')
key4 = types.InlineKeyboardButton(text='Проверить баланс', callback_data='balance')
key5 = types.InlineKeyboardButton(text='Пригласить друга', callback_data='invite')

key6 = types.InlineKeyboardButton(text='Как копить бонусы?', callback_data='how_to_collect')
key7 = types.InlineKeyboardButton(text='Адреса и режим работы', callback_data='address')
key8 = types.InlineKeyboardButton(text='Задать вопрос', callback_data='ask')
key9 = types.InlineKeyboardButton(text='Следить за нами в ТГ', url='https://t.me/kosplace')
key10 = types.InlineKeyboardButton(text='KOS в социальных сетях', callback_data='social')
key11 = types.InlineKeyboardButton(text='Оставить отзыв', callback_data='review')

key_menu = types.InlineKeyboardButton(text='Назад в меню', callback_data='back')


key_borodinskaya = types.InlineKeyboardButton(text='Бородинская', url='https://kosplace.ru/menyborodinskaya')
key_komendantskaya = types.InlineKeyboardButton(text='Комендантская', url='https://kosplace.ru/menykomenda')

review_borodinskaya = types.InlineKeyboardButton(text='Бородинская', url='https://kosplace.ru/review')
review_komendantskaya = types.InlineKeyboardButton(text='Комендантская', url='https://kosplace.ru/review_kom')


instagram_button = types.InlineKeyboardButton(text="Instagram", url="https://www.instagram.com/kos.place?igsh=aDBpc2x5cTB4dm4z")
vk_button = types.InlineKeyboardButton(text="VK", url="https://vk.com/kos.place")
telegram_button = types.InlineKeyboardButton(text="Telegram", url="https://t.me/kosplace")


keyboard_review = types.InlineKeyboardMarkup(inline_keyboard=[[review_borodinskaya, review_komendantskaya], [key_menu]])
keyboard_social = types.InlineKeyboardMarkup(inline_keyboard=[[instagram_button], [vk_button], [telegram_button], [key_menu]])
keyboard_main = types.InlineKeyboardMarkup(
    inline_keyboard=[[key1, key2], [key3], [key4], [key5], [key6], [key7], [key8], [key9], [key10], [key11]])
keyboard_menu = types.InlineKeyboardMarkup(inline_keyboard=[[key_borodinskaya, key_komendantskaya], [key_menu]])
keyboard_back = types.InlineKeyboardMarkup(inline_keyboard=[[key_menu]])


