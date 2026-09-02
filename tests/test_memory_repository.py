from datetime import datetime, timezone

from storage.conversation_repository import ConversationRepository
from storage.memory_repository import MemoryRepository
from storage.support_repository import SupportRepository


def build_repositories(tmp_path):
    seed_file = tmp_path / "records.csv"
    seed_file.write_text(
        "user_id,display_name,city,device_id,device_model,purchased_at,warranty_until,month,feature,efficiency,consumables,comparison\n"
        "u-1,用户一,上海,d-1,S9,2026-01-01,2028-01-01,2026-08,清扫 12 次,95%,滤网 60%,增加 2 次\n"
        "u-2,用户二,北京,d-2,X10,2026-02-01,2028-02-01,2026-08,清扫 8 次,93%,滤网 70%,增加 1 次\n",
        encoding="utf-8",
    )
    support_repository = SupportRepository(tmp_path / "support.db")
    support_repository.seed_business_data(seed_file)
    conversation_repository = ConversationRepository(support_repository.database_path)
    memory_repository = MemoryRepository(support_repository.database_path)
    return conversation_repository, memory_repository


def test_working_memory_keeps_recent_messages_and_summarizes_older_messages(tmp_path):
    conversations, memories = build_repositories(tmp_path)
    conversation = conversations.create_conversation("u-1", "测试会话")
    for index in range(6):
        conversations.add_message(
            "u-1",
            conversation.conversation_id,
            role="user" if index % 2 == 0 else "assistant",
            content=f"消息 {index}",
        )

    context = memories.refresh_conversation_summary(
        "u-1",
        conversation.conversation_id,
        retain_recent=2,
    )

    assert context.summarized_message_count == 4
    assert "消息 0" in context.summary
    assert "消息 3" in context.summary
    assert context.recent_messages == [
        {"role": "user", "content": "消息 4"},
        {"role": "assistant", "content": "消息 5"},
    ]


def test_memory_is_isolated_by_account_and_device(tmp_path):
    _, memories = build_repositories(tmp_path)
    memories.upsert_fault_episode(
        "u-1",
        query="设备报错 E3",
        answer="清理滚刷",
        device_id="d-1",
    )

    assert len(memories.list_active_memories("u-1", device_id="d-1")) == 1
    assert memories.list_active_memories("u-1", device_id="d-2") == []
    assert memories.list_active_memories("u-2", device_id="d-1") == []


def test_repeated_fault_updates_version_instead_of_duplicating(tmp_path):
    _, memories = build_repositories(tmp_path)
    first = memories.upsert_fault_episode(
        "u-1",
        query="设备报错 E3",
        answer="先清理滚刷",
        device_id="d-1",
    )
    second = memories.upsert_fault_episode(
        "u-1",
        query="设备报错 E3",
        answer="清理后重新启动",
        device_id="d-1",
    )

    active = memories.list_active_memories("u-1", device_id="d-1")
    assert first.memory_id == second.memory_id
    assert second.version == 2
    assert len(active) == 1
    assert "重新启动" in active[0].content


def test_expired_and_deleted_memories_are_not_recalled(tmp_path):
    _, memories = build_repositories(tmp_path)
    expired = memories.upsert_fault_episode(
        "u-1",
        query="旧故障",
        answer="旧处理结果",
        device_id="d-1",
        ttl_days=-1,
    )
    assert memories.expire_due_memories(datetime.now(timezone.utc)) == 1
    assert memories.list_active_memories("u-1", device_id="d-1") == []

    active = memories.upsert_fault_episode(
        "u-1",
        query="新故障",
        answer="新处理结果",
        device_id="d-1",
    )
    assert memories.delete_user_memory("u-2", active.memory_id) is False
    assert memories.delete_user_memory("u-1", active.memory_id) is True
    assert memories.list_active_memories("u-1", device_id="d-1") == []
    assert expired.status == "active"


def test_profile_conflict_updates_version_and_compaction_limits_events(tmp_path):
    _, memories = build_repositories(tmp_path)
    first = memories.upsert_profile_fact(
        "u-1",
        profile_key="household_pet",
        content="家庭环境中有猫",
    )
    second = memories.upsert_profile_fact(
        "u-1",
        profile_key="household_pet",
        content="家庭环境中有两只猫",
    )
    for index in range(3):
        memories.upsert_fault_episode(
            "u-1",
            query=f"故障 {index}",
            answer=f"处理 {index}",
            device_id="d-1",
        )

    compacted = memories.compact_memories(max_events_per_scope=2)
    active_events = memories.list_active_memories(
        "u-1",
        device_id="d-1",
        memory_type="episodic",
        limit=10,
    )

    assert first.memory_id == second.memory_id
    assert second.version == 2
    assert compacted == 1
    assert len(active_events) == 2
