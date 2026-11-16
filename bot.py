# -*- coding: utf-8 -*-
import asyncio
import os
import re

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# =========================================================
# НАСТРОЙКИ
# =========================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_STR = os.getenv("ADMIN_ID")

if not BOT_TOKEN:
    raise SystemExit("❌ Переменная BOT_TOKEN не задана.")

try:
    ADMIN_ID = int(ADMIN_ID_STR) if ADMIN_ID_STR else None
except ValueError:
    ADMIN_ID = None

BACK_TEXT = "⬅️ Назад"

# =========================================================
# ХЕЛПЕРЫ
# =========================================================
def parse_float(text: str):
    if text is None: return None
    s = text.strip().replace("\u00a0", "").replace(" ", "").replace(",", ".").replace("₽", "").replace("%", "")
    if not s: return None
    try: return float(s)
    except ValueError: return None

def parse_scores(text: str):
    parts = re.split(r"[,;\s]+", text.strip())
    result = []
    for p in parts:
        if not p: continue
        try: v = float(p.replace(",", "."))
        except ValueError: return None
        if v < 0: return None
        result.append(v)
    return result

# Уведомление админа
async def notify_admin(text: str):
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            print(f"Не удалось отправить уведомление админу: {e}")

# =========================================================
# КОЭФФИЦИЕНТЫ И РАСЧЕТЫ
# =========================================================
def eff_coef(p: float) -> float:
    if p < 60: return 0.0
    if p < 65: return 0.3
    if p < 70: return 0.7
    if p < 80: return 1.0
    return 1.1

def calls_coef(s: float) -> float:
    if s < 60: return 0.0
    if s < 75: return 0.3
    if s < 95: return 0.7
    if s < 100: return 1.0
    return 1.1

def chats_coef(s: float) -> float:
    if s < 75: return 0.0
    if s < 90: return 0.3
    if s < 95: return 0.7
    if s < 100: return 1.0
    return 1.1

def calc_quality(calls, chats) -> dict:
    n_calls, n_chats = len(calls), len(chats)
    total = n_calls + n_chats
    if total == 0:
        return {"n_calls": 0, "n_chats": 0, "avg_calls": None, "avg_chats": None, "k_calls": 0.0, "k_chats": 0.0, "share_calls": 0.0, "share_chats": 0.0, "contrib_calls": 0.0, "contrib_chats": 0.0, "kpi": 1.0}
    avg_calls = (sum(calls) / n_calls) if n_calls else None
    avg_chats = (sum(chats) / n_chats) if n_chats else None
    k_calls = calls_coef(avg_calls) if n_calls else 0.0
    k_chats = chats_coef(avg_chats) if n_chats else 0.0
    share_calls = n_calls / total
    share_chats = n_chats / total
    return {"n_calls": n_calls, "n_chats": n_chats, "avg_calls": avg_calls, "avg_chats": avg_chats, "k_calls": k_calls, "k_chats": k_chats, "share_calls": share_calls, "share_chats": share_chats, "contrib_calls": share_calls * k_calls, "contrib_chats": share_chats * k_chats, "kpi": (share_calls * k_calls) + (share_chats * k_chats)}

def calc_overtime(hours: float) -> float:
    if hours <= 0: return 0.0
    if hours <= 15: return hours * 700
    return (15 * 700) + ((hours - 15) * 800)

def fmt2(v: float) -> str: return f"{v:.2f}"
def fmt_money(v: float) -> str: return f"{v:,.0f}".replace(",", " ") + " ₽"

def build_result_text(d: dict) -> str:
    eff_total, eff_target = d["eff_total"], d["eff_target"]
    dtk = (eff_target / eff_total * 100) if eff_total > 0 else 0.0
    k_eff = eff_coef(dtk)
    q = calc_quality(d.get("calls", []), d.get("chats", []))
    
    spo, conv = d["spo"], d["conv"]
    kpi = 0.5 * q["kpi"] + 0.5 * k_eff - spo + conv
    disc, rate, offers = d["discipline"], d["rate"], d["offers"]
    hw, hp, ot_hours = d["hours_worked"], d["hours_planned"], d.get("overtime_hours", 0)
    
    vyrabotka = (hw / hp) if hp > 0 else 0.0
    base_bonus = rate * vyrabotka * kpi * disc
    ot_pay = calc_overtime(ot_hours)
    total_payout = base_bonus + offers + ot_pay

    calls_line = f"• Звонки: {q['n_calls']} оц., ср. {fmt2(q['avg_calls'])} → коэф {fmt2(q['k_calls'])}" if q["n_calls"] else "• Звонки: нет оценок"
    chats_line = f"• Чаты: {q['n_chats']} оц., ср. {fmt2(q['avg_chats'])} → коэф {fmt2(q['k_chats'])}" if q["n_chats"] else "• Чаты: нет оценок"

    return (
        f"✅ <b>Результат расчёта</b>\n\n"
        f"<b>1️⃣ К-Эффективности</b>\n• ДТК: {dtk:.1f}%\n• Коэф: <b>{fmt2(k_eff)}</b>\n\n"
        f"<b>2️⃣ К-Качества</b>\n{calls_line}\n{chats_line}\n• Коэф: <b>{fmt2(q['kpi'])}</b>\n\n"
        f"<b>3️⃣ Итоговый KPI</b>\n<b>{fmt2(kpi)}</b>\n\n"
        f"<b>4️⃣ Финансы</b>\n"
        f"• Базовая премия: {fmt_money(base_bonus)}\n"
        f"• Офферы: {fmt_money(offers)}\n"
        f"• Овертаймы: {fmt_money(ot_pay)}\n"
        f"<b>💰 ИТОГО: {fmt_money(total_payout)}</b>"
    )

# =========================================================
# FSM И КЛАВИАТУРЫ
# =========================================================
class Calc(StatesGroup):
    eff_total = State(); eff_target = State(); calls = State(); chats = State()
    spo = State(); conv = State(); discipline = State(); rate = State()
    offers = State(); hours_worked = State(); hours_planned = State(); overtime_hours = State()

def kb_back(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BACK_TEXT)]], resize_keyboard=True)
def kb_no_scores(): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Нет оценок")], [KeyboardButton(text=BACK_TEXT)]], resize_keyboard=True)
def kb_skip(val: str): return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=f"Пропустить ({val})")], [KeyboardButton(text=BACK_TEXT)]], resize_keyboard=True)
def kb_result(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Новый расчёт", callback_data="start_calc")]])
def kb_start(): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Начать расчёт", callback_data="start_calc")]])

# =========================================================
# BOT + DISPATCHER
# =========================================================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# =========================================================
# КОМАНДЫ И УВЕДОМЛЕНИЯ
# =========================================================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    # УВЕДОМЛЕНИЕ АДМИНУ О НОВОМ ПОЛЬЗОВАТЕЛЕ
    user = message.from_user
    username = f"@{user.username}" if user.username else "нет username"
    await notify_admin(
        f"👤 <b>Кто-то запустил бота!</b>\n"
        f"Имя: {user.full_name}\n"
        f"Логин: {username}\n"
        f"ID: <code>{user.id}</code>"
    )
    
    await message.answer(
        "👋 Привет! Это калькулятор мотивации.\n\n"
        "Я рассчитаю KPI и премию.\nНажми кнопку ниже.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Готов?", reply_markup=kb_start())

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Расчёт отменён. /start — начать заново.", reply_markup=ReplyKeyboardRemove())

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer("ℹ️ Вводи значения по шагам. Оценки пиши через запятую.\nКнопка «Назад» поможет исправить ошибку.")

# =========================================================
# ШАГИ
# =========================================================
@dp.callback_query(F.data == "start_calc")
async def cb_start_calc(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(Calc.eff_total)
    await callback.message.answer("📊 <b>Шаг 1/12.</b> Всего коммуникаций?\nНапример: <code>480</code>", reply_markup=ReplyKeyboardRemove())

@dp.message(Calc.eff_total, F.text)
async def step_eff_total(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT: return await message.answer("Это первый шаг.", reply_markup=ReplyKeyboardRemove())
    val = parse_float(message.text)
    if val is None or val < 0: return await message.answer("⚠️ Введи число.")
    await state.update_data(eff_total=val)
    await state.set_state(Calc.eff_target)
    await message.answer("🎯 <b>Шаг 2/12.</b> Попало в таргет?\nНапример: <code>390</code>", reply_markup=kb_back())

@dp.message(Calc.eff_target, F.text)
async def step_eff_target(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.eff_total)
        return await message.answer("📊 <b>Шаг 1/12.</b> Всего коммуникаций?", reply_markup=ReplyKeyboardRemove())
    val = parse_float(message.text)
    data = await state.get_data()
    if val is None or val < 0: return await message.answer("⚠️ Введи число.")
    if val > data.get("eff_total", 0): return await message.answer("⚠️ Таргет не может быть больше общего числа.")
    await state.update_data(eff_target=val)
    await state.set_state(Calc.calls)
    await message.answer("⭐ <b>Шаг 3/12.</b> Оценки за <b>звонки</b> через запятую.\nПример: <code>100, 80</code>", reply_markup=kb_no_scores())

@dp.message(Calc.calls, F.text)
async def step_calls(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.eff_target)
        return await message.answer("🎯 <b>Шаг 2/12.</b> Попало в таргет?", reply_markup=kb_back())
    text = message.text.strip()
    scores = [] if text.lower().startswith("нет оценок") else parse_scores(text)
    if scores is None: return await message.answer("⚠️ Ошибка ввода. Введи числа через запятую.")
    await state.update_data(calls=scores)
    await state.set_state(Calc.chats)
    await message.answer("💬 <b>Шаг 4/12.</b> Оценки за <b>чаты</b> через запятую.\nПример: <code>100, 0, 50</code>", reply_markup=kb_no_scores())

@dp.message(Calc.chats, F.text)
async def step_chats(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.calls)
        return await message.answer("⭐ <b>Шаг 3/12.</b> Оценки за <b>звонки</b>:", reply_markup=kb_no_scores())
    text = message.text.strip()
    scores = [] if text.lower().startswith("нет оценок") else parse_scores(text)
    if scores is None: return await message.answer("⚠️ Ошибка ввода. Введи числа.")
    await state.update_data(chats=scores)
    await state.set_state(Calc.spo)
    await message.answer("➖ <b>Шаг 5/12.</b> СПО / Постзвонок?\nЕсли 0 — «Пропустить».", reply_markup=kb_skip("0"))

@dp.message(Calc.spo, F.text)
async def step_spo(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.chats)
        return await message.answer("💬 <b>Шаг 4/12.</b> Оценки за <b>чаты</b>:", reply_markup=kb_no_scores())
    val = 0.0 if message.text.strip().startswith("Пропустить") else parse_float(message.text)
    if val is None: return await message.answer("⚠️ Введи число.")
    await state.update_data(spo=val)
    await state.set_state(Calc.conv)
    await message.answer("🔁 <b>Шаг 6/12.</b> Конверсия?\nЕсли 0 — «Пропустить».", reply_markup=kb_skip("0"))

@dp.message(Calc.conv, F.text)
async def step_conv(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.spo)
        return await message.answer("➖ <b>Шаг 5/12.</b> СПО?", reply_markup=kb_skip("0"))
    val = 0.0 if message.text.strip().startswith("Пропустить") else parse_float(message.text)
    if val is None: return await message.answer("⚠️ Введи число.")
    await state.update_data(conv=val)
    await state.set_state(Calc.discipline)
    await message.answer("📋 <b>Шаг 7/12.</b> Дисциплина (коэф).\nПо умолчанию <code>1</code>.", reply_markup=kb_skip("1"))

@dp.message(Calc.discipline, F.text)
async def step_discipline(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.conv)
        return await message.answer("🔁 <b>Шаг 6/12.</b> Конверсия?", reply_markup=kb_skip("0"))
    val = 1.0 if message.text.strip().startswith("Пропустить") else parse_float(message.text)
    if val is None: return await message.answer("⚠️ Введи число.")
    await state.update_data(discipline=val)
    await state.set_state(Calc.rate)
    await message.answer("💵 <b>Шаг 8/12.</b> Ставка премии (₽).\nНапример: <code>10000</code>", reply_markup=kb_back())

@dp.message(Calc.rate, F.text)
async def step_rate(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.discipline)
        return await message.answer("📋 <b>Шаг 7/12.</b> Дисциплина:", reply_markup=kb_skip("1"))
    val = parse_float(message.text)
    if val is None: return await message.answer("⚠️ Введи число.")
    await state.update_data(rate=val)
    await state.set_state(Calc.offers)
    await message.answer("🎁 <b>Шаг 9/12.</b> Сумма за офферы (₽).\nЕсли 0 — «Пропустить».", reply_markup=kb_skip("0"))

@dp.message(Calc.offers, F.text)
async def step_offers(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.rate)
        return await message.answer("💵 <b>Шаг 8/12.</b> Ставка премии:", reply_markup=kb_back())
    val = 0.0 if message.text.strip().startswith("Пропустить") else parse_float(message.text)
    if val is None: return await message.answer("⚠️ Введи число.")
    await state.update_data(offers=val)
    await state.set_state(Calc.hours_worked)
    await message.answer("⏱ <b>Шаг 10/12.</b> Отработано часов.", reply_markup=kb_back())

@dp.message(Calc.hours_worked, F.text)
async def step_hours_worked(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.offers)
        return await message.answer("🎁 <b>Шаг 9/12.</b> Сумма за офферы:", reply_markup=kb_skip("0"))
    val = parse_float(message.text)
    if val is None: return await message.answer("⚠️ Введи число.")
    await state.update_data(hours_worked=val)
    await state.set_state(Calc.hours_planned)
    await message.answer("📅 <b>Шаг 11/12.</b> Запланировано часов.", reply_markup=kb_back())

@dp.message(Calc.hours_planned, F.text)
async def step_hours_planned(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.hours_worked)
        return await message.answer("⏱ <b>Шаг 10/12.</b> Отработано часов:", reply_markup=kb_back())
    val = parse_float(message.text)
    if val is None or val <= 0: return await message.answer("⚠️ Введи число больше нуля.")
    await state.update_data(hours_planned=val)
    await state.set_state(Calc.overtime_hours)
    await message.answer("🔥 <b>Шаг 12/12.</b> Часы овертайма.\n*(1-15 ч. по 700₽, далее по 800₽)*", reply_markup=kb_skip("0"))

@dp.message(Calc.overtime_hours, F.text)
async def step_overtime_hours(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.hours_planned)
        return await message.answer("📅 <b>Шаг 11/12.</b> Запланировано часов:", reply_markup=kb_back())
    
    val = 0.0 if message.text.strip().startswith("Пропустить") else parse_float(message.text)
    if val is None: return await message.answer("⚠️ Введи число.")
    
    await state.update_data(overtime_hours=val)
    data = await state.get_data()
    await state.clear()

    result_text = build_result_text(data)
    await message.answer("✅ Готово! Считаю...", reply_markup=ReplyKeyboardRemove())
    await message.answer(result_text, reply_markup=kb_result())

    # УВЕДОМЛЕНИЕ АДМИНУ О РАСЧЕТЕ
    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name
    
    # Вытаскиваем итоговую сумму для админа
    ot_pay = calc_overtime(val)
    await notify_admin(
        f"📊 <b>Пользователь сделал расчёт!</b>\n"
        f"Кто: {username} (ID: <code>{user.id}</code>)\n"
        f"Овертайм: {val} ч.\n\n"
        f"{result_text}"
    )

# =========================================================
# FALLBACK И ЗАПУСК
# =========================================================
@dp.message()
async def fallback(message: Message):
    await message.answer("Нажми /start, чтобы начать расчёт, или /help.")

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
