import os
from typing import Optional, List

class Settings:
    # Telegram
    BOT_TOKEN: str = os.getenv('token', '')
    WEBHOOK_URL: Optional[str] = os.getenv('webhook_url')
    ADMIN_IDS: List[int] = [9969290700]  # Извлечено из кода

    # QuickResto API
    LOGIN_API: str = os.getenv('login_api', '')
    PASSWORD_API: str = os.getenv('password_api', '')

    # QuickResto LK (Backoffice)
    LOGIN_LK: str = os.getenv('login_lk', '')
    PASSWORD_LK: str = os.getenv('password_lk', '')

    # Database
    USER_DB: str = os.getenv('user_db', 'postgres')
    PASSWORD_DB: str = os.getenv('password_db', 'postgres')
    DATABASE: str = os.getenv('database', 'postgres')
    HOST_DB: str = os.getenv('host_db', 'localhost')

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.USER_DB}:{self.PASSWORD_DB}@{self.HOST_DB}/{self.DATABASE}"

    # Redis
    REDIS_HOST: str = os.getenv('redis_host', 'localhost')
    REDIS_PORT: int = int(os.getenv('redis_port', 6379))
    REDIS_DB: int = int(os.getenv('redis_db', 3))

    # RabbitMQ
    RABBITMQ_HOST: str = os.getenv('RABBITMQ_HOST', 'localhost')
    RABBITMQ_PORT: int = int(os.getenv('RABBITMQ_PORT', 5672))
    RABBITMQ_USER: str = os.getenv('RABBITMQ_USER', 'user')
    RABBITMQ_PASSWORD: str = os.getenv('RABBITMQ_PASSWORD', 'password')

    # Security
    CRYPT_KEY: str = os.getenv('crypt_key', '')

    # Proxy
    PROXY_URL: Optional[str] = os.getenv('PROXY_URL')

    # Debug
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')

settings = Settings()
