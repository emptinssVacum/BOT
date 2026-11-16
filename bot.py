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
if not BOT_TOKEN:
    raise SystemExit(
        "❌ Переменная окружения BOT_TOKEN не задана.\n"
        "Установите её: Railway → Variables → BOT_TOKEN"
    )

BACK_TEXT = "⬅️ Назад"  # Текст кнопки возврата

# =========================================================
# ХЕЛПЕРЫ ПАРСИНГА
# =========================================================
def parse_float(text: str):
    if text is None:
        return None
    s = text.strip().replace("\u00a0", "").replace(" ", "")
    s = s.replace(",", ".").replace("₽", "").replace("%", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_scores(text: str):
    parts = re.split(r"[,;\s]+", text.strip())
    result = []
    for p in parts:
        if not p:
            continue
        try:
            v = float(p.replace(",", "."))
        except ValueError:
            return None
        if v < 0:
            return None
        result.append(v)
    return result


# =========================================================
# КОЭФФИЦИЕНТЫ
# =========================================================
def eff_coef(percent: float) -> float:
    if percent < 60: return 0.0
    if percent < 65: return 0.3
    if percent < 70: return 0.7
    if percent < 80: return 1.0
    return 1.1

def calls_coef(score: float) -> float:
    if score < 60: return 0.0
    if score < 75: return 0.3
    if score < 95: return 0.7
    if score < 100: return 1.0
    return 1.1

def chats_coef(score: float) -> float:
    if score < 75: return 0.0
    if score < 90: return 0.3
    if score < 95: return 0.7
    if score < 100: return 1.0
    return 1.1


# =========================================================
# РАСЧЁТ КАЧЕСТВА
# =========================================================
def calc_quality(calls, chats) -> dict:
    n_calls, n_chats = len(calls), len(chats)
    total = n_calls + n_chats

    if total == 0:
        return {
            "n_calls": 0, "n_chats": 0, "avg_calls": None, "avg_chats": None,
            "k_calls": 0.0, "k_chats": 0.0, "share_calls": 0.0, "share_chats": 0.0,
            "contrib_calls": 0.0, "contrib_chats": 0.0, "kpi": 1.0,
        }

    avg_calls = (sum(calls) / n_calls) if n_calls else None
    avg_chats = (sum(chats) / n_chats) if n_chats else None
    k_calls = calls_coef(avg_calls) if n_calls else 0.0
    k_chats = chats_coef(avg_chats) if n_chats else 0.0
    share_calls = n_calls / total
    share_chats = n_chats / total

    return {
        "n_calls": n_calls, "n_chats": n_chats, "avg_calls": avg_calls, "avg_chats": avg_chats,
        "k_calls": k_calls, "k_chats": k_chats, "share_calls": share_calls, "share_chats": share_chats,
        "contrib_calls": share_calls * k_calls, "contrib_chats": share_chats * k_chats,
        "kpi": (share_calls * k_calls) + (share_chats * k_chats),
    }


# =========================================================
# ФОРМАТИРОВАНИЕ
# =========================================================
def fmt2(v: float) -> str:
    return f"{v:.2f}"

def fmt_money(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ") + " ₽"

def build_result_text(d: dict) -> str:
    eff_total = d["eff_total"]
    eff_target = d["eff_target"]
    dtk = (eff_target / eff_total * 100) if eff_total > 0 else 0.0
    k_eff = eff_coef(dtk)
    q = calc_quality(d.get("calls", []), d.get("chats", []))
    spo = d["spo"]
    conv = d["conv"]
    kpi = 0.5 * q["kpi"] + 0.5 * k_eff - spo + conv

    disc = d["discipline"]
    rate = d["rate"]
    offers = d["offers"]
    hw = d["hours_worked"]
    hp = d["hours_planned"]
    vyrabotka = (hw / hp) if hp > 0 else 0.0
    bonus = rate * vyrabotka * kpi * disc + offers

    calls_line = f"• Звонки: {q['n_calls']} оц., ср. {fmt2(q['avg_calls'])} → коэф {fmt2(q['k_calls'])} (доля {fmt2(q['share_calls'])}, вклад {fmt2(q['contrib_calls'])})" if q["n_calls"] else "• Звонки: нет оценок (коэф 0.00)"
    chats_line = f"• Чаты: {q['n_chats']} оц., ср. {fmt2(q['avg_chats'])} → коэф {fmt2(q['k_chats'])} (доля {fmt2(q['share_chats'])}, вклад {fmt2(q['contrib_chats'])})" if q["n_chats"] else "• Чаты: нет оценок (коэф 0.00)"

    return (
        "✅ <b>Результат расчёта</b>\n\n"
        "<b>1️⃣ К-Эффективности</b>\n"
        f"• Всего коммуникаций: {eff_total:.0f}\n"
        f"• В таргете: {eff_target:.0f}\n"
        f"• ДТК: {dtk:.1f}%\n"
        f"• К-эффективности: <b>{fmt2(k_eff)}</b>\n\n"
        "<b>2️⃣ К-Качества</b>\n"
        f"{calls_line}\n{chats_line}\n"
        f"• К-качества: <b>{fmt2(q['kpi'])}</b>\n\n"
        "<b>3️⃣ Итоговый KPI</b>\n"
        f"(0.5 × {fmt2(q['kpi'])}) + (0.5 × {fmt2(k_eff)}) − {fmt2(spo)} + {fmt2(conv)} = <b>{fmt2(kpi)}</b>\n\n"
        "<b>4️⃣ Премия</b>\n"
        f"• Выработка: {hw:.0f} / {hp:.0f} = {fmt2(vyrabotka)}\n"
        f"• ({rate:.0f} × {fmt2(vyrabotka)} × {fmt2(kpi)} × {fmt2(disc)}) + {offers:.0f}\n"
        f"• Премия: <b>{fmt_money(bonus)}</b>"
    )


# =========================================================
# FSM
# =========================================================
class Calc(StatesGroup):
    eff_total = State()
    eff_target = State()
    calls = State()
    chats = State()
    spo = State()
    conv = State()
    discipline = State()
    rate = State()
    offers = State()
    hours_worked = State()
    hours_planned = State()


# =========================================================
# КЛАВИАТУРЫ
# =========================================================
def kb_back():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BACK_TEXT)]],
        resize_keyboard=True,
    )

def kb_no_scores():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Нет оценок")], [KeyboardButton(text=BACK_TEXT)]],
        resize_keyboard=True,
    )

def kb_skip(value: str):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f"Пропустить ({value})")], [KeyboardButton(text=BACK_TEXT)]],
        resize_keyboard=True,
    )

def kb_result():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Новый расчёт", callback_data="start_calc")]
    ])

def kb_start():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Начать расчёт", callback_data="start_calc")]
    ])


# =========================================================
# BOT + DISPATCHER
# =========================================================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# =========================================================
# КОМАНДЫ
# =========================================================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Привет! Это калькулятор мотивации.\n\n"
        "Я рассчитаю:\n1️⃣ К-Эффективности (таргет)\n2️⃣ К-Качества (оценки)\n"
        "3️⃣ Итоговый KPI\n4️⃣ Премию\n\nНажми кнопку ниже, чтобы начать.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer("Готов?", reply_markup=kb_start())

@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Расчёт отменён. /start — начать заново.", reply_markup=ReplyKeyboardRemove())

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "ℹ️ <b>Как пользоваться</b>\n\n"
        "1. /start — запустить расчёт.\n"
        "2. Вводи значения по шагам.\n"
        "3. Оценки вводятся через запятую: <code>100, 80, 90</code>\n"
        "4. Если ошиблись — нажми кнопку <b>⬅️ Назад</b>, чтобы вернуться на шаг назад.\n"
        "5. Для полей по умолчанию — «Пропустить»."
    )


# =========================================================
# СТАРТ И ШАГИ
# =========================================================
@dp.callback_query(F.data == "start_calc")
async def cb_start_calc(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await state.set_state(Calc.eff_total)
    await callback.message.answer(
        "📊 <b>Шаг 1/11.</b> Сколько всего было коммуникаций?\nНапример: <code>480</code>",
        reply_markup=ReplyKeyboardRemove(),
    )

# --- ШАГ 1: Всего ---
@dp.message(Calc.eff_total, F.text)
async def step_eff_total(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await message.answer("Это первый шаг. Нажмите /start, чтобы выйти в меню.", reply_markup=ReplyKeyboardRemove())
        return
    
    val = parse_float(message.text)
    if val is None or val < 0:
        await message.answer("⚠️ Введи неотрицательное число. Например: 480")
        return
    
    await state.update_data(eff_total=val)
    await state.set_state(Calc.eff_target)
    await message.answer(
        "🎯 <b>Шаг 2/11.</b> Сколько попало в таргет?\nНапример: <code>390</code>",
        reply_markup=kb_back()
    )

# --- ШАГ 2: Таргет ---
@dp.message(Calc.eff_target, F.text)
async def step_eff_target(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.eff_total)
        await message.answer("📊 <b>Шаг 1/11.</b> Сколько всего было коммуникаций?\nНапример: <code>480</code>", reply_markup=ReplyKeyboardRemove())
        return

    val = parse_float(message.text)
    data = await state.get_data()
    total = data.get("eff_total", 0)

    if val is None or val < 0:
        await message.answer("⚠️ Введи неотрицательное число. Например: 390")
        return
    if val > total:
        await message.answer(f"⚠️ В таргет не может попасть больше, чем всего коммуникаций ({total:.0f}).")
        return

    dtk = (val / total * 100) if total > 0 else 0.0
    k_eff = eff_coef(dtk)

    await state.update_data(eff_target=val)
    await state.set_state(Calc.calls)
    await message.answer(
        f"📈 ДТК: <b>{dtk:.1f}%</b> → К-эффективности: <b>{fmt2(k_eff)}</b>\n\n"
        "⭐ <b>Шаг 3/11.</b> Оценки за <b>звонки</b> (через запятую).\nПример: <code>100, 80</code>\n"
        "Если оценок нет — нажми «Нет оценок».",
        reply_markup=kb_no_scores(),
    )

# --- ШАГ 3: Звонки ---
@dp.message(Calc.calls, F.text)
async def step_calls(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.eff_target)
        data = await state.get_data()
        await message.answer(f"🎯 <b>Шаг 2/11.</b> Сколько попало в таргет?\n(Всего было: {data.get('eff_total', 0):.0f})", reply_markup=kb_back())
        return

    text = message.text.strip()
    if text.lower().startswith("нет оценок"):
        scores = []
    else:
        scores = parse_scores(text)
        if scores is None or len(scores) == 0:
            await message.answer("⚠️ Не смог разобрать оценки. Введи числа через запятую, например: <code>100, 80, 90</code>")
            return

    await state.update_data(calls=scores)
    await state.set_state(Calc.chats)
    await message.answer(
        "💬 <b>Шаг 4/11.</b> Оценки за <b>чаты</b> (через запятую).\nПример: <code>100, 0, 50</code>\n"
        "Если оценок нет — нажми «Нет оценок».",
        reply_markup=kb_no_scores(),
    )

# --- ШАГ 4: Чаты ---
@dp.message(Calc.chats, F.text)
async def step_chats(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.calls)
        await message.answer("⭐ <b>Шаг 3/11.</b> Оценки за <b>звонки</b> (через запятую).\nЕсли оценок нет — нажми «Нет оценок».", reply_markup=kb_no_scores())
        return

    text = message.text.strip()
    if text.lower().startswith("нет оценок"):
        scores = []
    else:
        scores = parse_scores(text)
        if scores is None or len(scores) == 0:
            await message.answer("⚠️ Не смог разобрать оценки. Введи числа через запятую, например: <code>100, 80, 90</code>")
            return

    await state.update_data(chats=scores)
    await state.set_state(Calc.spo)
    data = await state.get_data()
    q = calc_quality(data.get("calls", []), data.get("chats", []))

    await message.answer(
        f"📊 Промежуточный К-качества: <b>{fmt2(q['kpi'])}</b>\n\n"
        "➖ <b>Шаг 5/11.</b> СПО / Постзвонок (число).\nЕсли 0 — нажми «Пропустить».",
        reply_markup=kb_skip("0"),
    )

# --- ШАГ 5: СПО ---
@dp.message(Calc.spo, F.text)
async def step_spo(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.chats)
        await message.answer("💬 <b>Шаг 4/11.</b> Оценки за <b>чаты</b> (через запятую).\nЕсли оценок нет — нажми «Нет оценок».", reply_markup=kb_no_scores())
        return

    text = message.text.strip()
    val = 0.0 if text.startswith("Пропустить") else parse_float(text)
    if val is None:
        await message.answer("⚠️ Введи число или нажми «Пропустить (0)».")
        return

    await state.update_data(spo=val)
    await state.set_state(Calc.conv)
    await message.answer("🔁 <b>Шаг 6/11.</b> Конверсия (число).\nЕсли 0 — нажми «Пропустить».", reply_markup=kb_skip("0"))

# --- ШАГ 6: Конверсия ---
@dp.message(Calc.conv, F.text)
async def step_conv(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.spo)
        await message.answer("➖ <b>Шаг 5/11.</b> СПО / Постзвонок (число).\nЕсли 0 — нажми «Пропустить».", reply_markup=kb_skip("0"))
        return

    text = message.text.strip()
    val = 0.0 if text.startswith("Пропустить") else parse_float(text)
    if val is None:
        await message.answer("⚠️ Введи число или нажми «Пропустить (0)».")
        return

    await state.update_data(conv=val)
    await state.set_state(Calc.discipline)
    await message.answer("📋 <b>Шаг 7/11.</b> Дисциплина (коэффициент).\nПо умолчанию <code>1</code>.", reply_markup=kb_skip("1"))

# --- ШАГ 7: Дисциплина ---
@dp.message(Calc.discipline, F.text)
async def step_discipline(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.conv)
        await message.answer("🔁 <b>Шаг 6/11.</b> Конверсия (число).\nЕсли 0 — нажми «Пропустить».", reply_markup=kb_skip("0"))
        return

    text = message.text.strip()
    val = 1.0 if text.startswith("Пропустить") else parse_float(text)
    if val is None or val < 0:
        await message.answer("⚠️ Введи неотрицательное число или нажми «Пропустить (1)».")
        return

    await state.update_data(discipline=val)
    await state.set_state(Calc.rate)
    await message.answer("💵 <b>Шаг 8/11.</b> Ставка премии в ₽ (например <code>10000</code>).", reply_markup=kb_back())

# --- ШАГ 8: Ставка ---
@dp.message(Calc.rate, F.text)
async def step_rate(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.discipline)
        await message.answer("📋 <b>Шаг 7/11.</b> Дисциплина (коэффициент).\nПо умолчанию <code>1</code>.", reply_markup=kb_skip("1"))
        return

    val = parse_float(message.text)
    if val is None or val < 0:
        await message.answer("⚠️ Введи неотрицательное число. Например: 10000")
        return

    await state.update_data(rate=val)
    await state.set_state(Calc.offers)
    await message.answer("🎁 <b>Шаг 9/11.</b> Сумма за офферы в ₽.\nЕсли 0 — нажми «Пропустить».", reply_markup=kb_skip("0"))

# --- ШАГ 9: Офферы ---
@dp.message(Calc.offers, F.text)
async def step_offers(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.rate)
        await message.answer("💵 <b>Шаг 8/11.</b> Ставка премии в ₽ (например <code>10000</code>).", reply_markup=kb_back())
        return

    text = message.text.strip()
    val = 0.0 if text.startswith("Пропустить") else parse_float(text)
    if val is None or val < 0:
        await message.answer("⚠️ Введи неотрицательное число или нажми «Пропустить (0)».")
        return

    await state.update_data(offers=val)
    await state.set_state(Calc.hours_worked)
    await message.answer("⏱ <b>Шаг 10/11.</b> Отработано часов (например <code>160</code>).", reply_markup=kb_back())

# --- ШАГ 10: Отработано часов ---
@dp.message(Calc.hours_worked, F.text)
async def step_hours_worked(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.offers)
        await message.answer("🎁 <b>Шаг 9/11.</b> Сумма за офферы в ₽.\nЕсли 0 — нажми «Пропустить».", reply_markup=kb_skip("0"))
        return

    val = parse_float(message.text)
    if val is None or val < 0:
        await message.answer("⚠️ Введи неотрицательное число. Например: 160")
        return

    await state.update_data(hours_worked=val)
    await state.set_state(Calc.hours_planned)
    await message.answer("📅 <b>Шаг 11/11.</b> Запланировано часов (например <code>160</code>).", reply_markup=kb_back())

# --- ШАГ 11: Запланировано часов ---
@dp.message(Calc.hours_planned, F.text)
async def step_hours_planned(message: Message, state: FSMContext):
    if message.text.strip() == BACK_TEXT:
        await state.set_state(Calc.hours_worked)
        await message.answer("⏱ <b>Шаг 10/11.</b> Отработано часов (например <code>160</code>).", reply_markup=kb_back())
        return

    val = parse_float(message.text)
    if val is None or val <= 0:
        await message.answer("⚠️ Введи положительное число. Например: 160")
        return

    await state.update_data(hours_planned=val)
    data = await state.get_data()
    await state.clear()

    await message.answer("✅ Готово! Считаю...", reply_markup=ReplyKeyboardRemove())
    await message.answer(build_result_text(data), reply_markup=kb_result())


# =========================================================
# FALLBACK И ЗАПУСК
# =========================================================
@dp.message()
async def fallback(message: Message):
    await message.answer(
        "Нажми /start, чтобы начать расчёт, или /help для справки.",
        reply_markup=ReplyKeyboardRemove(),
    )

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())