from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore', env_ignore_empty=True)
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
    llm_timeout_seconds: float = 180
    llm_max_tokens: int = 800
    llm_token_parameter: Literal['max_tokens', 'max_completion_tokens'] = 'max_completion_tokens'
    llm_max_retries: int = 0
    llm_json_schema: bool = True
    llm_reasoning_effort: str | None = None
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    carrier_base_url: str = ''
    carrier_api_key: str = ''

    def validate_runtime(self):
        if self.atlas_mode not in {'demo', 'llm'}:
            raise ValueError('ATLAS_MODE must be demo or llm')
        if self.atlas_mode == 'llm' and not (self.openai_api_key and self.openai_model):
            raise ValueError('LLM mode requires OPENAI_API_KEY and OPENAI_MODEL')
        if self.embedding_model and not self.openai_api_key:
            raise ValueError('EMBEDDING_MODEL requires OPENAI_API_KEY')
        if self.llm_timeout_seconds <= 0 or self.llm_max_tokens < 64 or self.llm_max_retries < 0:
            raise ValueError('Invalid model call bounds')
        if any(x is not None and x < 0 for x in
               (self.input_cost_per_million, self.output_cost_per_million)):
            raise ValueError('Model cost rates must be non-negative')
        if not self.demo_access and not self.customer_tokens:
            raise ValueError('Configure CUSTOMER_TOKENS when DEMO_ACCESS=false')
        if self.database_url.startswith('sqlite:///'):
            Path(self.database_url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
        Path(self.chroma_path).mkdir(parents=True, exist_ok=True)


@lru_cache
def settings():
    return Settings()
