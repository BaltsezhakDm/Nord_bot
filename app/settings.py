import os
from typing import Optional, List

class Settings:
    # Telegram
    BOT_TOKEN: str = os.getenv('token', '')
    WEBHOOK_URL: Optional[str] = os.getenv('webhook_url')

    @property
    def ADMIN_IDS(self) -> List[int]:
        ids_str = os.getenv('ADMIN_IDS', '')
        if not ids_str:
            return []
        return [int(x.strip()) for x in ids_str.split(',') if x.strip().isdigit()]

    # QuickResto API
    LOGIN_API: str = os.getenv('login_api', '')
    PASSWORD_API: str = os.getenv('password_api', '')

    # QuickResto LK (Backoffice)
    LOGIN_LK: str = os.getenv('login_lk', '')
    PASSWORD_LK: str = os.getenv('password_lk', '')

    # Database
    USER_DB: str = os.getenv('user_db', '')
    PASSWORD_DB: str = os.getenv('password_db', '')
    DATABASE: str = os.getenv('database', '')
    HOST_DB: str = os.getenv('host_db', '')

    @property
    def DATABASE_URL(self) -> str:
        if not self.USER_DB:
            return ""
        return f"postgresql+asyncpg://{self.USER_DB}:{self.PASSWORD_DB}@{self.HOST_DB}/{self.DATABASE}"

    # Redis
    REDIS_HOST: str = os.getenv('redis_host', 'localhost')
    REDIS_PORT: int = int(os.getenv('redis_port', 6379))
    REDIS_DB: int = int(os.getenv('redis_db', 3))

    # Security
    CRYPT_KEY: str = os.getenv('crypt_key', '')

    # Proxy
    PROXY_URL: Optional[str] = os.getenv('PROXY_URL')

    # Debug
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')

settings = Settings()
