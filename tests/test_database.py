"""Регрессия: выбранная LoRA должна попадать в галерею.

До фикта save_to_gallery читал params.get("lora"), а настройки хранят ключ
`selected_lora` → столбец lora всегда оставался пустым.
"""
import database
from database import get_user_gallery, init_db, save_to_gallery


async def test_gallery_records_selected_lora(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    await init_db()
    await save_to_gallery(
        1, "/tmp/x.png", {"prompt": "cat", "selected_lora": "myLora", "seed": 5}
    )
    rows = await get_user_gallery(1)
    assert len(rows) == 1
    assert rows[0]["lora"] == "myLora"
    assert rows[0]["prompt"] == "cat"


async def test_gallery_lora_empty_when_none(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    await init_db()
    await save_to_gallery(1, "/tmp/x.png", {"prompt": "cat", "seed": 5})
    rows = await get_user_gallery(1)
    assert rows[0]["lora"] == ""
