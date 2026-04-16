import pika
import json
from settings import settings

def send_to_queue(user_id):
    credentials = pika.PlainCredentials(settings.RABBITMQ_USER, settings.RABBITMQ_PASSWORD)
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=settings.RABBITMQ_HOST,
            port=settings.RABBITMQ_PORT,
            credentials=credentials
        )
    )
    channel = connection.channel()
    channel.queue_declare(queue='nord_referal', durable=True)

    data = json.dumps({"user_id": user_id})

    channel.basic_publish(
        exchange='',
        routing_key='nord_referal',
        body=data,
        properties=pika.BasicProperties(
            delivery_mode=2,
        )
    )
    connection.close()
