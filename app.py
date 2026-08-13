import html

import streamlit as st
from streamlit_js_eval import get_geolocation

from agent.react_agent import ReactAgent
from storage.support_repository import SupportRepository
from ui.knowledge_base import render_knowledge_base_page
from utils.config_handler import agent_config
from utils.location_weather import extract_coordinates, format_weather, get_location_weather
from utils.path_tool import get_abs_path

AGENT_RUNTIME_VERSION = "structured_stream_v3"

st.set_page_config(page_title="智扫通机器人智能客服", page_icon="🤖")
st.title("智扫通机器人智能客服")
st.caption("基于 Agent 的扫地机器人售前与售后支持助手")
st.divider()
st.markdown(
    """
    <style>
    .agent-trace {
        background: rgba(100, 116, 139, 0.12);
        border-left: 3px solid rgba(100, 116, 139, 0.45);
        border-radius: 0 8px 8px 0;
        color: rgba(71, 85, 105, 0.9);
        font-size: 0.82rem;
        line-height: 1.55;
        margin: 0 0 0.8rem;
        padding: 0.6rem 0.75rem;
    }
    .agent-trace-title {
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.03em;
        margin-bottom: 0.25rem;
        opacity: 0.8;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

page = st.sidebar.radio("工作台", ["智能客服", "知识库运营"])
if page == "知识库运营":
    render_knowledge_base_page()
    st.stop()


support_repository = SupportRepository()
support_repository.seed_business_data(get_abs_path(agent_config["business_seed_path"]))
support_users = support_repository.list_users()
if not support_users:
    st.error("No demo user data is available.")
    st.stop()

selected_user = st.sidebar.selectbox(
    "Demo user",
    support_users,
    format_func=lambda user: f"{user.display_name} ({user.user_id}) - {user.city}",
)
selected_device = support_repository.get_device(selected_user.user_id)


def render_trace(trace_steps: list[str], placeholder=None):
    safe_steps = "<br>".join(html.escape(step) for step in trace_steps)
    trace_html = (
        '<div class="agent-trace">'
        '<div class="agent-trace-title">处理过程</div>'
        f"{safe_steps}"
        "</div>"
    )
    target = placeholder if placeholder is not None else st
    target.markdown(trace_html, unsafe_allow_html=True)


if st.session_state.get("agent_runtime_version") != AGENT_RUNTIME_VERSION:
    st.session_state["agent"] = ReactAgent()
    st.session_state["agent_runtime_version"] = AGENT_RUNTIME_VERSION
if "message" not in st.session_state:
    st.session_state["message"] = []

with st.container(border=True):
    st.subheader("Current conversation user")
    st.caption(f"{selected_user.display_name} · {selected_user.city} · ID: {selected_user.user_id}")
    if selected_device:
        device_columns = st.columns(3)
        device_columns[0].metric("Device model", selected_device["model"])
        device_columns[1].metric("Purchased", selected_device["purchased_at"])
        device_columns[2].metric("Warranty until", selected_device["warranty_until"])

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
    with st.chat_message(message["role"]):
        if message.get("trace"):
            render_trace(message["trace"])
        st.markdown(message["content"])

prompt = st.chat_input("请输入扫地机器人相关问题")
if prompt:
    st.chat_message("user").write(prompt)
    st.session_state["message"].append({"role": "user", "content": prompt})

    trace_steps = []
    answer_parts = []
    with st.spinner("正在思考..."):
        response_stream = st.session_state["agent"].execute_stream(
            prompt,
            location_profile=st.session_state.get("location_profile"),
            user_id=selected_user.user_id,
        )
        with st.chat_message("assistant"):
            trace_placeholder = st.empty()
            answer_placeholder = st.empty()
            for event in response_stream:
                if isinstance(event, str):
                    answer_parts.append(event)
                    answer_placeholder.markdown("\n\n".join(answer_parts))
                    continue
                if event["type"] == "trace":
                    trace_steps.append(event["content"])
                    render_trace(trace_steps, trace_placeholder)
                elif event["type"] == "answer":
                    answer_parts.append(event["content"])
                    answer_placeholder.markdown("\n\n".join(answer_parts))

    if answer_parts:
        st.session_state["message"].append(
            {
                "role": "assistant",
                "content": "\n\n".join(answer_parts),
                "trace": trace_steps,
            }
        )
    else:
        st.warning("暂未生成有效回答，请重试。")
