import asyncio
import logging
import os
from dataclasses import dataclass

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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


@dataclass
class Order:
    order_id: int
    buyer_id: int
    buyer_username: str
    target: str
    amount: int
    status: str = "new"
    admin_message_id: int | None = None


orders: dict[int, Order] = {}
order_counter: int = 0


def next_order_id() -> int:
    global order_counter
    order_counter += 1
    return order_counter


class BuyStars(StatesGroup):
    choosing_target = State()
    entering_username = State()
    entering_amount = State()


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⭐ Купить звёзды", callback_data="buy")]]
    )


def target_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Для себя", callback_data="target_self")],
            [InlineKeyboardButton(text="По юзернейму", callback_data="target_username")],
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


@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Ты попал в <b>Banan Stars Bot</b> ⭐\n\n"
        "Здесь можно купить звёзды Telegram себе или другому пользователю.\n"
        f"Минимальная сумма покупки — {MIN_STARS} звёзд.",
        reply_markup=start_keyboard(),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "buy")
async def buy_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyStars.choosing_target)
    await callback.message.edit_text("Кому начисляем звёзды?", reply_markup=target_keyboard())
    await callback.answer()


@dp.callback_query(BuyStars.choosing_target, F.data == "target_self")
async def target_self(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(target="себе")
    await state.set_state(BuyStars.entering_amount)
    await callback.message.edit_text(f"Введи количество звёзд (минимум {MIN_STARS}):")
    await callback.answer()


@dp.callback_query(BuyStars.choosing_target, F.data == "target_username")
async def target_username(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BuyStars.entering_username)
    await callback.message.edit_text("Введи юзернейм получателя (например, @username):")
    await callback.answer()


@dp.message(BuyStars.entering_username)
async def username_entered(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if not username.startswith("@") or len(username) < 3:
        await message.answer("Похоже на неверный юзернейм. Введи в формате @username:")
        return
    await state.update_data(target=username)
    await state.set_state(BuyStars.entering_amount)
    await message.answer(f"Введи количество звёзд (минимум {MIN_STARS}):")


@dp.message(BuyStars.entering_amount)
async def amount_entered(message: types.Message, state: FSMContext):
    text = message.text.strip()

    if not text.isdigit():
        await message.answer("Нужно ввести число. Попробуй ещё раз:")
        return

    amount = int(text)
    if amount < MIN_STARS:
        await message.answer(f"Минимальная сумма — {MIN_STARS} звёзд. Введи число не меньше {MIN_STARS}:")
        return

    data = await state.get_data()
    target = data.get("target", "себе")

    order_id = next_order_id()
    order = Order(
        order_id=order_id,
        buyer_id=message.from_user.id,
        buyer_username=f"@{message.from_user.username}" if message.from_user.username else "(без юзернейма)",
        target=target,
        amount=amount,
    )
    orders[order_id] = order

    await state.clear()

    await message.answer(
        f"Заказ №{order_id} принят ✅\n"
        f"Получатель: {target}\n"
        f"Количество звёзд: {amount}\n\n"
        "Ожидай, администратор скоро свяжется с тобой."
    )

    sent = await bot.send_message(
        ADMIN_ID,
        f"🆕 Новый заказ №{order_id}\n"
        f"От: {order.buyer_username} (id: {order.buyer_id})\n"
        f"Получатель: {target}\n"
        f"Количество звёзд: {amount}\n\n"
        f"Чтобы написать клиенту — просто ответь (Reply) на это сообщение.",
        reply_markup=admin_order_keyboard(order_id),
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
    await bot.send_message(order.buyer_id, f"Администратор начал выполнение вашего заказа №{order_id} 🚀")
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
    await bot.send_message(order.buyer_id, f"По заказу №{order_id}: администратор сейчас занят, ожидайте.")
    await callback.answer("Пользователь уведомлён")


# Ответ клиенту через Reply на уведомление о заказе
@dp.message(F.reply_to_message, F.from_user.id == ADMIN_ID)
async def admin_reply_to_client(message: types.Message):
    replied_id = message.reply_to_message.message_id
    target_order = None
    for order in orders.values():
        if order.admin_message_id == replied_id:
            target_order = order
            break

    if not target_order:
        return  # это не ответ на заказ — игнорируем

    await bot.send_message(target_order.buyer_id, message.text)
    await message.answer(f"Сообщение отправлено клиенту (заказ №{target_order.order_id}) ✅")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())