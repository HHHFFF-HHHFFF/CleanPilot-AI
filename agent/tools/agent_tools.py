import json
from datetime import date

import requests
from langchain_core.tools import tool

from rag.rag_service import RagSummarizeService
from storage.support_repository import SupportRepository
from utils.config_handler import agent_config
from utils.location_weather import format_weather, get_city_weather
from utils.path_tool import get_abs_path

rag = RagSummarizeService()
support_repository = SupportRepository()
support_repository.seed_business_data(get_abs_path(agent_config["business_seed_path"]))


@tool(description="Search the vector knowledge base and summarize the relevant product guidance.")
def rag_summarize(query: str) -> str:
    return rag.rag_summarize(query)


@tool(description="Get live weather for a specified city.")
def get_weather(city: str) -> str:
    try:
        return format_weather(get_city_weather(city))
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        return f"Unable to retrieve live weather for {city}: {error}"


@tool(description="Get the current city from browser location after the user has granted permission.")
def get_user_location() -> str:
    return "Browser location permission is unavailable. Ask the user to grant permission or provide a city."


@tool(description="Get the current conversation user ID for personalized usage-record queries.")
def get_user_id() -> str:
    users = support_repository.list_users()
    return users[0].user_id if users else ""


@tool(description="Get the current year and month in YYYY-MM format.")
def get_current_month() -> str:
    return date.today().strftime("%Y-%m")


@tool(description="Query a user's device usage record for a specified month; return an empty string if unavailable.")
def fetch_external_data(user_id: str, month: str) -> str:
    record = support_repository.get_usage_record(user_id, month)
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


@tool(description="Switch the agent into its structured usage-report prompt context.")
def fill_context_for_report() -> str:
    return "fill_context_for_report completed"
