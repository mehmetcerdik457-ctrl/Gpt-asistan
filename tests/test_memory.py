from memory import MemoryStorage


def test_memory_search_export_import_and_clear(tmp_path):
    storage = MemoryStorage(tmp_path / "source.db")
    assert storage.store("a useful note")
    assert storage.store("100%_literal")

    assert [entry["text"] for entry in storage.search("useful")] == ["a useful note"]
    assert [entry["text"] for entry in storage.search("%_")] == ["100%_literal"]

    backup = tmp_path / "backup.json"
    storage.export_json(backup)
    restored = MemoryStorage(tmp_path / "restored.db")
    assert restored.import_json(backup) == 2
    assert [entry["text"] for entry in restored.retrieve()] == [
        "a useful note",
        "100%_literal",
    ]

    restored.clear()
    assert restored.retrieve() == []
