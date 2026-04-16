import pika
import json
import time
import asyncio
import logging
import aiohttp
from datetime import datetime, timedelta
from threading import Thread
from app.settings import settings

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DELAY_QUEUE = "delayed_tasks"
MAIN_QUEUE = "nord_referal"
DELAY_SECONDS = 60 * 60 * 3  # 3 часа

async def process_user_id(user_id, session: aiohttp.ClientSession):
    """
    Отправляет уведомление администратору о необходимости пополнения бонусов.
    """
    try:
        url = f'https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage'
        # Используем первый ID из списка админов для уведомлений
        admin_id = settings.ADMIN_IDS[0] if settings.ADMIN_IDS else None
        if not admin_id:
            logger.error("No ADMIN_IDS configured")
            return False

        data = {'chat_id': admin_id, 'text': f'Пополнить бонусы для пользователя ID: {user_id}'}
        async with session.post(url, data=data, proxy=settings.PROXY_URL) as response:
            if response.status != 200:
                text = await response.text()
                logger.error(f"TG API error: {response.status} - {text}")
                return False
            return True
    except Exception as e:
        logger.exception(f"Error processing user_id {user_id}: {e}")
        return False

async def consume_messages():
    credentials = pika.PlainCredentials(settings.RABBITMQ_USER, settings.RABBITMQ_PASSWORD)
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(host=settings.RABBITMQ_HOST, port=settings.RABBITMQ_PORT, credentials=credentials)
    )
    channel = connection.channel()
    channel.queue_declare(queue=MAIN_QUEUE, durable=True)
    channel.queue_declare(queue=DELAY_QUEUE, durable=True)

    async with aiohttp.ClientSession() as session:
        while True:
            method_frame, header_frame, body = channel.basic_get(MAIN_QUEUE, auto_ack=False)
            if method_frame:
                try:
                    message = json.loads(body.decode())
                    user_id = message.get("user_id")

                    if await process_user_id(user_id, session):
                        logger.info(f"Successfully processed user_id {user_id}")
                        channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                    else:
                        logger.warning(f"Failed to process user_id {user_id}, scheduling retry.")
                        retry_at = datetime.now() + timedelta(seconds=DELAY_SECONDS)
                        delayed_message = json.dumps({"user_id": user_id, "retry_at": retry_at.isoformat()})
                        channel.basic_publish(
                            exchange="",
                            routing_key=DELAY_QUEUE,
                            body=delayed_message,
                            properties=pika.BasicProperties(delivery_mode=2)
                        )
                        channel.basic_ack(delivery_tag=method_frame.delivery_tag)
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    channel.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=True)

            # Также проверяем отложенную очередь
            check_delayed_tasks(channel)

            await asyncio.sleep(1)

def check_delayed_tasks(channel):
    while True:
        method_frame, header_frame, body = channel.basic_get(DELAY_QUEUE, auto_ack=False)
        if not method_frame:
            break

        try:
            message = json.loads(body.decode())
            retry_at = datetime.fromisoformat(message["retry_at"])
            if datetime.now() >= retry_at:
                logger.info(f"Requeueing user_id {message['user_id']} into main queue.")
                channel.basic_publish(
                    exchange="",
                    routing_key=MAIN_QUEUE,
                    body=json.dumps({"user_id": message["user_id"]}),
                    properties=pika.BasicProperties(delivery_mode=2)
                )
                channel.basic_ack(delivery_tag=method_frame.delivery_tag)
            else:
                channel.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=True)
                break # Остальные в очереди еще позже должны быть
        except Exception as e:
            logger.error(f"Error checking delayed task: {e}")
            channel.basic_ack(delivery_tag=method_frame.delivery_tag)

if __name__ == "__main__":
    logger.info("Starting task consumer...")
    try:
        asyncio.run(consume_messages())
    except KeyboardInterrupt:
        logger.info("Consumer stopped by user")
