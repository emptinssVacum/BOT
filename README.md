# Motivation Bot

Telegram-бот — калькулятор мотивации.

## Что считает
1. К-Эффективности (таргет, ДТК)
2. К-Качества (оценки звонков и чатов)
3. Итоговый KPI
4. Премию

## Формулы
- KPI = 0.5 × Качество + 0.5 × Таргет − СПО + Конверсия
- Премия = Ставка × Выработка × KPI × Дисциплина + Офферы

## Локальный запуск

```bash
# 1. Установить зависимости
python -m venv venv
source venv/bin/activate          # macOS/Linux
# venv\Scripts\activate           # Windows
pip install -r requirements.txt

# 2. Указать токен
export BOT_TOKEN="123456:ABC..."  # macOS/Linux
# $env:BOT_TOKEN="123456:ABC..."  # Windows PowerShell

# 3. Запустить
python bot.py