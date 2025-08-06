import logging
import os
import json
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, ContentType, CallbackQuery
from aiohttp import web
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv
from datetime import datetime, timedelta

# === LOAD ENV ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_URL")  # without /webhook
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

APP_HOST = "0.0.0.0"
APP_PORT = int(os.getenv("PORT", 8080))

# === GOOGLE SHEETS ===
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
CREDS = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(os.getenv("GOOGLE_CREDS_JSON")), SCOPE)
gc = gspread.authorize(CREDS)
sheet = gc.open('Near Miss Reports').worksheet('Reports')

# === BOT SETUP ===
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# === FSM STATES ===
class Form(StatesGroup):
    name = State()
    location = State()
    area = State()
    severity = State()
    description = State()
    photo = State()

# === KEYBOARDS ===
cancel_keyboard = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("/cancel"))
report_keyboard = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("/report"))

# === HANDLERS ===
# === Start ===
@dp.message_handler(commands='start')
async def start(message: types.Message, state: FSMContext):
    await state.finish()  # Cancel any ongoing form/report
    await message.answer("Hi! Use /report to file a near miss report.\n\nHi! Tekan /report untuk membuat laporan.", reply_markup=report_keyboard)

# === CANCEL HANDLER ===
@dp.message_handler(commands='cancel', state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if current:
        await state.finish()
        await message.answer(
            "❌ Report cancelled. Hit /report to start again.\n\n❌ Laporan dibatalkan. Tekan /report untuk mulakan laporan.",
            reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("⚠️ No active report to cancel.",
                             reply_markup=ReplyKeyboardRemove())

# === Report Start ===
@dp.message_handler(commands='report')
async def report(message: types.Message):
    await dp.current_state(user=message.from_user.id).set_state(Form.name.state)
    await message.answer("What is your name?\n(You can cancel anytime with /cancel)\n\nNama anda?\n(Anda boleh batalkan bila-bila masa dengan /cancel)", reply_markup=cancel_keyboard)

# === Name ===
@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    keyboard = InlineKeyboardMarkup(row_width=2)
    for loc in ["Simpang Renggam", "U1 Office"]:
        keyboard.insert(InlineKeyboardButton(loc, callback_data=f"loc_{loc}"))
    await dp.current_state(user=message.from_user.id).set_state(Form.location.state)
    await message.answer("Select the incident location:\n\nPilih lokasi insiden:", reply_markup=keyboard)

# === Location ===
@dp.callback_query_handler(lambda c: c.data.startswith("loc_"), state=Form.location)
async def process_location(callback: CallbackQuery, state: FSMContext):
    location = callback.data.split("_", 1)[1]
    await state.update_data(location=location)
    await callback.answer()
    area_options = {
        "Simpang Renggam": ["Guard House", "Factory Surrounding", "Car/Motorcycle Parking", "Office", "Toilet", "Prayer Room", "Canteen", "Warehouse (Material)", "Warehouse (Component)", "Cutting Section", "Blasting Section", "Deck Assembly", "Lip Assembly", "Frame Assembly", "Crane Fabrication", "Painting Section", "DL Assembly", "Laser Cleaning", "Loading Bay"],
        "U1 Office": ["Guard House", "Building Surrounding", "Car/Motorcycle Parking", "Office 1st Floor", "Office 2nd Floor", "Toilet", "Prayer Room", "Pantry", "Warehouse (MHE)", "Warehouse (T&I)", "Training Room", "Ground Floor Office", "Stairs", "Meeting Room", "Discussion Room", "Privacy Room", "L2 Lobby"]
    }
    keyboard = InlineKeyboardMarkup(row_width=2)
    for area in area_options.get(location, ["General Area"]):
        keyboard.insert(InlineKeyboardButton(area, callback_data=f"area_{area}"))
    await dp.current_state(user=callback.from_user.id).set_state(Form.area.state)
    await bot.send_message(callback.from_user.id, "Select the area:\n\nPilih kawasan kejadian:", reply_markup=keyboard)

# === Area ===
@dp.callback_query_handler(lambda c: c.data.startswith("area_"), state=Form.area)
async def process_area(callback: CallbackQuery, state: FSMContext):
    area = callback.data.split("_", 1)[1]
    await state.update_data(area=area)
    await callback.answer()
    keyboard = InlineKeyboardMarkup(row_width=3)
    for level in ["Low", "Medium", "High"]:
        keyboard.insert(InlineKeyboardButton(level, callback_data=f"sev_{level}"))
    await dp.current_state(user=callback.from_user.id).set_state(Form.severity.state)
    await bot.send_message(callback.from_user.id, "Select severity level:\n\nPilih tahap keseriusan:", reply_markup=keyboard)

# === Severity ===
@dp.callback_query_handler(lambda c: c.data.startswith("sev_"), state=Form.severity)
async def process_severity(callback: CallbackQuery, state: FSMContext):
    severity = callback.data.split("_", 1)[1]
    await state.update_data(severity=severity)
    await callback.answer()
    await dp.current_state(user=callback.from_user.id).set_state(Form.description.state)
    await bot.send_message(callback.from_user.id, "Describe what happened:\n\nTerangkan apa yang berlaku:", reply_markup=cancel_keyboard)

# === Description  ===
@dp.message_handler(state=Form.description)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await dp.current_state(user=message.from_user.id).set_state(Form.photo.state)
    await message.answer("Send a photo or short video (or type 'skip'):\n\nHantar gambar atau video pendek (atau taip 'skip'):", reply_markup=cancel_keyboard)

# === Skip Photo  ===
@dp.message_handler(lambda m: m.text.lower() == 'skip', state=Form.photo)
async def skip_photo(message: types.Message, state: FSMContext):
    await save_data(message, state, photo_url="")

# === Photo or Video  ===
@dp.message_handler(content_types=[ContentType.PHOTO, ContentType.VIDEO], state=Form.photo)
async def process_media(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    media_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    await save_data(message, state, media_url)

# === SAVE DATA TO GOOGLE SHEETS ===
async def save_data(message: types.Message, state: FSMContext, photo_url):
    data = await state.get_data()
    sheet.append_row([
        (datetime.utcnow() + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S'),
        data.get('name'),
        data.get('location'),
        data.get('area'),
        data.get('severity'),
        data.get('description'),
        photo_url,
        message.from_user.id
    ])
    await message.answer("✅ Report saved. Tap /report to send another.\n\n✅Laporan disimpan. Tekan /report untuk menghantar lagi.", reply_markup=report_keyboard)
    await state.finish()

# === AIOHTTP WEBHOOK ===
async def handle_webhook(request):
    data = await request.json()
    update = types.Update.to_object(data)

    # Fix: Set current bot and dispatcher context manually
    bot.set_current(bot)
    dp.set_current(dp)

    await dp.process_update(update)
    return web.Response()

async def on_startup_app(app):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info("🚀 Webhook set and bot started")

async def on_cleanup_app(app):
    await bot.delete_webhook()
    logging.info("🧹 Webhook deleted on shutdown")

def main():
    logging.basicConfig(level=logging.INFO)

    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.on_startup.append(on_startup_app)
    app.on_cleanup.append(on_cleanup_app)

    logging.info(f"🌐 Starting app on {APP_HOST}:{APP_PORT}")
    web.run_app(app, host=APP_HOST, port=APP_PORT)

if __name__ == '__main__':
    main()
