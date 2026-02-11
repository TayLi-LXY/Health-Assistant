"""应用配置"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用设置"""
    # LLM
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    dashscope_api_key: str = ""
    
    # RAG
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 5
    
    # Paths
    data_dir: str = "data"
    knowledge_base_dir: str = "knowledge_base"
    
    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
