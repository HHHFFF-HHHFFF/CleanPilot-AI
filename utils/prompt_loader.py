from utils.logger_handler import logger
from utils.config_handler import prompts_config
from utils.path_tool import get_abs_path


def _load_prompt(config_key: str, prompt_name: str) -> str:
    try:
        prompt_path = get_abs_path(prompts_config[config_key])
    except KeyError as error:
        logger.error("[prompt loader] 缺少配置项 %s", config_key)
        raise error

    try:
        with open(prompt_path, "r", encoding="utf-8") as prompt_file:
            return prompt_file.read()
    except Exception as error:
        logger.error("[prompt loader] 解析%s提示词失败：%s", prompt_name, error)
        raise


def load_system_prompts():
    return _load_prompt("main_prompt_path", "系统")


def load_rag_prompts():
    return _load_prompt("rag_summarize_prompt_path", "RAG 总结")


def load_report_prompts():
    return _load_prompt("report_prompt_path", "报告")


def load_router_prompts():
    return _load_prompt("router_prompt_path", "调度 Agent")


def load_knowledge_prompts():
    return _load_prompt("knowledge_prompt_path", "知识问答 Agent")


def load_diagnosis_prompts():
    return _load_prompt("diagnosis_prompt_path", "故障诊断 Agent")


def load_customer_prompts():
    return _load_prompt("customer_prompt_path", "用户运营 Agent")

if __name__ == '__main__':
    print(load_system_prompts())
