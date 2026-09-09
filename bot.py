import asyncio
import logging
import os
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MIN_STARS = 50

if not BOT_TOKEN:
    raise RuntimeError("Не найден BOT_TOKEN — заполни файл .env")
if not ADMIN_ID:
    raise RuntimeError("Не найден ADMIN_ID — заполни файл .env")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

DIVIDER = "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"


@dataclass
class Order:
    order_id: int
    buyer_id: int
    buyer_username: str
    target: str
    amount: int
    comment: str = "—"
    status: str = "new"
    admin_message_id: int | None = None


orders: dict[int, Order] = {}
order_counter: int = 0

# для кнопки "Связь с админом": admin_message_id -> id пользователя
contact_messages: dict[int, int] = {}


def next_order_id() -> int:
    global order_counter
    order_counter += 1
    return order_counter


class BuyStars(StatesGroup):
    choosing_target = State()
    entering_username = State()
    entering_amount = State()
    entering_contact = State()
    entering_comment = State()


class ContactAdmin(StatesGroup):
    writing_message = State()


# ---------------------------------------------------------
# КЛАВИАТУРЫ
# ---------------------------------------------------------

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Купить звёзды", callback_data="buy")],
            [InlineKeyboardButton(text="💬 Связь с админом", callback_data="contact_admin")],
        ]
    )


def target_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 Для себя", callback_data="target_self")],
            [InlineKeyboardButton(text="🔗 По юзернейму", callback_data="target_username")],
        ]
    )


def admin_order_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Могу сейчас", callback_data=f"able_{order_id}"),
                InlineKeyboardButton(text="⏳ Не могу сейчас", callback_data=f"busy_{order_id}"),
            ]
        ]
    )


# ---------------------------------------------------------
# КОМАНДЫ МЕНЮ (видны в синей кнопке "Меню" у поля ввода)
# ---------------------------------------------------------

async def setup_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="🏠 Главное меню"),
        BotCommand(command="menu", description="📋 Открыть меню заново"),
        BotCommand(command="info", description="ℹ️ О боте"),
    ])


# ---------------------------------------------------------
# СТАРТ / МЕНЮ
# ---------------------------------------------------------

async def send_main_menu(message: types.Message):
    await message.answer(
        "✨ <b>BANAN STARS BOT</b> ✨\n"
        f"{DIVIDER}\n\n"
        "Привет! 👋 Здесь можно быстро купить "
        "<b>звёзды Telegram</b> — себе или в подарок другу.\n\n"
        f"⭐ Минимальная сумма: <b>{MIN_STARS} звёзд</b>\n"
        "⚡ Быстрая обработка заявки\n"
        "🔒 Прямая связь с администратором\n\n"
        "Выбери действие 👇",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await send_main_menu(message)


@dp.message(Command("menu"))
async def cmd_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await send_main_menu(message)


@dp.message(Command("info"))
async def cmd_info(message: types.Message):
    await message.answer(
        "ℹ️ <b>О боте</b>\n"
        f"{DIVIDER}\n\n"
        "🤖 <b>Banan Stars Bot</b> — бот для покупки звёзд Telegram.\n\n"
        "🛠 Написан с помощью <b>Claude</b> (Anthropic) — ИИ-ассистента для разработки.\n"
        "📦 Код размещён и развёрнут через <b>GitHub</b>.\n"
        "🔓 Бот <b>open source</b> — исходный код открыт.\n\n"
        f"{DIVIDER}\n"
        "Используй /menu, чтобы вернуться в главное меню.",
        parse_mode="HTML",
    )


# ---------------------------------------------------------
# ПОКУПКА ЗВЁЗД
# ---------------------------------------------------------

@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyStars.choosing_target)
    await callback.message.edit_text(
        "🎯 <b>Кому начисляем звёзды?</b>",
        reply_markup=target_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(BuyStars.choosing_target, F.data == "target_self")
async def target_self(callback: types.CallbackQuery, state: FSMContext):
    user = callback.from_user
    target_display = f"себе (@{user.username})" if user.username else "себе"
    await state.update_data(target=target_display)
    await state.set_state(BuyStars.entering_amount)
    await callback.message.edit_text(
        f"⭐ <b>Введи количество звёзд</b>\nМинимум — {MIN_STARS}:",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(BuyStars.choosing_target, F.data == "target_username")
async def target_username(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyStars.entering_username)
    await callback.message.edit_text(
        "🔗 <b>Введи юзернейм получателя</b>\nНапример: <code>@username</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(BuyStars.entering_username)
async def username_entered(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if not username.startswith("@") or len(username) < 3:
        await message.answer("⚠️ Похоже на неверный юзернейм. Введи в формате @username:")
        return
    await state.update_data(target=username)
    await state.set_state(BuyStars.entering_amount)
    await message.answer(
        f"⭐ <b>Введи количество звёзд</b>\nМинимум — {MIN_STARS}:",
        parse_mode="HTML",
    )


@dp.message(BuyStars.entering_amount)
async def amount_entered(message: types.Message, state: FSMContext):
    text = message.text.strip()

    if not text.isdigit():
        await message.answer("⚠️ Нужно ввести число. Попробуй ещё раз:")
        return

    amount = int(text)
    if amount < MIN_STARS:
        await message.answer(f"⚠️ Минимальная сумма — {MIN_STARS} звёзд. Введи число не меньше {MIN_STARS}:")
        return

    await state.update_data(amount=amount)

    if message.from_user.username:
        await state.update_data(contact=f"@{message.from_user.username}")
        await ask_comment(message, state)
    else:
        await state.set_state(BuyStars.entering_contact)
        await message.answer(
            "🔒 <b>У тебя скрыт юзернейм</b>\n\n"
            "Администратор не сможет найти тебя напрямую. Напиши, как с тобой связаться — "
            "юзернейм, номер телефона или контакт в другом мессенджере:",
            parse_mode="HTML",
        )


@dp.message(BuyStars.entering_contact)
async def contact_entered(message: types.Message, state: FSMContext):
    contact = message.text.strip()
    if not contact:
        await message.answer("Напиши, пожалуйста, как с тобой связаться:")
        return
    await state.update_data(contact=contact)
    await ask_comment(message, state)


async def ask_comment(message: types.Message, state: FSMContext):
    await state.set_state(BuyStars.entering_comment)
    await message.answer(
        "💬 <b>Хочешь добавить комментарий к заказу?</b>\n"
        "Например, пожелание или уточнение.\n\n"
        "Напиши текст, либо отправь «-», если комментарий не нужен:",
        parse_mode="HTML",
    )


@dp.message(BuyStars.entering_comment)
async def comment_entered(message: types.Message, state: FSMContext):
    comment_text = message.text.strip()
    comment = "—" if comment_text == "-" else comment_text
    await finalize_order(message, state, comment=comment)


async def finalize_order(message: types.Message, state: FSMContext, comment: str):
    data = await state.get_data()
    target = data.get("target", "себе")
    amount = data.get("amount")
    contact = data.get("contact", "неизвестно")

    order_id = next_order_id()
    order = Order(
        order_id=order_id,
        buyer_id=message.from_user.id,
        buyer_username=contact,
        target=target,
        amount=amount,
        comment=comment,
    )
    orders[order_id] = order

    await state.clear()

    await message.answer(
        "✅ <b>Заказ оформлен!</b>\n"
        f"{DIVIDER}\n"
        f"🧾 Номер заказа: <b>#{order_id}</b>\n"
        f"🎯 Получатель: <b>{target}</b>\n"
        f"⭐ Количество: <b>{amount}</b>\n"
        f"💬 Комментарий: <b>{comment}</b>\n"
        f"{DIVIDER}\n\n"
        "⏳ Ожидай, администратор скоро свяжется с тобой.",
        parse_mode="HTML",
    )

    sent = await bot.send_message(
        ADMIN_ID,
        "🆕 <b>НОВЫЙ ЗАКАЗ</b>\n"
        f"{DIVIDER}\n"
        f"🧾 Номер: <b>#{order_id}</b>\n"
        f"👤 Покупатель: <b>{contact}</b> (id: <code>{order.buyer_id}</code>)\n"
        f"🎯 Получатель: <b>{target}</b>\n"
        f"⭐ Количество: <b>{amount}</b>\n"
        f"💬 Комментарий: <b>{comment}</b>\n"
        f"{DIVIDER}\n\n"
        "Чтобы написать клиенту — ответь (Reply) на это сообщение.",
        reply_markup=admin_order_keyboard(order_id),
        parse_mode="HTML",
    )
    order.admin_message_id = sent.message_id


@dp.callback_query(F.data.startswith("able_"))
async def admin_able(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Недоступно.", show_alert=True)
        return

    order_id = int(callback.data.split("_", 1)[1])
    order = orders.get(order_id)
    if not order:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    order.status = "in_progress"
    await bot.send_message(
        order.buyer_id,
        f"🚀 <b>Администратор начал выполнение вашего заказа #{order_id}</b>",
        parse_mode="HTML",
    )
    await callback.message.edit_text(callback.message.text + "\n\n✅ Взято в работу")
    await callback.answer("Пользователь уведомлён")


@dp.callback_query(F.data.startswith("busy_"))
async def admin_busy(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Недоступно.", show_alert=True)
        return

    order_id = int(callback.data.split("_", 1)[1])
    order = orders.get(order_id)
    if not order:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    order.status = "busy"
    await bot.send_message(
        order.buyer_id,
        f"⏳ По заказу <b>#{order_id}</b>: администратор сейчас занят, ожидайте.",
        parse_mode="HTML",
    )
    await callback.answer("Пользователь уведомлён")


# ---------------------------------------------------------
# СВЯЗЬ С АДМИНОМ (вне заказа)
# ---------------------------------------------------------

@dp.callback_query(F.data == "contact_admin")
async def contact_admin_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ContactAdmin.writing_message)
    await callback.message.edit_text(
        "💬 <b>Напиши своё сообщение администратору</b>\n"
        "Оно будет переслано напрямую:",
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(ContactAdmin.writing_message)
async def contact_admin_send(message: types.Message, state: FSMContext):
    await state.clear()

    user = message.from_user
    handle = f"@{user.username}" if user.username else "(без юзернейма)"

    sent = await bot.send_message(
        ADMIN_ID,
        "💬 <b>Сообщение от пользователя</b>\n"
        f"{DIVIDER}\n"
        f"👤 {handle} (id: <code>{user.id}</code>)\n"
        f"{DIVIDER}\n\n"
        f"{message.text}\n\n"
        "Чтобы ответить — используй Reply на это сообщение.",
        parse_mode="HTML",
    )
    contact_messages[sent.message_id] = user.id

    await message.answer("✅ Сообщение отправлено администратору, ожидай ответа.")


# ---------------------------------------------------------
# ОТВЕТ АДМИНА ЧЕРЕЗ REPLY (работает и для заказов, и для связи)
# ---------------------------------------------------------

@dp.message(F.reply_to_message, F.from_user.id == ADMIN_ID)
async def admin_reply(message: types.Message):
    replied_id = message.reply_to_message.message_id

    # проверяем — это ответ на заказ?
    for order in orders.values():
        if order.admin_message_id == replied_id:
            await bot.send_message(order.buyer_id, message.text)
            await message.answer(f"✅ Сообщение отправлено клиенту (заказ #{order.order_id})")
            return

    # или ответ на сообщение из "Связь с админом"?
    if replied_id in contact_messages:
        user_id = contact_messages[replied_id]
        await bot.send_message(user_id, message.text)
        await message.answer("✅ Сообщение отправлено пользователю")
        return


# ---------------------------------------------------------
# ЗАПУСК
# ---------------------------------------------------------

async def main():
    await setup_commands()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())