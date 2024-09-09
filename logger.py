import logging

# Создаем и настраиваем логгер
def setup_logger():
    logger = logging.getLogger('aiogram_logger')
    logger.setLevel(logging.DEBUG)  # Устанавливаем уровень логгирования на debug

    # Обработчик для вывода в консоль
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)  # Тоже выводим сообщения уровня debug
    console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)

    # Обработчик для записи в файл
    file_handler = logging.FileHandler('aiogram_debug.log', mode='a')
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)

    # Добавляем обработчики в логгер
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


