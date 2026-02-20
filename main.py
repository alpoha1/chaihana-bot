import asyncio
import sqlite3
from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command

TOKEN = "8557847306:AAGEnxTt3sZT05HjOlV4cusH02cCPfmVX60"

bot = Bot(TOKEN)
dp = Dispatcher()

# ================= DATABASE =================

conn = sqlite3.connect("game.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    tea INTEGER DEFAULT 0,
    business_level INTEGER DEFAULT 1,
    resources INTEGER DEFAULT 0,
    tax_level INTEGER DEFAULT 0,
    tax_due INTEGER DEFAULT 0,
    tax_timer TEXT,
    frozen INTEGER DEFAULT 0,
    warned INTEGER DEFAULT 0
)
""")
conn.commit()


def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        return get_user(user_id)

    return user


def update_user(user_id, field, value):
    cursor.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()


# ================= БИЗНЕС =================

BUSINESS_LEVELS = {
    1: "Полиэстр",
    2: "Хлопок",
    3: "Шерсть медведя",
    4: "Золотая ткань",
    5: "Кожа крокодила"
}

UPGRADE_REQUIREMENTS = {
    1: {"res": 100, "tea": 200},   # <-- поставь свои значения
    2: {"res": 250, "tea": 500},
    3: {"res": 500, "tea": 1000},
    4: {"res": 1000, "tea": 2500},
}

# ================= JOB =================

@dp.message(Command("job"))
async def job(message: Message):
    user = get_user(message.from_user.id)

    level = user[2]
    frozen = user[7]
    tax_level = user[4]

    if frozen:
        await message.answer("❄ Бизнес заморожен.")
        return

    base_res = 10   # <-- можешь менять
    base_tea = 20   # <-- можешь менять

    if tax_level == 1:
        base_res *= 0.5
        base_tea *= 0.5

    update_user(message.from_user.id, "resources", user[3] + base_res)
    update_user(message.from_user.id, "tea", user[1] + base_tea)

    await message.answer(
        f"Ты добыл {base_res} ресурса ({BUSINESS_LEVELS[level]})\n"
        f"+{base_tea} чая"
    )


# ================= BUSINESS =================

@dp.message(Command("business"))
async def business(message: Message):
    text = "🏭 Уровни бизнеса:\n\n"

    for lvl in BUSINESS_LEVELS:
        text += f"{lvl}. {BUSINESS_LEVELS[lvl]}\n"

        if lvl in UPGRADE_REQUIREMENTS:
            req = UPGRADE_REQUIREMENTS[lvl]
            text += f"   Нужно: {req['res']} ресурсов + {req['tea']} чая\n"

        text += "\n"

    text += "Бонусы остаются прежними."

    await message.answer(text)


# ================= PROFILE =================

@dp.message(Command("profile"))
async def profile(message: Message):
    user = get_user(message.from_user.id)
    level = user[2]

    text = (
        f"📊 Профиль\n\n"
        f"Уровень бизнеса: {level} ({BUSINESS_LEVELS[level]})\n"
        f"Ресурсы: {user[3]}\n"
        f"Чай: {user[1]}\n"
    )

    if level in UPGRADE_REQUIREMENTS:
        req = UPGRADE_REQUIREMENTS[level]
        text += f"\nДо апгрейда нужно: {req['res']} ресурсов + {req['tea']} чая"

    await message.answer(text)


# ================= НАЛОГ =================

@dp.message(Command("nalog"))
async def nalog(message: Message):
    user = get_user(message.from_user.id)

    if user[5] == 0:
        await message.answer("Налогов нет.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Оплатить налог",
                    callback_data="pay_tax"
                )
            ]
        ]
    )

    await message.answer(
        f"Текущий налог: {user[5]} чая\n"
        f"Срок оплаты: 24 часа",
        reply_markup=kb
    )





@dp.callback_query(F.data == "pay_tax")
async def pay_tax(callback: CallbackQuery):
    user = get_user(callback.from_user.id)

    tax_due = user[5]
    tea = user[1]

    if tax_due == 0:
        await callback.answer("Налогов нет.", show_alert=True)
        return

    if tea < tax_due:
        await callback.answer("Недостаточно чая.", show_alert=True)
        return

    # списываем чай
    update_user(callback.from_user.id, "tea", tea - tax_due)

    # обнуляем налог
    update_user(callback.from_user.id, "tax_due", 0)
    update_user(callback.from_user.id, "tax_level", 0)
    update_user(callback.from_user.id, "frozen", 0)
    update_user(callback.from_user.id, "warned", 0)

    await callback.message.edit_text("✅ Налог успешно оплачен.")


# ================= АВТО НАЛОГ =================

async def tax_system():
    while True:
        now = datetime.now()
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()

        for user in users:
            user_id = user[0]
            level = user[2]
            tax_timer = user[6]

            if level <= 0:
                continue

            if not tax_timer or datetime.fromisoformat(tax_timer) + timedelta(hours=24) <= now:

                # <-- ПОСТАВЬ СВОЮ ФОРМУЛУ НАЛОГА
                tax_amount = level * 100

                update_user(user_id, "tax_due", tax_amount)
                update_user(user_id, "tax_timer", now.isoformat())
                update_user(user_id, "warned", 0)

                try:
                    await bot.send_message(
                        user_id,
                        f"Вова Холокост выдал тебе налог в размере {tax_amount} чая."
                    )
                except:
                    pass

        await asyncio.sleep(3600)


# ================= ПРЕДУПРЕЖДЕНИЯ =================

async def tax_warning_system():
    while True:
        now = datetime.now()
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()

        for user in users:
            user_id = user[0]
            level = user[2]
            tax_level = user[4]
            tax_due = user[5]
            tax_timer = user[6]
            warned = user[8]

            if tax_due > 0 and tax_timer:
                deadline = datetime.fromisoformat(tax_timer) + timedelta(hours=24)

                if deadline - now <= timedelta(minutes=10) and not warned:
                    update_user(user_id, "warned", 1)
                    await bot.send_message(user_id, "⚠ Через 10 минут истекает срок оплаты налога!")

                if now >= deadline:
                    tax_level += 1
                    update_user(user_id, "tax_level", tax_level)

                    if tax_level == 1:
                        await bot.send_message(user_id, "⚠ Бонусы снижены до 0.5")

                    elif tax_level == 2:
                        update_user(user_id, "frozen", 1)
                        await bot.send_message(user_id, "❄ Бизнес заморожен.")

                    elif tax_level >= 3:
                        new_level = max(1, level - 1)
                        update_user(user_id, "business_level", new_level)
                        update_user(user_id, "tax_due", 0)
                        await bot.send_message(user_id, "📉 Уровень бизнеса снижен. Налоги больше не приходят.")

        await asyncio.sleep(60)

@dp.message(Command("evreygandon"))
async def evreygandon(message: Message):
    args = message.text.split()

    if len(args) != 2:
        await message.answer("Использование: /evreygandon число")
        return

    try:
        amount = int(args[1])
    except ValueError:
        await message.answer("Нужно указать число.")
        return

    if amount <= 0:
        await message.answer("Число должно быть больше 0.")
        return

    user = get_user(message.from_user.id)

    new_tea = user[1] + amount
    new_res = user[3] + amount

    update_user(message.from_user.id, "tea", new_tea)
    update_user(message.from_user.id, "resources", new_res)

    await message.answer(
        f"Выдано:\n"
        f"+{amount} чая\n"
        f"+{amount} ресурсов"
    )


# ================= DEV COMMANDS =================

@dp.message(Command("pizdilovka"))
async def dev1(message: Message):
    await message.answer("🚧 В разработке")

@dp.message(Command("shop"))
async def dev2(message: Message):
    await message.answer("🚧 В разработке")

@dp.message(Command("anal"))
async def dev3(message: Message):
    await message.answer("канал всевеликой чайханы :https://t.me/chaikhana48")


# ================= START =================

async def main():
    asyncio.create_task(tax_system())
    asyncio.create_task(tax_warning_system())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())