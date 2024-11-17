import pika
import json
import time
from datetime import datetime, timedelta

DELAY_QUEUE = "delayed_tasks"
MAIN_QUEUE = "nord_referal"
DELAY_SECONDS = 10  # 3 часа в секундах
from threading import Thread



def process_user_id(user_id):
    """
    Обрабатывает user_id.
    Возвращает False, если задача не выполнена, True - если выполнена.
    """
    time.sleep(1)  # Симуляция обработки
    return True if int(user_id) % 7 == 0 else False


def handle_delayed_tasks():
    """
    Проверяет отложенные задачи и возвращает их в основную очередь,
    если истекло время задержки.
    """
    credentials = pika.PlainCredentials('user', 'password')
    connection = pika.BlockingConnection(pika.ConnectionParameters("localhost", credentials=credentials))
    channel = connection.channel()

    channel.queue_declare(queue=DELAY_QUEUE, durable=True)
    channel.queue_declare(queue=MAIN_QUEUE, durable=True)

    while True:
        method_frame, header_frame, body = channel.basic_get(DELAY_QUEUE, auto_ack=False)

        while method_frame:
            message = json.loads(body.decode())
            retry_at = datetime.fromisoformat(message["retry_at"])
            now = datetime.now()

            if now >= retry_at:
                print(f"Requeueing user_id {message['user_id']} into main queue.")
                # Переместить задачу обратно в основную очередь
                channel.basic_publish(
                    exchange="",
                    routing_key=MAIN_QUEUE,
                    body=json.dumps({"user_id": message["user_id"]}),
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # Сделать сообщение устойчивым
                    ),
                )
                channel.basic_ack(delivery_tag=method_frame.delivery_tag)
            else:
                # Если время еще не истекло, оставляем задачу в очереди
                channel.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=True)

            # Проверяем следующее сообщение
            method_frame, header_frame, body = channel.basic_get(DELAY_QUEUE, auto_ack=False)

        # Ждем перед следующей проверкой
        time.sleep(DELAY_SECONDS)




def consumer_callback(ch, method, properties, body):
    message = json.loads(body.decode())
    try:
        user_id = message.get("user_id")
    except (KeyError, AttributeError):
        print(f"Invalid message format: {message}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    if process_user_id(user_id):
        print(f"Successfully processed user_id {user_id}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
    else:
        print(f"Failed to process user_id {user_id}, scheduling retry.")
        # Добавить задачу в отложенную очередь
        retry_at = datetime.now() + timedelta(seconds=DELAY_SECONDS)
        delayed_message = json.dumps({"user_id": int(user_id) + 1, "retry_at": retry_at.isoformat()})

        ch.basic_publish(
            exchange="",
            routing_key=DELAY_QUEUE,
            body=delayed_message,
            properties=pika.BasicProperties(
                delivery_mode=2,  # Сделать сообщение устойчивым
            ),
        )
        ch.basic_ack(delivery_tag=method.delivery_tag)


def start_consumer():
    """
    Основной консумер для обработки задач из основной очереди.
    """
    credentials = pika.PlainCredentials('user', 'password')
    connection = pika.BlockingConnection(pika.ConnectionParameters("localhost", credentials=credentials))
    channel = connection.channel()

    channel.queue_declare(queue=MAIN_QUEUE, durable=True)

    channel.basic_consume(
        queue=MAIN_QUEUE,
        on_message_callback=consumer_callback
    )

    print("Waiting for messages in main queue. To exit, press CTRL+C.")
    channel.start_consuming()


if __name__ == "__main__":
    # Запуск проверки отложенных задач каждые 3 часа
    Thread(target=start_consumer).start()
    Thread(target=handle_delayed_tasks).start()
