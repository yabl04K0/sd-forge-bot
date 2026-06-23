"""Регрессия: callback_data обрезается до 40 символов, хендлер обязан
восстановить полное имя модели/LoRA, иначе set_model/<lora:...> получают
обрезанное (неверное) имя.

Импорт bot требует python-telegram-bot; где зависимостей нет — тест пропускается.
"""
import pytest

try:
    from bot import resolve_full_name
except BaseException:  # noqa: BLE001 - telegram/cryptography может паниковать (не Exception)
    resolve_full_name = None

pytestmark = pytest.mark.skipif(
    resolve_full_name is None, reason="bot зависимости недоступны в этом окружении"
)


def test_resolve_truncated_prefix_to_full_name():
    full = "veryLongModelName_v3_fp16_pruned_emaonly.safetensors"
    assert len(full) > 40
    assert resolve_full_name(full[:40], [full]) == full


def test_resolve_prefers_exact_match():
    assert resolve_full_name("exact", ["other", "exact", "exactlonger"]) == "exact"


def test_resolve_unknown_returns_prefix():
    assert resolve_full_name("missing", ["a", "b"]) == "missing"
