import asyncio
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv
import os
from aiohttp import web

load_dotenv()


WEBHOOK_HOST = os.getenv("WEBHOOK_HOST") 
WEBHOOK_PATH = '/webhook'
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

API_TOKEN = os.getenv("API_TOKEN")
CURATOR_ID = int(os.getenv("CURATOR_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")
TEST_LINK = os.getenv("TEST_LINK")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
scheduler = AsyncIOScheduler()

db_pool = None  # глобальное соединение с БД

# ---------------------- FSM Состояния ----------------------
class Form(StatesGroup):
    full_name = State()
    phone = State()
    choosing_day = State()
    choosing_time = State()
    
async def handle_request(request):
    Bot.set_current(bot)
    Dispatcher.set_current(dp)

    update = types.Update(**await request.json())
    await dp.process_update(update)
    return web.Response()

# ---------------------- Команды ----------------------

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    # Клавиатура с кнопками
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    register_button = KeyboardButton("/register")
    info_button = KeyboardButton("/info")
    
    # Добавляем кнопки на клавиатуру
    keyboard.add(register_button, info_button)
    await message.answer(
        "👋 Здравствуйте! Это бот для участия в исследовании.\n\n"
        "Чтобы узнать подробнее о тесте и оплате — введите команду <b>/info.</b>\n"
        "Если вы готовы пройти регистрацию: назначить время прохождения и получить ссылку — используйте <b>/register.</b>",
        parse_mode="HTML"
    )

@dp.message_handler(commands=['info'])
async def cmd_info(message: types.Message):
    await message.answer(
    "ℹ️ Это нейробиологическое исследование, направленное на изучение поведения в онлайн-среде.\n\n"
    "📋 Вам предстоит пройти онлайн-тест продолжительностью около <b>1 часа</b>. Тест нужно проходить на <b>ПК или ноутбуке</b> — на телефонах он не работает корректно. Нужно использовать <b>Windows и Chrome</b>\n\n"
    "🧠 В ходе теста будет использоваться <b>трекинг взгляда с помощью камеры</b> — в начале будет калибровка, чтобы всё работало корректно. Задания будут включать <b>поиск объектов, запоминание и другие простые когнитивные задачи</b>.\n\n"
    "❗Очень важно проходить тест <b>внимательно и без отвлечений</b>. Лучше выбрать <b>тихое место</b> и не слишком позднее время. Если вы отвлечётесь, тест может завершиться некорректно.\n\n"
    "😌 Не переживайте, если что-то не получилось или вы чувствовали себя «тупо» — это нормально! Мы <b>не оцениваем участников</b>, результаты <b>анонимны</b> и <b>не влияют на оплату</b>. Главное — пройти тест честно.\n\n"
    "⏰ Тест доступен с 09:00 до 20:00 ежедневно. При регистрации вы сможете выбрать удобное время. Это ориентировочный слот, но мы просим придерживаться выбранного времени.\n\n"
    "💰 После подтверждения прохождения теста вы получите вознаграждение <b>в размере 700 рублей</b> на указанный номер телефона.\n\n"
    "Чтобы принять участие, используйте команду <b>/register</b>.",
    parse_mode="HTML"
)


@dp.message_handler(commands=['register'])
async def cmd_start(message: types.Message):
    try:
        existing_user = await get_user_data(message.from_user.id)
        if existing_user:
            await message.answer("Вы уже зарегистрированы и записаны на тест.\n"
                                 f"Дата и время: {existing_user['schedule']}\n"
                                 "Если вы считаете, что это ошибка, свяжитесь с куратором.")
        else:
            await message.answer("Здравствуйте! Это бот для участия в исследовании.\nПожалуйста, введите ваше ФИО:")
            await Form.full_name.set()
    except Exception as e:
        # можно логировать ошибку, если нужно: print(f"Ошибка при проверке БД: {e}")
        await message.answer("Здравствуйте! Это бот для участия в исследовании.\nПожалуйста, введите ваше ФИО:")
        await Form.full_name.set()

@dp.message_handler(state=Form.full_name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    await message.answer("Введите номер телефона или номер карты и банк, куда бы вы хотели получить деньги:")
    await Form.phone.set()

@dp.message_handler(state=Form.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    markup = InlineKeyboardMarkup(row_width=2)
    today = datetime.now().date()
    now = datetime.now()
    if now.hour >= 20:
        today += timedelta(days=1)
    for i in range(7):
        day = today + timedelta(days=i)
        button = InlineKeyboardButton(day.strftime('%d.%m (%a)'), callback_data=f"day_{day.isoformat()}")
        markup.insert(button)
    await message.answer("Выберите удобный день прохождения теста:", reply_markup=markup)
    await Form.choosing_day.set()

@dp.callback_query_handler(lambda c: c.data.startswith("day_"), state=Form.choosing_day)
async def process_day(callback_query: types.CallbackQuery, state: FSMContext):
    day_str = callback_query.data[4:]
    await state.update_data(selected_day=day_str)
    markup = InlineKeyboardMarkup(row_width=4)
    
    selected_date = datetime.fromisoformat(day_str).date()
    now = datetime.now()
    
    for hour in range(9, 21):
        time_option = datetime.combine(selected_date, datetime.min.time()) + timedelta(hours=hour)
        if selected_date == now.date() and time_option <= now:
            continue  # Пропускаем уже прошедшие слоты
        
        time_str = f"{hour:02}:00"
        markup.insert(InlineKeyboardButton(time_str, callback_data=f"time_{time_str}"))
        
    if now.hour < 20 and selected_date == now.date():
        time_str = f"{now.hour:02}:{now.minute+1:02}"
        markup.add(InlineKeyboardButton("🚀 Сейчас", callback_data=f"time_{time_str}"))
    await bot.edit_message_text(chat_id=callback_query.message.chat.id,
                                message_id=callback_query.message.message_id,
                                text=f"Вы выбрали {datetime.fromisoformat(day_str).strftime('%d.%m (%A)')}\nТеперь выберите время:",
                                reply_markup=markup)
    await Form.choosing_time.set()

@dp.callback_query_handler(lambda c: c.data.startswith("time_"), state=Form.choosing_time)
async def process_time(callback_query: types.CallbackQuery, state: FSMContext):
    time_part = callback_query.data[5:]
    user_data = await state.get_data()
    day_str = user_data.get("selected_day")
    full_name = user_data.get("full_name")
    phone = user_data.get("phone")

    full_datetime = datetime.fromisoformat(day_str + "T" + time_part)

    await save_user_data(callback_query.from_user.id, full_name, phone, full_datetime.strftime('%Y-%m-%d %H:%M'))

    await bot.edit_message_text(chat_id=callback_query.message.chat.id,
                                message_id=callback_query.message.message_id,
                                text=f"✅ Вы записаны на {full_datetime.strftime('%d.%m %H:%M')}\nСсылка на тест будет отправлена в назначенное время.")
    
    scheduler.add_job(send_test_link, 'date', run_date=full_datetime, args=[callback_query.from_user.id])
    
    '''test'''
    #test_run_time = datetime.now() + timedelta(seconds=10)
    #scheduler.add_job(send_test_link, 'date', run_date=test_run_time, args=[callback_query.from_user.id])
    await state.finish()

# ---------------------- Отправка ссылки на тест ----------------------
async def send_test_link(user_id):
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("✅ Тест пройден", callback_data="test_done"))
    await bot.send_message(user_id, f"Вот ваша ссылка на тест: {TEST_LINK}. После теста сделайте скриншот финальной страницы, я попрошу отправить его в чат!\n\n Проходите тест в <b>Windows, в Chrome браузере.</b> Нужна <b>камера.</b>", parse_mode="HTML", reply_markup=markup)

# ---------------------- Обработка кнопки ----------------------
@dp.callback_query_handler(lambda c: c.data == 'test_done')
async def test_done_handler(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(callback_query.from_user.id, "Пожалуйста, отправьте скриншот прохождения теста.")

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_screenshot(message: types.Message):
    user_id = message.from_user.id
    photo_id = message.photo[-1].file_id
    user_data = await get_user_data(user_id)
    if user_data:
        caption = (
            f"✅ Тест пройден\nФИО: {user_data['full_name']}\n"
            f"Телефон: {user_data['phone']}\n"
            f"Время теста: {user_data['schedule']}"
        )
        await bot.send_photo(CURATOR_ID, photo=photo_id, caption=caption)
        await message.answer("Спасибо! Ваши данные отправлены куратору.")

# ---------------------- Работа с PostgreSQL ----------------------
async def save_user_data(tg_id, full_name, phone, schedule):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                tg_id BIGINT PRIMARY KEY,
                full_name TEXT,
                phone TEXT,
                schedule TEXT
            )
        """)
        await conn.execute("""
            INSERT INTO users (tg_id, full_name, phone, schedule)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (tg_id) DO UPDATE
            SET full_name = EXCLUDED.full_name,
                phone = EXCLUDED.phone,
                schedule = EXCLUDED.schedule
        """, tg_id, full_name, phone, schedule)

async def get_user_data(tg_id):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT full_name, phone, schedule FROM users WHERE tg_id = $1", tg_id)
        if row:
            return {'full_name': row['full_name'], 'phone': row['phone'], 'schedule': row['schedule']}
        return None

# ---------------------- Запуск бота via webhook----------------------

async def on_startup(app):
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, ssl='require')
    scheduler.start()
    await bot.set_webhook(WEBHOOK_URL)
    Bot.set_current(bot)

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()


# aiohttp-приложение
app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle_request)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == '__main__':
    web.run_app(app, port=8000)
