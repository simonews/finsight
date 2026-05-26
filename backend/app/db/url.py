import os


def get_async_database_url() -> str:
    """Converte la DATABASE_URL standard (postgresql://) nel dialetto
    asincrono dell'applicazione (postgresql+asyncpg://).
    """
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)