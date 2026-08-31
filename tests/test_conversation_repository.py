from storage.conversation_repository import ConversationRepository
from storage.support_repository import SupportRepository


def build_repository(tmp_path):
    seed_file = tmp_path / "records.csv"
    seed_file.write_text(
        "user_id,display_name,city,device_id,device_model,purchased_at,warranty_until,month,feature,efficiency,consumables,comparison\n"
        "u-1,用户一,上海,d-1,S9,2026-01-01,2028-01-01,2026-08,清扫 12 次,95%,滤网 60%,增加 2 次\n"
        "u-2,用户二,北京,d-2,X10,2026-02-01,2028-02-01,2026-08,清扫 8 次,93%,滤网 70%,增加 1 次\n",
        encoding="utf-8",
    )
    support_repository = SupportRepository(tmp_path / "support.db")
    support_repository.seed_business_data(seed_file)
    return ConversationRepository(support_repository.database_path)


def test_conversation_messages_are_persisted_and_ordered(tmp_path):
    repository = build_repository(tmp_path)
    conversation = repository.create_conversation("u-1", "  如何清理主刷  ")
    repository.add_message(
        "u-1",
        conversation.conversation_id,
        role="user",
        content="主刷怎么清理？",
    )
    repository.add_message(
        "u-1",
        conversation.conversation_id,
        role="assistant",
        content="请先断电并取下主刷。",
        traces=["已检索维护知识库。"],
        agent="knowledge_agent",
    )

    summary, messages = repository.get_conversation("u-1", conversation.conversation_id)

    assert summary.title == "如何清理主刷"
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[-1].traces == ["已检索维护知识库。"]
    assert repository.list_conversations("u-1")[0].preview == "请先断电并取下主刷。"


def test_conversation_isolated_by_user(tmp_path):
    repository = build_repository(tmp_path)
    conversation = repository.create_conversation("u-1", "用户一的会话")

    assert repository.get_conversation("u-2", conversation.conversation_id) is None
    assert not repository.delete_conversation("u-2", conversation.conversation_id)
    assert repository.delete_conversation("u-1", conversation.conversation_id)
    assert repository.get_conversation("u-1", conversation.conversation_id) is None
