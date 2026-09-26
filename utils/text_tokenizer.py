"""为中文知识片段生成可供 SQLite FTS5 使用的检索词。"""

from __future__ import annotations

import re


_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+")


def tokenize_search_text(text: str) -> list[str]:
    """生成英文单词、中文单字和中文二元词，兼顾精确词与短语召回。"""
    tokens: list[str] = []
    for segment in _TOKEN_PATTERN.findall(text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", segment):
            tokens.extend(segment)
            tokens.extend(segment[index : index + 2] for index in range(len(segment) - 1))
        else:
            tokens.append(segment)
    return list(dict.fromkeys(token for token in tokens if token.strip()))


def build_fts_query(text: str) -> str:
    """将查询转换为经过转义的 FTS5 OR 表达式。"""
    tokens = tokenize_search_text(text)
    return " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
