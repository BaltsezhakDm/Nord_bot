import pika
import json
import os

rabbitmq_host = os.getenv('RABBITMQ_HOST', 'localhost')
rabbimq_user = os.getenv('RABBITMQ_USER', 'user')
rabbitmq_password = os.getenv('RABBITMQ_PASSWORD', 'password')

credentials = pika.PlainCredentials(rabbimq_user, rabbitmq_password)


def send_to_queue(user_id):
    connection = pika.BlockingConnection(pika.ConnectionParameters(rabbitmq_host, credentials=credentials))
    channel = connection.channel()
    channel.queue_declare(queue='nord_referal', durable=True)
    # Declare the queue

    data = json.dumps({"user_id": user_id})

    # Publish message
    channel.basic_publish(
        exchange='',
        routing_key='nord_referal',
        body=data,
        properties=pika.BasicProperties(
            delivery_mode=2,  # Make message persistent
        )
    )
    print(f"Sent user_id {user_id} to queue 'nord_referal'")
    connection.close()


if __name__ == '__main__':
    send_to_queue(1)