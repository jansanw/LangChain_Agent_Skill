import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek

from config import load_config
from core.registry import logger
from models import DeepSeekReasonerChatModel

# 1. 加载配置
config_path = Path('./config.yaml')
config = load_config(config_path)

load_dotenv()
api_key = os.getenv('DEEPSEEK_API_KEY')

# 2. 初始化模型
logger.info(f"初始化模型配置: {config.default_model}")
llm = None
switcher = {
    'deepseek-chat': lambda: ChatDeepSeek(
        model=config.default_model,
        api_key=api_key,
        temperature=config.temperature,
    ),
    'deepseek-reasoner': lambda: DeepSeekReasonerChatModel(
        model=config.default_model,
        api_key=api_key,
        temperature=config.temperature,
    ),
}
model_loader = switcher.get(config.default_model)
if model_loader is None:
    raise ValueError(f"不支持的模型类型: {config.default_model}")
llm = model_loader()
