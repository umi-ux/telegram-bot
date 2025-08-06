import logging
import os
import json
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.executor import start_webhook

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Gspread setup
SCOPE = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds_dict = json.loads(os.getenv("GOOGLE_CREDS_JSON"))
CREDS = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
gc = gspread.authorize(CREDS)
sheet = gc.open('Near Miss Reports').worksheet('Reports')

# Bot and dispatcher
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Webhook config
WEBHOOK_PATH = '/webhook'
WEBAPP_HOST = '0.0.0.0'
WEBAPP_PORT = int(os.environ.get('PORT', 10000))

# States
class Form(StatesGroup):
    name = State()
    location = State()
    area = State()
    severity = State()
    description = State()
    photo = State()

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, ContentType, CallbackQuery

cancel_keyboard = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("/cancel"))
report_keyboard = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("/report"))

# Handlers
@dp.message_handler(commands='start')
async def start(message: types.Message):
    await message.answer("Hi! Use /report to file a near miss report.", reply_markup=report_keyboard)

@dp.message_handler(commands='report')
async def report(message: types.Message):
    await Form.name.set()
    await message.answer("What is your name?\n(You can cancel anytime with /cancel)", reply_markup=cancel_keyboard)

@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    keyboard = InlineKeyboardMarkup(row_width=2)
    for loc in ["Simpang Renggam", "U1 Office"]:
        keyboard.insert(InlineKeyboardButton(loc, callback_data=f"loc_{loc}"))
    await Form.location.set()
    await message.answer("Select the incident location:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("loc_"), state=Form.location)
async def process_location(callback: CallbackQuery, state: FSMContext):
    location = callback.data.split("_", 1)[1]
    await state.update_data(location=location)
    await callback.answer()
    area_options = {
        "Simpang Renggam": ["Guard House", "Factory", "Office"],
        "U1 Office": ["Office 1st Floor", "Office 2nd Floor", "Pantry"]
    }
    keyboard = InlineKeyboardMarkup(row_width=2)
    for area in area_options.get(location, ["General Area"]):
        keyboard.insert(InlineKeyboardButton(area, callback_data=f"area_{area}"))
    await Form.area.set()
    await bot.send_message(callback.from_user.id, "Select the area:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("area_"), state=Form.area)
async def process_area(callback: CallbackQuery, state: FSMContext):
    area = callback.data.split("_", 1)[1]
    await state.update_data(area=area)
    await callback.answer()
    keyboard = InlineKeyboardMarkup(row_width=3)
    for level in ["Low", "Medium", "High"]:
        keyboard.insert(InlineKeyboardButton(level, callback_data=f"sev_{level}"))
    await Form.severity.set()
    await bot.send_message(callback.from_user.id, "Select severity:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("sev_"), state=Form.severity)
async def process_severity(callback: CallbackQuery, state: FSMContext):
    severity = callback.data.split("_", 1)[1]
    await state.update_data(severity=severity)
    await callback.answer()
    await Form.description.set()
    await bot.send_message(callback.from_user.id, "Describe what happened:", reply_markup=cancel_keyboard)

@dp.message_handler(state=Form.description)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await Form.photo.set()
    await message.answer("Send a photo or type 'skip':", reply_markup=cancel_keyboard)

@dp.message_handler(lambda m: m.text.lower() == 'skip', state=Form.photo)
async def skip_photo(message: types.Message, state: FSMContext):
    await save_data(message, state, photo_url="")

@dp.message_handler(content_types=[ContentType.PHOTO, ContentType.VIDEO], state=Form.photo)
async def process_media(message: types.Message, state: FSMContext):
    file_id = message.photo[-1].file_id if message.photo else message.video.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    media_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    await save_data(message, state, media_url)

async def save_data(message: types.Message, state: FSMContext, photo_url):
    data = await state.get_data()
    sheet.append_row([
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        data.get('name'),
        data.get('location'),
        data.get('area'),
        data.get('severity'),
        data.get('description'),
        photo_url,
        message.from_user.id
    ])
    await message.answer("✅ Report saved. Tap /report to send another.", reply_markup=report_keyboard)
    await state.finish()

@dp.message_handler(commands='cancel', state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    if await state.get_state():
        await state.finish()
        await message.answer("❌ Report cancelled.", reply_markup=ReplyKeyboardRemove())

# Webhook startup/shutdown
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

# Main run
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )
