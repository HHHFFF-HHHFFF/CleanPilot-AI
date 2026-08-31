"""Uvicorn 默认加载入口。"""

from api.app import create_app
from api.settings import ApiSettings


app = create_app(ApiSettings.from_env())
