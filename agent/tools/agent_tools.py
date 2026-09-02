import json
from datetime import date

import requests
from langchain_core.tools import tool

from rag.rag_service import RagSummarizeService
from storage.support_repository import SupportRepository
from utils.config_handler import agent_config
from utils.location_weather import format_weather, get_city_weather
from utils.path_tool import get_abs_path

_rag_service = None
_support_repository = None


def _get_rag_service() -> RagSummarizeService:
    global _rag_service
    if _rag_service is None:
        _rag_service = RagSummarizeService()
    return _rag_service


def _get_support_repository() -> SupportRepository:
    global _support_repository
    if _support_repository is None:
        _support_repository = SupportRepository()
        _support_repository.seed_business_data(
            get_abs_path(agent_config["business_seed_path"])
        )
    return _support_repository


@tool(description="检索向量知识库，并总结与用户问题相关的产品知识和操作建议。")
def rag_summarize(query: str) -> str:
    return _get_rag_service().rag_summarize(query)


@tool(description="查询指定城市的实时天气信息。")
def get_weather(city: str) -> str:
    try:
        return format_weather(get_city_weather(city))
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        return f"暂时无法获取 {city} 的实时天气：{error}"


@tool(description="获取用户授权的浏览器定位所对应的当前城市。")
def get_user_location() -> str:
    return "当前无法读取浏览器定位，请提示用户授权定位或直接提供城市名称。"


@tool(description="获取当前会话用户 ID，用于个性化使用记录查询。")
def get_user_id() -> str:
    users = _get_support_repository().list_users()
    return users[0].user_id if users else ""


@tool(description="获取系统当前年月，格式为 YYYY-MM。")
def get_current_month() -> str:
    return date.today().strftime("%Y-%m")


@tool(description="查询当前会话用户绑定的设备型号、设备编号、购买日期和保修期限。")
def get_current_device(user_id: str) -> str:
    device = _get_support_repository().get_device(user_id)
    if device is None:
        return ""
    return json.dumps(device, ensure_ascii=False)


@tool(description="查询指定用户在指定月份的设备使用记录；没有记录时返回空字符串。")
def fetch_external_data(user_id: str, month: str) -> str:
    record = _get_support_repository().get_usage_record(user_id, month)
    if record is None:
        return ""
    return json.dumps(
        {
            "user_id": record.user_id,
            "month": record.month,
            "feature": record.feature,
            "efficiency": record.efficiency,
            "consumables": record.consumables,
            "comparison": record.comparison,
        },
        ensure_ascii=False,
    )
