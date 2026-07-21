from enum import Enum, auto
from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings

from app.config.settings import settings


T = TypeVar("T", bound=BaseModel)


class LLMs(Enum):
    REASONER = auto()
    CHAT = auto()
    DEBUG = auto()
    MULTI = auto()
    FLASH = auto()

class InvalidLLMTypeError(ValueError):

    def __init__(self, invalid_value):
        message = f"无效的LLM类型: {invalid_value}"
        super().__init__(message)


class _CommonLLMSetting(BaseSettings):
    model: str
    api_key: SecretStr
    base_url: str

    max_retries: int = 10


class FlashLLMSetting(_CommonLLMSetting):
    model: str = "deepseek-v4-flash"
    base_url: str = "https://api.deepseek.com/v1"
    api_key: SecretStr = SecretStr(settings.deepseek_api_key)
    max_tokens: int = 384_000
    extra_body:dict={"thinking": {"type": "disabled"}}


class ChatLLMSetting(_CommonLLMSetting):
    model: str = "deepseek-v4-pro"
    base_url: str = "https://api.deepseek.com/v1"
    api_key: SecretStr = SecretStr(settings.deepseek_api_key)
    max_tokens: int = 384_000
    extra_body:dict={"thinking": {"type": "disabled"}}


class ReasonerLLMSetting(_CommonLLMSetting):
    model: str = "deepseek-v4-pro"
    base_url: str = "https://api.deepseek.com/v1"
    api_key: SecretStr = SecretStr(settings.deepseek_api_key)
    max_tokens: int = 384_000


class MultiModelLLMSetting(_CommonLLMSetting):
    model: str = "qwen3.6-plus"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key: SecretStr = SecretStr(settings.qwen_api_key)

    max_tokens: int = 30000
    extra_body:dict = {
        "enable_thinking": True,
        "thinking_budget": 8192
    }


class DebugLLMSetting(_CommonLLMSetting):
    base_url: str = "https://api.siliconflow.cn/v1"
    model: str = "Pro/THUDM/glm-4-9b-chat"
    api_key: SecretStr = SecretStr(settings.siliconflow_api_key)


class LLMCreator:
    _map = {
        LLMs.REASONER: (ReasonerLLMSetting, ChatDeepSeek),
        LLMs.CHAT: (ChatLLMSetting, ChatDeepSeek),
        LLMs.DEBUG: (DebugLLMSetting, ChatOpenAI),
        LLMs.MULTI: (MultiModelLLMSetting, ChatOpenAI),
        LLMs.FLASH: (FlashLLMSetting, ChatOpenAI),
    }
    _instances: dict[LLMs, BaseChatModel] = {}

    @classmethod
    def get_llm(
        cls,
        llm_type: LLMs,
        schema: type[T] | None = None,
        method: str | None = None,
        *,
        retry: bool = True,
        stop_after_attempt: int | None = None,
    ) -> Runnable:
        effective = LLMs.DEBUG if settings.llm_debug else llm_type
        if effective not in cls._instances:
            config_cls, chat_cls = cls._map[effective]
            cls._instances[effective] = chat_cls(**config_cls().model_dump())

        llm = cls._instances[effective]

        if schema is not None:
            _, chat_cls = cls._map[effective]
            if method is None:
                method = "json_mode"
            llm = llm.with_structured_output(schema, method=method)

        if retry:
            kwargs = {}
            if stop_after_attempt is not None:
                kwargs["stop_after_attempt"] = stop_after_attempt
            llm = llm.with_retry(**kwargs)

        return llm
