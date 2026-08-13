from storage.support_repository import SupportRepository


def test_seeded_business_records_are_queryable(tmp_path):
    seed_file = tmp_path / "records.csv"
    seed_file.write_text(
        "user_id,display_name,city,device_id,device_model,purchased_at,warranty_until,month,feature,efficiency,consumables,comparison\n"
        "u-1,Alice,Shanghai,d-1,S9,2026-01-01,2028-01-01,2026-08,cleaned 12 times,95 percent,filter 60 percent,up 2 times\n",
        encoding="utf-8",
    )
    repository = SupportRepository(tmp_path / "support.db")

    repository.seed_business_data(seed_file)
    repository.seed_business_data(seed_file)

    assert [user.user_id for user in repository.list_users()] == ["u-1"]
    assert repository.get_user("u-1").city == "Shanghai"
    assert repository.get_device("u-1")["model"] == "S9"
    assert repository.get_usage_record("u-1", "2026-08").feature == "cleaned 12 times"
    assert repository.get_usage_record("u-1", "2026-07") is None
