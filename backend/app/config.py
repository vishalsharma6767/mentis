from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    appwrite_endpoint: str = 'https://sgp.cloud.appwrite.io/v1'
    appwrite_project_id: str = ''
    appwrite_api_key: str = ''
    groq_api_key: str = ''
    database_url: str = 'sqlite:///./mentis.db'
    redis_url: str = 'redis://localhost:6379/0'

    model_config = {'env_file': '.env', 'env_file_encoding': 'utf-8'}


settings = Settings()
