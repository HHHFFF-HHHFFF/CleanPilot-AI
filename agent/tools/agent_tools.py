import os
import random

import requests
from langchain_core.tools import tool

from rag.rag_service import RagSummarizeService
from utils.config_handler import agent_config
from utils.location_weather import format_weather, get_city_weather
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

rag = RagSummarizeService()

user_ids = ["1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008", "1009", "1010"]
month_arr = [
    "2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06",
    "2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12",
]
external_data = {}


@tool(description="从向量存储中检索参考资料并结合用户提问概括回答。")
def rag_summarize(query: str) -> str:
    return rag.rag_summarize(query)


@tool(description="获取指定城市的实时天气信息；城市名称应由用户提供或通过 get_user_location 获取。")
def get_weather(city: str) -> str:
    try:
        return format_weather(get_city_weather(city))
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        return f"暂时无法获取{city}的实时天气：{error}"


@tool(description="获取用户当前所在城市。仅在用户已授权浏览器位置访问时可用。")
def get_user_location() -> str:
    return "用户尚未授权浏览器位置访问，无法获取当前城市。请提示用户授权定位或直接提供城市名称。"


@tool(description="获取用户的 ID，以纯字符串形式返回。")
def get_user_id() -> str:
    return random.choice(user_ids)


@tool(description="获取当前月份，以纯字符串形式返回。")
def get_current_month() -> str:
    return random.choice(month_arr)


def generate_external_data():
    if external_data:
        return

    external_data_path = get_abs_path(agent_config["external_data_path"])
    if not os.path.exists(external_data_path):
        raise FileNotFoundError(f"外部数据文件 {external_data_path} 不存在")

    with open(external_data_path, "r", encoding="utf-8") as file:
        for line in file.readlines()[1:]:
            values = line.strip().split(",")
            user_id = values[0].replace('"', "")
            feature = values[1].replace('"', "")
            efficiency = values[2].replace('"', "")
            consumables = values[3].replace('"', "")
            comparison = values[4].replace('"', "")
            month = values[5].replace('"', "")

            external_data.setdefault(user_id, {})[month] = {
                "特征": feature,
                "效率": efficiency,
                "耗材": consumables,
                "对比": comparison,
            }


@tool(description="从外部系统中获取用户使用记录；如未检索到则返回空字符串。")
def fetch_external_data(user_id: str, month: str) -> str:
    generate_external_data()
    try:
        return external_data[user_id][month]
    except KeyError:
        logger.warning(f"[fetch_external_data] 未检索到用户 {user_id} 在 {month} 的使用记录数据")
        return ""


@tool(description="无入参、无返回值；调用后触发报告场景的动态上下文注入。")
def fill_context_for_report() -> str:
    return "fill_context_for_report 已调用"