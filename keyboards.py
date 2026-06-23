from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from typing import List, Dict, Optional


# ── Главное меню ────────────────────────────────────────────
def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎨 Генерация", callback_data="menu_generate"),
            InlineKeyboardButton("🖼️ img2img", callback_data="menu_img2img"),
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings"),
            InlineKeyboardButton("🖼️ Галерея", callback_data="menu_gallery"),
        ],
        [
            InlineKeyboardButton("🤖 Модель", callback_data="menu_model"),
            InlineKeyboardButton("🎭 LoRA", callback_data="menu_lora"),
        ],
        [
            InlineKeyboardButton("📊 Мой профиль", callback_data="menu_profile"),
        ],
    ])


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎨 Генерация", callback_data="menu_generate"),
            InlineKeyboardButton("🖼️ img2img", callback_data="menu_img2img"),
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings"),
            InlineKeyboardButton("🖼️ Галерея", callback_data="menu_gallery"),
        ],
        [
            InlineKeyboardButton("🤖 Модель", callback_data="menu_model"),
            InlineKeyboardButton("🎭 LoRA", callback_data="menu_lora"),
        ],
        [
            InlineKeyboardButton("📊 Мой профиль", callback_data="menu_profile"),
            InlineKeyboardButton("👑 Админ", callback_data="menu_admin"),
        ],
    ])


# ── Меню настроек ───────────────────────────────────────────
def settings_menu(settings: Dict) -> InlineKeyboardMarkup:
    lora_label = f"🎭 LoRA: {settings.get('selected_lora', 'нет')[:12]}" if settings.get('selected_lora') else "🎭 LoRA: нет"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🔢 Steps: {settings.get('steps', 25)}", callback_data="set_steps"),
            InlineKeyboardButton(f"🎯 CFG: {settings.get('cfg_scale', 7.0)}", callback_data="set_cfg"),
        ],
        [
            InlineKeyboardButton(f"📐 Размер: {settings.get('width', 512)}x{settings.get('height', 768)}", callback_data="set_size"),
            InlineKeyboardButton(f"🔀 Sampler", callback_data="set_sampler"),
        ],
        [
            InlineKeyboardButton(f"📅 Scheduler", callback_data="set_scheduler"),
            InlineKeyboardButton(f"⚖️ LoRA вес: {settings.get('lora_weight', 0.8)}", callback_data="set_lora_weight"),
        ],
        [
            InlineKeyboardButton("📝 Негативный промпт", callback_data="set_negative"),
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data="menu_main"),
        ],
    ])


# ── Выбор Steps ─────────────────────────────────────────────
def steps_menu() -> InlineKeyboardMarkup:
    steps_options = [10, 15, 20, 25, 30, 35, 40, 50, 60, 80]
    rows = []
    row = []
    for s in steps_options:
        row.append(InlineKeyboardButton(str(s), callback_data=f"steps_{s}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="menu_settings")])
    return InlineKeyboardMarkup(rows)


# ── Выбор CFG ───────────────────────────────────────────────
def cfg_menu() -> InlineKeyboardMarkup:
    cfg_options = [1.0, 3.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0, 15.0]
    rows = []
    row = []
    for c in cfg_options:
        row.append(InlineKeyboardButton(str(c), callback_data=f"cfg_{c}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="menu_settings")])
    return InlineKeyboardMarkup(rows)


# ── Выбор размера ───────────────────────────────────────────
def size_menu() -> InlineKeyboardMarkup:
    sizes = [
        ("512x512", "512", "512"),
        ("512x768", "512", "768"),
        ("768x512", "768", "512"),
        ("768x768", "768", "768"),
        ("768x1024", "768", "1024"),
        ("1024x768", "1024", "768"),
        ("1024x1024", "1024", "1024"),
        ("832x1216", "832", "1216"),
        ("1216x832", "1216", "832"),
    ]
    rows = []
    row = []
    for label, w, h in sizes:
        row.append(InlineKeyboardButton(label, callback_data=f"size_{w}_{h}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="menu_settings")])
    return InlineKeyboardMarkup(rows)


# ── Выбор сэмплера ──────────────────────────────────────────
def sampler_menu(samplers: List[str]) -> InlineKeyboardMarkup:
    rows = []
    for s in samplers[:20]:
        rows.append([InlineKeyboardButton(s, callback_data=f"sampler_{s[:40]}")])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="menu_settings")])
    return InlineKeyboardMarkup(rows)


# ── Выбор шедулера ──────────────────────────────────────────
def scheduler_menu(schedulers: List[str]) -> InlineKeyboardMarkup:
    rows = []
    for s in schedulers[:15]:
        rows.append([InlineKeyboardButton(s, callback_data=f"scheduler_{s[:40]}")])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="menu_settings")])
    return InlineKeyboardMarkup(rows)


# ── Выбор LoRA ──────────────────────────────────────────────
def lora_menu(loras: List[Dict], current_lora: Optional[str] = None) -> InlineKeyboardMarkup:
    rows = []
    # Кнопка "без LoRA"
    no_lora_label = "✅ Без LoRA" if not current_lora else "❌ Без LoRA"
    rows.append([InlineKeyboardButton(no_lora_label, callback_data="lora_none")])

    for lora in loras[:20]:
        name = lora.get("name", lora.get("alias", "unknown"))
        label = f"✅ {name[:25]}" if name == current_lora else f"🎭 {name[:25]}"
        rows.append([InlineKeyboardButton(label, callback_data=f"lora_select_{name[:40]}")])

    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


# ── Выбор LoRA веса ─────────────────────────────────────────
def lora_weight_menu() -> InlineKeyboardMarkup:
    weights = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2]
    rows = []
    row = []
    for w in weights:
        row.append(InlineKeyboardButton(str(w), callback_data=f"loraw_{w}"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="menu_settings")])
    return InlineKeyboardMarkup(rows)


# ── Выбор модели ────────────────────────────────────────────
def model_menu(models: List[Dict], current_model: str) -> InlineKeyboardMarkup:
    rows = []
    for model in models[:20]:
        name = model.get("model_name", model.get("title", "unknown"))
        label = f"✅ {name[:28]}" if name in current_model or current_model in name else f"🤖 {name[:28]}"
        rows.append([InlineKeyboardButton(label, callback_data=f"model_{name[:40]}")])
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


# ── После генерации ─────────────────────────────────────────
def after_generation_menu(seed: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔁 Повторить", callback_data="gen_repeat"),
            InlineKeyboardButton(f"🌱 Тот же seed ({seed})", callback_data=f"gen_same_seed_{seed}"),
        ],
        [
            InlineKeyboardButton("✏️ img2img", callback_data="gen_img2img"),
            InlineKeyboardButton("⬆️ Апскейл", callback_data="gen_upscale"),
        ],
        [
            InlineKeyboardButton("🏠 Главное меню", callback_data="menu_main"),
        ],
    ])


# ── Галерея ─────────────────────────────────────────────────
def gallery_menu(page: int, total: int, per_page: int = 5) -> InlineKeyboardMarkup:
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"gallery_page_{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{(total-1)//per_page+1}", callback_data="noop"))
    if (page + 1) * per_page < total:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"gallery_page_{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔙 Назад", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


# ── Админ панель ────────────────────────────────────────────
def admin_panel_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 Все пользователи", callback_data="admin_users"),
            InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        ],
        [
            InlineKeyboardButton("🚫 Забанить", callback_data="admin_ban"),
            InlineKeyboardButton("✅ Разбанить", callback_data="admin_unban"),
        ],
        [
            InlineKeyboardButton("📨 Рассылка", callback_data="admin_broadcast"),
            InlineKeyboardButton("⚙️ Лимит юзера", callback_data="admin_set_limit"),
        ],
        [
            InlineKeyboardButton("🔌 Статус Forge", callback_data="admin_forge_status"),
            InlineKeyboardButton("⛔ Стоп генерацию", callback_data="admin_interrupt"),
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data="menu_main"),
        ],
    ])


# ── Выбор апскейлера ────────────────────────────────────────
def upscaler_menu(upscalers: List[str]) -> InlineKeyboardMarkup:
    rows = []
    scales = [
        InlineKeyboardButton("x1.5", callback_data="upscale_1.5"),
        InlineKeyboardButton("x2", callback_data="upscale_2.0"),
        InlineKeyboardButton("x4", callback_data="upscale_4.0"),
    ]
    rows.append(scales)
    rows.append([InlineKeyboardButton("🔙 Отмена", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Отмена", callback_data="menu_main")]
    ])


def back_keyboard(target: str = "menu_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад", callback_data=target)]
    ])
