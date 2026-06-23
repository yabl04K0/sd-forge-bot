import io
import logging
from datetime import datetime
from pathlib import Path

import yaml
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import keyboards as kb
from database import (
    ban_user,
    get_all_users,
    get_total_stats,
    get_user_gallery,
    get_user_limit,
    get_user_request_count,
    get_user_settings,
    increment_user_requests,
    init_db,
    is_user_banned,
    register_user,
    save_to_gallery,
    set_user_limit,
    unban_user,
    update_user_setting,
)
from forge_api import ForgeAPI

# ── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Состояния ConversationHandler ───────────────────────────
WAITING_PROMPT = 1
WAITING_IMG2IMG_PHOTO = 2
WAITING_IMG2IMG_PROMPT = 3
WAITING_NEGATIVE = 4
WAITING_BROADCAST = 5
WAITING_BAN_ID = 6
WAITING_UNBAN_ID = 7
WAITING_LIMIT_ID = 8
WAITING_LIMIT_VALUE = 9

# ── Конфиг ──────────────────────────────────────────────────
def load_config() -> dict:
    with open("config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)

CONFIG = load_config()
ADMIN_ID = CONFIG["telegram"]["admin_id"]
forge = ForgeAPI(CONFIG["forge"]["url"], CONFIG["forge"]["timeout"])
GALLERY_PATH = Path(CONFIG["gallery"]["save_path"])
GALLERY_PATH.mkdir(parents=True, exist_ok=True)

# Временное хранилище для img2img
user_img2img_data: dict[int, bytes] = {}
user_last_params: dict[int, dict] = {}
user_last_image: dict[int, bytes] = {}


# ── Утилиты ─────────────────────────────────────────────────
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


async def check_limits(user_id: int) -> tuple[bool, int, int]:
    """Проверка лимитов. Возвращает (ok, использовано, лимит)"""
    if is_admin(user_id):
        return True, 0, 999
    limit = await get_user_limit(user_id, CONFIG["limits"]["daily_requests"])
    used = await get_user_request_count(user_id)
    return used < limit, used, limit


def format_params(settings: dict, prompt: str) -> str:
    lora_info = f"\n🎭 LoRA: `{settings.get('selected_lora', 'нет')}` ({settings.get('lora_weight', 0.8)})" if settings.get('selected_lora') else ""
    return (
        f"📝 *Промпт:* `{prompt[:200]}`\n"
        f"🔢 Steps: `{settings.get('steps', 25)}` | 🎯 CFG: `{settings.get('cfg_scale', 7.0)}`\n"
        f"📐 Размер: `{settings.get('width', 512)}x{settings.get('height', 768)}`\n"
        f"🔀 Sampler: `{settings.get('sampler', 'Euler a')}`"
        f"{lora_info}"
    )


async def merge_settings_with_defaults(user_id: int) -> dict:
    """Получить настройки пользователя с дефолтами"""
    settings = await get_user_settings(user_id)
    defaults = CONFIG["defaults"]
    if not settings:
        return defaults.copy()
    merged = defaults.copy()
    merged.update({k: v for k, v in settings.items() if v is not None})
    return merged


# ── Команды ─────────────────────────────────────────────────
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await register_user(user.id, user.username or "", user.full_name or "")

    forge_ok = await forge.check_connection()
    status = "✅ Forge подключён" if forge_ok else "❌ Forge недоступен"

    text = (
        f"👋 Привет, *{user.first_name}*!\n\n"
        f"🎨 *SD Forge Telegram Bot*\n"
        f"{status}\n\n"
        f"Отправь промпт текстом для генерации, или используй меню:"
    )

    menu = kb.admin_menu() if is_admin(user.id) else kb.main_menu()
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=menu)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Помощь*\n\n"
        "🎨 Просто напиши промпт — бот сгенерирует картинку\n\n"
        "*Команды:*\n"
        "/start — главное меню\n"
        "/generate — генерация по промпту\n"
        "/settings — настройки генерации\n"
        "/lora — выбор LoRA\n"
        "/model — выбор модели\n"
        "/gallery — твои изображения\n"
        "/profile — мой профиль\n"
        "/help — эта справка\n\n"
        "*Для промпта:*\n"
        "Пиши на английском для лучших результатов.\n"
        "Можно добавить seed: `my prompt --seed 12345`"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


# ── Главное меню (callback) ─────────────────────────────────
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "menu_main":
        menu = kb.admin_menu() if is_admin(user_id) else kb.main_menu()
        await query.edit_message_text("🏠 *Главное меню*", parse_mode=ParseMode.MARKDOWN, reply_markup=menu)

    elif data == "menu_generate":
        await query.edit_message_text(
            "✏️ Введи промпт для генерации:\n\n"
            "_Совет: пиши на английском, добавь `--seed 1234` для конкретного seed_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.cancel_keyboard()
        )
        context.user_data["state"] = WAITING_PROMPT

    elif data == "menu_img2img":
        await query.edit_message_text(
            "📸 Отправь изображение для img2img:",
            reply_markup=kb.cancel_keyboard()
        )
        context.user_data["state"] = WAITING_IMG2IMG_PHOTO

    elif data == "menu_settings":
        settings = await merge_settings_with_defaults(user_id)
        await query.edit_message_text(
            "⚙️ *Настройки генерации*\nТекущие параметры:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.settings_menu(settings)
        )

    elif data == "menu_lora":
        msg = await query.edit_message_text("⏳ Загружаю список LoRA...")
        loras = await forge.get_loras()
        settings = await get_user_settings(user_id)
        current_lora = settings.get("selected_lora")
        if not loras:
            await msg.edit_text("❌ LoRA не найдены или Forge недоступен.", reply_markup=kb.back_keyboard())
            return
        await msg.edit_text(
            f"🎭 *Выбор LoRA*\nТекущая: `{current_lora or 'нет'}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.lora_menu(loras, current_lora)
        )

    elif data == "menu_model":
        msg = await query.edit_message_text("⏳ Загружаю список моделей...")
        models = await forge.get_models()
        current = await forge.get_current_model()
        if not models:
            await msg.edit_text("❌ Модели не найдены или Forge недоступен.", reply_markup=kb.back_keyboard())
            return
        await msg.edit_text(
            f"🤖 *Выбор модели*\nТекущая: `{current[:40]}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.model_menu(models, current)
        )

    elif data == "menu_gallery":
        images = await get_user_gallery(user_id, limit=50)
        if not images:
            await query.edit_message_text(
                "🖼️ Галерея пуста — сгенерируй первое изображение!",
                reply_markup=kb.back_keyboard()
            )
            return
        context.user_data["gallery"] = images
        context.user_data["gallery_page"] = 0
        await show_gallery_page(query, context, user_id, 0)

    elif data == "menu_profile":
        ok, used, limit = await check_limits(user_id)
        stats_rows = await get_user_gallery(user_id, limit=1000)
        total_gen = len(stats_rows)
        settings = await merge_settings_with_defaults(user_id)
        lora = settings.get("selected_lora", "нет")
        current_model = await forge.get_current_model()
        text = (
            f"👤 *Профиль*\n\n"
            f"🆔 ID: `{user_id}`\n"
            f"📊 Запросов сегодня: `{used}/{limit}`\n"
            f"🖼️ Всего сгенерировано: `{total_gen}`\n\n"
            f"*Текущие настройки:*\n"
            f"🤖 Модель: `{current_model[:30]}`\n"
            f"🎭 LoRA: `{lora}`\n"
            f"🔢 Steps: `{settings.get('steps', 25)}`\n"
            f"🎯 CFG: `{settings.get('cfg_scale', 7.0)}`\n"
            f"📐 Размер: `{settings.get('width', 512)}x{settings.get('height', 768)}`\n"
            f"🔀 Sampler: `{settings.get('sampler', 'Euler a')}`"
        )
        menu = kb.admin_menu() if is_admin(user_id) else kb.main_menu()
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=menu)

    elif data == "menu_admin" and is_admin(user_id):
        await query.edit_message_text("👑 *Панель администратора*", parse_mode=ParseMode.MARKDOWN, reply_markup=kb.admin_panel_menu())

    elif data == "noop":
        pass


# ── Настройки ───────────────────────────────────────────────
async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "set_steps":
        await query.edit_message_text("🔢 Выбери количество шагов:", reply_markup=kb.steps_menu())

    elif data.startswith("steps_"):
        steps = int(data.split("_")[1])
        await update_user_setting(user_id, "steps", steps)
        settings = await merge_settings_with_defaults(user_id)
        await query.edit_message_text(
            f"✅ Steps установлен: `{steps}`\n\n⚙️ Настройки:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.settings_menu(settings)
        )

    elif data == "set_cfg":
        await query.edit_message_text("🎯 Выбери CFG Scale:", reply_markup=kb.cfg_menu())

    elif data.startswith("cfg_"):
        cfg = float(data.split("_")[1])
        await update_user_setting(user_id, "cfg_scale", cfg)
        settings = await merge_settings_with_defaults(user_id)
        await query.edit_message_text(
            f"✅ CFG установлен: `{cfg}`\n\n⚙️ Настройки:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.settings_menu(settings)
        )

    elif data == "set_size":
        await query.edit_message_text("📐 Выбери размер изображения:", reply_markup=kb.size_menu())

    elif data.startswith("size_"):
        parts = data.split("_")
        w, h = int(parts[1]), int(parts[2])
        await update_user_setting(user_id, "width", w)
        await update_user_setting(user_id, "height", h)
        settings = await merge_settings_with_defaults(user_id)
        await query.edit_message_text(
            f"✅ Размер: `{w}x{h}`\n\n⚙️ Настройки:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.settings_menu(settings)
        )

    elif data == "set_sampler":
        samplers = await forge.get_samplers()
        if not samplers:
            samplers = CONFIG["options"]["samplers"]
        await query.edit_message_text("🔀 Выбери сэмплер:", reply_markup=kb.sampler_menu(samplers))

    elif data.startswith("sampler_"):
        sampler = data[8:]
        await update_user_setting(user_id, "sampler", sampler)
        settings = await merge_settings_with_defaults(user_id)
        await query.edit_message_text(
            f"✅ Сэмплер: `{sampler}`\n\n⚙️ Настройки:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.settings_menu(settings)
        )

    elif data == "set_scheduler":
        schedulers = await forge.get_schedulers()
        if not schedulers:
            schedulers = CONFIG["options"]["schedulers"]
        await query.edit_message_text("📅 Выбери планировщик:", reply_markup=kb.scheduler_menu(schedulers))

    elif data.startswith("scheduler_"):
        scheduler = data[10:]
        await update_user_setting(user_id, "scheduler", scheduler)
        settings = await merge_settings_with_defaults(user_id)
        await query.edit_message_text(
            f"✅ Scheduler: `{scheduler}`\n\n⚙️ Настройки:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.settings_menu(settings)
        )

    elif data == "set_negative":
        settings = await merge_settings_with_defaults(user_id)
        current_neg = settings.get("negative_prompt", "")
        await query.edit_message_text(
            f"📝 Текущий негативный промпт:\n`{current_neg}`\n\n"
            "Напиши новый негативный промпт:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.cancel_keyboard()
        )
        context.user_data["state"] = WAITING_NEGATIVE

    elif data == "set_lora_weight":
        await query.edit_message_text("⚖️ Выбери вес LoRA:", reply_markup=kb.lora_weight_menu())

    elif data.startswith("loraw_"):
        weight = float(data.split("_")[1])
        await update_user_setting(user_id, "lora_weight", weight)
        settings = await merge_settings_with_defaults(user_id)
        await query.edit_message_text(
            f"✅ Вес LoRA: `{weight}`\n\n⚙️ Настройки:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.settings_menu(settings)
        )


# ── LoRA и Модели ───────────────────────────────────────────
async def lora_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "lora_none":
        await update_user_setting(user_id, "selected_lora", None)
        loras = await forge.get_loras()
        await query.edit_message_text(
            "✅ LoRA отключена\n\n🎭 *Выбор LoRA:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.lora_menu(loras, None)
        )

    elif data.startswith("lora_select_"):
        lora_name = data[12:]
        await update_user_setting(user_id, "selected_lora", lora_name)
        loras = await forge.get_loras()
        await query.edit_message_text(
            f"✅ LoRA выбрана: `{lora_name}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.lora_menu(loras, lora_name)
        )


async def model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("model_"):
        model_name = data[6:]
        msg = await query.edit_message_text(f"⏳ Загружаю модель `{model_name}`...", parse_mode=ParseMode.MARKDOWN)
        success = await forge.set_model(model_name)
        if success:
            current = await forge.get_current_model()
            models = await forge.get_models()
            await msg.edit_text(
                f"✅ Модель загружена: `{model_name}`",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=kb.model_menu(models, current)
            )
        else:
            await msg.edit_text("❌ Ошибка загрузки модели.", reply_markup=kb.back_keyboard("menu_model"))


# ── Генерация ────────────────────────────────────────────────
async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str, img_bytes: bytes | None = None):
    """Основная функция генерации"""
    user_id = update.effective_user.id

    # Проверка лимитов
    ok, used, limit = await check_limits(user_id)
    if not ok:
        text = f"⛔ Лимит исчерпан: `{used}/{limit}` запросов сегодня."
        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
        elif update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        return

    # Проверка бана
    if await is_user_banned(user_id):
        return

    # Получить настройки
    settings = await merge_settings_with_defaults(user_id)

    # Парсинг seed из промпта
    seed = -1
    if "--seed" in prompt:
        parts = prompt.split("--seed")
        prompt = parts[0].strip()
        try:
            seed = int(parts[1].strip().split()[0])
        except Exception:
            seed = -1

    settings["prompt"] = prompt
    settings["seed"] = seed

    # Статусное сообщение
    status_text = f"⏳ Генерирую...\n{format_params(settings, prompt)}"
    if update.message:
        status_msg = await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)
    else:
        status_msg = await update.callback_query.edit_message_text(status_text, parse_mode=ParseMode.MARKDOWN)

    try:
        if img_bytes:
            image_data, info = await forge.img2img(img_bytes, settings)
        else:
            image_data, info = await forge.txt2img(settings)

        if not image_data:
            await status_msg.edit_text("❌ Ошибка генерации. Проверь Forge.", reply_markup=kb.back_keyboard())
            return

        # Увеличить счётчик
        await increment_user_requests(user_id)

        # Сохранить на ПК
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{user_id}_{timestamp}.png"
        file_path = GALLERY_PATH / filename
        with open(file_path, "wb") as f:
            f.write(image_data)

        # Сохранить в БД
        actual_seed = info.get("seed", seed)
        params_for_db = {**settings, "seed": actual_seed}
        await save_to_gallery(user_id, str(file_path), params_for_db)

        # Сохранить для повтора
        user_last_params[user_id] = {**settings, "seed": actual_seed}
        user_last_image[user_id] = image_data

        # Отправить изображение
        caption = (
            f"✅ Готово!\n"
            f"🌱 Seed: `{actual_seed}`\n"
            f"🔢 Steps: `{settings.get('steps')}` | 🎯 CFG: `{settings.get('cfg_scale')}`\n"
            f"📐 `{settings.get('width')}x{settings.get('height')}`"
        )
        await status_msg.delete()
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=io.BytesIO(image_data),
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.after_generation_menu(actual_seed)
        )

    except Exception as e:
        logger.error(f"Generation error: {e}")
        await status_msg.edit_text(
            f"❌ Ошибка: `{str(e)[:100]}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.back_keyboard()
        )


# ── После генерации ─────────────────────────────────────────
async def after_gen_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "gen_repeat":
        params = user_last_params.get(user_id)
        if not params:
            await query.edit_message_text("❌ Нет данных для повтора.", reply_markup=kb.back_keyboard())
            return
        params["seed"] = -1
        await generate_image(update, context, params.get("prompt", ""))

    elif data.startswith("gen_same_seed_"):
        seed = int(data.split("_")[-1])
        params = user_last_params.get(user_id)
        if not params:
            await query.edit_message_text("❌ Нет данных.", reply_markup=kb.back_keyboard())
            return
        params["seed"] = seed
        await generate_image(update, context, params.get("prompt", ""))

    elif data == "gen_img2img":
        last_img = user_last_image.get(user_id)
        if not last_img:
            await query.edit_message_text("❌ Нет изображения.", reply_markup=kb.back_keyboard())
            return
        user_img2img_data[user_id] = last_img
        await query.edit_message_text(
            "✏️ Введи промпт для img2img (или /skip чтобы использовать тот же):",
            reply_markup=kb.cancel_keyboard()
        )
        context.user_data["state"] = WAITING_IMG2IMG_PROMPT

    elif data == "gen_upscale":
        last_img = user_last_image.get(user_id)
        if not last_img:
            await query.edit_message_text("❌ Нет изображения.", reply_markup=kb.back_keyboard())
            return
        await query.edit_message_text("⬆️ Выбери масштаб апскейла:", reply_markup=kb.upscaler_menu([]))


async def upscale_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("upscale_"):
        scale = float(data.split("_")[1])
        last_img = user_last_image.get(user_id)
        if not last_img:
            await query.edit_message_text("❌ Нет изображения.", reply_markup=kb.back_keyboard())
            return
        msg = await query.edit_message_text(f"⏳ Апскейл x{scale}...")
        result = await forge.upscale(last_img, scale=scale)
        if result:
            user_last_image[user_id] = result
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = GALLERY_PATH / f"{user_id}_{timestamp}_upscaled.png"
            with open(file_path, "wb") as f:
                f.write(result)
            await msg.delete()
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=io.BytesIO(result),
                caption=f"✅ Апскейл x{scale} готов!",
                reply_markup=kb.back_keyboard()
            )
        else:
            await msg.edit_text("❌ Ошибка апскейла.", reply_markup=kb.back_keyboard())


# ── Галерея ─────────────────────────────────────────────────
async def show_gallery_page(query, context: ContextTypes.DEFAULT_TYPE, user_id: int, page: int):
    images = context.user_data.get("gallery", [])
    per_page = 5
    start = page * per_page
    end = start + per_page
    page_images = images[start:end]

    if not page_images:
        await query.edit_message_text("📭 Страница пуста.", reply_markup=kb.back_keyboard())
        return

    text = f"🖼️ *Галерея* (страница {page+1}):\n\n"
    for i, img in enumerate(page_images, 1):
        text += (
            f"*{start+i}.* `{img.get('prompt', '')[:40]}`\n"
            f"   Seed: `{img.get('seed', '?')}` | {img.get('created_at', '')[:16]}\n\n"
        )

    await query.edit_message_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.gallery_menu(page, len(images))
    )


async def gallery_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data.startswith("gallery_page_"):
        page = int(data.split("_")[-1])
        context.user_data["gallery_page"] = page
        await show_gallery_page(query, context, user_id, page)


# ── Обработка входящих сообщений ────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await register_user(user.id, user.username or "", user.full_name or "")

    if await is_user_banned(user.id):
        return

    state = context.user_data.get("state")

    if state == WAITING_PROMPT:
        context.user_data.pop("state", None)
        await generate_image(update, context, update.message.text)

    elif state == WAITING_NEGATIVE:
        context.user_data.pop("state", None)
        new_neg = update.message.text
        await update_user_setting(user.id, "negative_prompt", new_neg)
        settings = await merge_settings_with_defaults(user.id)
        await update.message.reply_text(
            f"✅ Негативный промпт обновлён:\n`{new_neg[:200]}`",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb.settings_menu(settings)
        )

    elif state == WAITING_IMG2IMG_PROMPT:
        context.user_data.pop("state", None)
        prompt = update.message.text
        img_bytes = user_img2img_data.get(user.id)
        if not img_bytes:
            await update.message.reply_text("❌ Изображение не найдено.")
            return
        await generate_image(update, context, prompt, img_bytes=img_bytes)

    elif state == WAITING_BROADCAST and is_admin(user.id):
        context.user_data.pop("state", None)
        text = update.message.text
        users = await get_all_users()
        sent = 0
        for u in users:
            try:
                await context.bot.send_message(u["user_id"], f"📢 {text}")
                sent += 1
            except Exception:
                pass
        await update.message.reply_text(f"✅ Рассылка отправлена: {sent}/{len(users)}")

    elif state == WAITING_BAN_ID and is_admin(user.id):
        context.user_data.pop("state", None)
        try:
            target_id = int(update.message.text.strip())
            await ban_user(target_id)
            await update.message.reply_text(f"🚫 Пользователь `{target_id}` забанен.", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ Неверный ID.")

    elif state == WAITING_UNBAN_ID and is_admin(user.id):
        context.user_data.pop("state", None)
        try:
            target_id = int(update.message.text.strip())
            await unban_user(target_id)
            await update.message.reply_text(f"✅ Пользователь `{target_id}` разбанен.", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ Неверный ID.")

    elif state == WAITING_LIMIT_ID and is_admin(user.id):
        try:
            target_id = int(update.message.text.strip())
            context.user_data["limit_target_id"] = target_id
            context.user_data["state"] = WAITING_LIMIT_VALUE
            await update.message.reply_text(f"Введи новый лимит для пользователя `{target_id}`:", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ Неверный ID.")
            context.user_data.pop("state", None)

    elif state == WAITING_LIMIT_VALUE and is_admin(user.id):
        context.user_data.pop("state", None)
        target_id = context.user_data.pop("limit_target_id", None)
        try:
            limit_val = int(update.message.text.strip())
            if target_id:
                await set_user_limit(target_id, limit_val)
                await update.message.reply_text(f"✅ Лимит для `{target_id}` = `{limit_val}`/день", parse_mode=ParseMode.MARKDOWN)
        except ValueError:
            await update.message.reply_text("❌ Неверное число.")

    else:
        # Нет состояния — интерпретируем как промпт
        if update.message.text and not update.message.text.startswith("/"):
            await generate_image(update, context, update.message.text)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото (для img2img)"""
    user_id = update.effective_user.id
    state = context.user_data.get("state")

    if state == WAITING_IMG2IMG_PHOTO:
        context.user_data.pop("state", None)
        photo = update.message.photo[-1]
        file = await photo.get_file()
        img_bytes = await file.download_as_bytearray()
        user_img2img_data[user_id] = bytes(img_bytes)

        await update.message.reply_text(
            "✅ Фото получено! Введи промпт для img2img:",
            reply_markup=kb.cancel_keyboard()
        )
        context.user_data["state"] = WAITING_IMG2IMG_PROMPT
    else:
        # Попробовать прочитать метаданные PNG
        photo = update.message.photo[-1]
        file = await photo.get_file()
        img_bytes = bytes(await file.download_as_bytearray())
        info = await forge.png_info(img_bytes)
        parameters = info.get("info", "")
        if parameters:
            await update.message.reply_text(
                f"📋 *Параметры изображения:*\n```\n{parameters[:800]}\n```",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                "📸 Отправь это фото для img2img?",
                reply_markup=InlineKeyboardMarkup([
                    [{"text": "✅ Да", "callback_data": "start_img2img_from_photo"}]
                ])
            )
            user_img2img_data[user_id] = img_bytes


# ── Адмнин callbacks ─────────────────────────────────────────
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id):
        await query.answer("⛔ Только для администратора", show_alert=True)
        return

    data = query.data

    if data == "admin_stats":
        stats = await get_total_stats()
        forge_ok = await forge.check_connection()
        current_model = await forge.get_current_model()
        text = (
            f"📊 *Статистика*\n\n"
            f"👥 Пользователей: `{stats['total_users']}`\n"
            f"📨 Запросов сегодня: `{stats['today_requests']}`\n"
            f"🖼️ Всего изображений: `{stats['total_images']}`\n\n"
            f"🔌 Forge: {'✅ Онлайн' if forge_ok else '❌ Офлайн'}\n"
            f"🤖 Модель: `{current_model[:40]}`"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb.admin_panel_menu())

    elif data == "admin_users":
        users = await get_all_users()
        text = f"👥 *Пользователи* ({len(users)}):\n\n"
        for u in users[:20]:
            banned = "🚫" if u["is_banned"] else "✅"
            text += f"{banned} `{u['user_id']}` — {u.get('full_name', '')[:20]}\n"
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb.admin_panel_menu())

    elif data == "admin_ban":
        await query.edit_message_text("🚫 Введи ID пользователя для бана:", reply_markup=kb.cancel_keyboard())
        context.user_data["state"] = WAITING_BAN_ID

    elif data == "admin_unban":
        await query.edit_message_text("✅ Введи ID пользователя для разбана:", reply_markup=kb.cancel_keyboard())
        context.user_data["state"] = WAITING_UNBAN_ID

    elif data == "admin_broadcast":
        await query.edit_message_text("📨 Введи текст рассылки:", reply_markup=kb.cancel_keyboard())
        context.user_data["state"] = WAITING_BROADCAST

    elif data == "admin_set_limit":
        await query.edit_message_text("⚙️ Введи ID пользователя для изменения лимита:", reply_markup=kb.cancel_keyboard())
        context.user_data["state"] = WAITING_LIMIT_ID

    elif data == "admin_forge_status":
        forge_ok = await forge.check_connection()
        progress = await forge.get_progress()
        prog_pct = int(progress.get("progress", 0) * 100)
        current_model = await forge.get_current_model()
        loras = await forge.get_loras()
        text = (
            f"🔌 *Статус Forge*\n\n"
            f"Статус: {'✅ Онлайн' if forge_ok else '❌ Офлайн'}\n"
            f"Прогресс: `{prog_pct}%`\n"
            f"Модель: `{current_model[:40]}`\n"
            f"LoRA загружено: `{len(loras)}`"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb.admin_panel_menu())

    elif data == "admin_interrupt":
        ok = await forge.interrupt()
        await query.answer("⛔ Генерация остановлена" if ok else "❌ Ошибка", show_alert=True)


# ── Команды shortcuts ────────────────────────────────────────
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = await merge_settings_with_defaults(user_id)
    await update.message.reply_text(
        "⚙️ *Настройки генерации:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.settings_menu(settings)
    )


async def lora_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    loras = await forge.get_loras()
    settings = await get_user_settings(user_id)
    current_lora = settings.get("selected_lora")
    await update.message.reply_text(
        f"🎭 *Выбор LoRA*\nТекущая: `{current_lora or 'нет'}`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.lora_menu(loras, current_lora)
    )


async def gallery_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    images = await get_user_gallery(user_id, limit=50)
    if not images:
        await update.message.reply_text("🖼️ Галерея пуста!", reply_markup=kb.back_keyboard())
        return
    context.user_data["gallery"] = images
    context.user_data["gallery_page"] = 0
    page_images = images[:5]
    text = "🖼️ *Галерея* (стр. 1):\n\n"
    for i, img in enumerate(page_images, 1):
        text += (
            f"*{i}.* `{img.get('prompt', '')[:40]}`\n"
            f"   Seed: `{img.get('seed', '?')}` | {img.get('created_at', '')[:16]}\n\n"
        )
    await update.message.reply_text(
        text, parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.gallery_menu(0, len(images))
    )


async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    models = await forge.get_models()
    current = await forge.get_current_model()
    await update.message.reply_text(
        f"🤖 *Модели*\nТекущая: `{current[:40]}`",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb.model_menu(models, current)
    )


# ── Запуск ──────────────────────────────────────────────────
async def post_init(application):
    await init_db()
    logger.info("База данных инициализирована")
    forge_ok = await forge.check_connection()
    if forge_ok:
        logger.info(f"Forge подключён: {CONFIG['forge']['url']}")
    else:
        logger.warning(f"Forge недоступен: {CONFIG['forge']['url']}")


def main():
    token = CONFIG["telegram"]["token"]
    app = Application.builder().token(token).post_init(post_init).build()

    # Команды
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("lora", lora_command))
    app.add_handler(CommandHandler("gallery", gallery_command))
    app.add_handler(CommandHandler("model", model_command))

    # Callbacks
    app.add_handler(CallbackQueryHandler(menu_callback, pattern="^menu_"))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^(set_|steps_|cfg_|size_|sampler_|scheduler_|loraw_)"))
    app.add_handler(CallbackQueryHandler(lora_callback, pattern="^lora_"))
    app.add_handler(CallbackQueryHandler(model_callback, pattern="^model_"))
    app.add_handler(CallbackQueryHandler(after_gen_callback, pattern="^gen_"))
    app.add_handler(CallbackQueryHandler(upscale_callback, pattern="^upscale_"))
    app.add_handler(CallbackQueryHandler(gallery_callback, pattern="^gallery_"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))

    # Сообщения
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
