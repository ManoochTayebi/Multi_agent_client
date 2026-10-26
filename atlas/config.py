from datetime import date
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    atlas_mode: str = 'demo'
    database_url: str = 'sqlite:///runtime/atlas.db'
    chroma_path: str = 'runtime/chroma'
    data_dir: str = 'data'
    as_of_date: date = date(2026, 10, 26)
    demo_access: bool = True
    admin_api_key: str = ''
    customer_tokens: dict[str, str] = {}
    openai_api_key: str = ''
    openai_model: str = ''
    openai_base_url: str = 'https://api.openai.com/v1'
    embedding_model: str = ''
    carrier_base_url: str = ''
    carrier_api_key: str = ''

    def validate_runtime(self):
        if self.atlas_mode not in {'demo', 'llm'}:
            raise ValueError('ATLAS_MODE must be demo or llm')
        if self.atlas_mode == 'llm' and not (self.openai_api_key and self.openai_model):
            raise ValueError('LLM mode requires OPENAI_API_KEY and OPENAI_MODEL')
        if self.embedding_model and not self.openai_api_key:
            raise ValueError('EMBEDDING_MODEL requires OPENAI_API_KEY')
        if not self.demo_access and not self.customer_tokens:
            raise ValueError('Configure CUSTOMER_TOKENS when DEMO_ACCESS=false')
        if self.database_url.startswith('sqlite:///'):
            Path(self.database_url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
        Path(self.chroma_path).mkdir(parents=True, exist_ok=True)


@lru_cache
def settings():
    return Settings()
