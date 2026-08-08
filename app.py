import time

import streamlit as st
from streamlit_js_eval import get_geolocation

from agent.react_agent import ReactAgent
from utils.location_weather import extract_coordinates, format_weather, get_location_weather

st.set_page_config(page_title="智扫通机器人智能客服", page_icon="🤖")
st.title("智扫通机器人智能客服")
st.caption("基于 Agent 的扫地机器人售前与售后支持助手")
st.divider()


if "agent" not in st.session_state:
    st.session_state["agent"] = ReactAgent()
if "message" not in st.session_state:
    st.session_state["message"] = []

raw_location = get_geolocation(component_key="browser_geolocation")
coordinates = extract_coordinates(raw_location)
if coordinates:
    location_key = tuple(round(value, 4) for value in coordinates)
    if st.session_state.get("location_key") != location_key:
        try:
            with st.spinner("正在获取本地天气..."):
                st.session_state["location_profile"] = get_location_weather(*coordinates)
                st.session_state["location_key"] = location_key
                st.session_state.pop("location_error", None)
        except Exception:
            st.session_state["location_error"] = "暂时无法获取本地天气，请稍后刷新重试。"

with st.container(border=True):
    st.subheader("本地天气")
    st.caption("仅在本次会话中使用浏览器位置；不会写入聊天记录或向量数据库。")
    location_profile = st.session_state.get("location_profile")
    if location_profile:
        st.success(f"已定位到：{location_profile['city']}")
        weather_columns = st.columns(3)
        weather_columns[0].metric("天气", location_profile["condition"])
        weather_columns[1].metric("气温", f"{location_profile['temperature']} °C")
        weather_columns[2].metric("湿度", f"{location_profile['humidity']}%")
        st.caption(format_weather(location_profile))
        if st.button("刷新本地天气", use_container_width=True):
            st.session_state.pop("location_key", None)
            st.session_state.pop("location_profile", None)
            st.rerun()
    elif st.session_state.get("location_error"):
        st.warning(st.session_state["location_error"])
    else:
        st.info("请在浏览器弹出的提示中允许位置访问，以显示当前城市和实时天气。")

for message in st.session_state["message"]:
    st.chat_message(message["role"]).write(message["content"])

prompt = st.chat_input("请输入扫地机器人相关问题")
if prompt:
    st.chat_message("user").write(prompt)
    st.session_state["message"].append({"role": "user", "content": prompt})

    response_messages = []
    with st.spinner("正在思考..."):
        response_stream = st.session_state["agent"].execute_stream(
            prompt,
            location_profile=st.session_state.get("location_profile"),
        )

        def capture(generator, cache_list):
            for chunk in generator:
                cache_list.append(chunk)
                for character in chunk:
                    time.sleep(0.01)
                    yield character

        st.chat_message("assistant").write_stream(capture(response_stream, response_messages))
        if response_messages:
            st.session_state["message"].append(
                {"role": "assistant", "content": response_messages[-1]}
            )
        st.rerun()