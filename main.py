import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ContentType, CallbackQuery
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# === CONFIGURATION ===
API_TOKEN = '8433221482:AAExhTkTldSA99kE4Cu9tZJADoSGMEHBgEw'  # ← Replace with your real bot token

SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
CREDS = ServiceAccountCredentials.from_json_keyfile_name('creds.json', SCOPE)
gc = gspread.authorize(CREDS)
sheet = gc.open('Near Miss Reports').worksheet('Reports')

# === BOT SETUP ===
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())


# === STATE MACHINE ===
class Form(StatesGroup):
    name = State()
    location = State()
    area = State()
    severity = State()
    description = State()
    photo = State()


# === KEYBOARDS ===
cancel_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
cancel_keyboard.add(KeyboardButton("/cancel"))

report_keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
report_keyboard.add(KeyboardButton("/report"))


# === CANCEL HANDLER ===
@dp.message_handler(commands='cancel', state='*')
async def cancel_handler(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if current:
        await state.finish()
        await message.answer(
            "❌ Report cancelled. You can start again anytime with /report.",
            reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("⚠️ No active report to cancel.",
                             reply_markup=ReplyKeyboardRemove())


# === START ===
@dp.message_handler(commands='start')
async def start(message: types.Message):
    await message.answer("Hi! Use /report to file a near miss report.",
                         reply_markup=report_keyboard)


# === REPORT START ===
@dp.message_handler(commands='report')
async def report(message: types.Message):
    await Form.name.set()
    await message.answer(
        "What is your name?\n(You can cancel anytime with /cancel)\n\nNama anda?\n(Anda boleh batalkan bila-bila masa dengan /cancel)",
        reply_markup=cancel_keyboard)


# === NAME ===
@dp.message_handler(state=Form.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)

    keyboard = InlineKeyboardMarkup(row_width=2)
    for loc in ["Simpang Renggam", "U1 Office"]:
        keyboard.insert(InlineKeyboardButton(loc, callback_data=f"loc_{loc}"))
    await Form.location.set()
    await message.answer(
        "Select the incident location:\n\nPilih lokasi insiden:",
        reply_markup=keyboard)


# === LOCATION ===
@dp.callback_query_handler(lambda c: c.data.startswith("loc_"),
                           state=Form.location)
async def process_location(callback: CallbackQuery, state: FSMContext):
    location = callback.data.split("_", 1)[1]
    await state.update_data(location=location)
    await callback.answer()

    area_options = {
        "Simpang Renggam": [
            "Guard House", "Factory Surrounding", "Car/Motorcycle Parking",
            "Office", "Toilet", "Prayer Room", "Canteen",
            "Warehouse (Material)", "Warehouse (Component)", "Cutting Section",
            "Blasting Section", "Deck Assembly", "Lip Assembly",
            "Frame Assembly", "Crane Fabrication", "Painting Section",
            "DL Assembly", "Laser Cleaning", "Loading Bay"
        ],
        "U1 Office": [
            "Guard House", "Building Surrounding", "Car/Motorcycle Parking",
            "Office 1st Floor", "Office 2nd Floor", "Toilet", "Prayer Room",
            "Pantry", "Warehouse (MHE)", "Warehouse (T&I)", "Training Room",
            "Ground Floor Office", "Stairs", "Meeting Room", "Discussion Room",
            "Privacy Room", "L2 Lobby"
        ]
    }
    areas = area_options.get(location, ["General Area"])

    keyboard = InlineKeyboardMarkup(row_width=2)
    for area in areas:
        keyboard.insert(
            InlineKeyboardButton(area, callback_data=f"area_{area}"))

    await Form.area.set()
    await bot.send_message(
        callback.from_user.id,
        f"Which area in the {location}?\n\nDi kawasan manakah di {location}?",
        reply_markup=keyboard)


# === AREA ===
@dp.callback_query_handler(lambda c: c.data.startswith("area_"),
                           state=Form.area)
async def process_area(callback: CallbackQuery, state: FSMContext):
    area = callback.data.split("_", 1)[1]
    await state.update_data(area=area)
    await callback.answer()

    keyboard = InlineKeyboardMarkup(row_width=3)
    for level in ["Low", "Medium", "High"]:
        keyboard.insert(
            InlineKeyboardButton(level, callback_data=f"sev_{level}"))

    await Form.severity.set()
    await bot.send_message(callback.from_user.id,
                           "Select severity level:\n\nPilih tahap keseriusan:",
                           reply_markup=keyboard)


# === SEVERITY ===
@dp.callback_query_handler(lambda c: c.data.startswith("sev_"),
                           state=Form.severity)
async def process_severity(callback: CallbackQuery, state: FSMContext):
    severity = callback.data.split("_", 1)[1]
    await state.update_data(severity=severity)
    await callback.answer()

    await Form.description.set()
    await bot.send_message(
        callback.from_user.id,
        "Describe what happened:\n\nTerangkan apa yang berlaku:",
        reply_markup=cancel_keyboard)


# === DESCRIPTION ===
@dp.message_handler(state=Form.description)
async def process_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text)
    await Form.photo.set()
    await message.answer(
        "You may now send a photo or short video (or type 'skip'):\n\nAnda boleh menghantar gambar atau video pendek (atau taip 'skip')",
        reply_markup=cancel_keyboard)


# === SKIP PHOTO ===
@dp.message_handler(lambda m: m.text.lower() == 'skip', state=Form.photo)
async def skip_photo(message: types.Message, state: FSMContext):
    await save_data(message, state, photo_url="")


# === PHOTO OR VIDEO ===
@dp.message_handler(content_types=[ContentType.PHOTO, ContentType.VIDEO],
                    state=Form.photo)
async def process_media(message: types.Message, state: FSMContext):
    file_id = message.photo[
        -1].file_id if message.photo else message.video.file_id
    file = await bot.get_file(file_id)
    file_path = file.file_path
    media_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_path}"
    await save_data(message, state, media_url)


# === SAVE DATA TO GOOGLE SHEETS ===
async def save_data(message: types.Message, state: FSMContext, photo_url):
    data = await state.get_data()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    sheet.append_row([
        timestamp,
        data.get('name'),
        data.get('location'),
        data.get('area'),
        data.get('severity'),
        data.get('description'), photo_url, message.from_user.id
    ])

    await message.answer(
        "✅ Report saved. Tap /report to send another.\n\n✅ Laporan disimpan. Tekan /report untuk menghantar lagi.",
        reply_markup=report_keyboard)
    await state.finish()


# === FALLBACK FOR RANDOM TEXT DURING CALLBACKS ===
@dp.message_handler(state='*', content_types=types.ContentTypes.TEXT)
async def unknown_text(message: types.Message, state: FSMContext):
    await message.reply("⚠️ Please use the buttons or type /cancel to stop.",
                        reply_markup=cancel_keyboard)


# === START POLLING ===
def start_bot():
    executor.start_polling(dp, skip_updates=True)
