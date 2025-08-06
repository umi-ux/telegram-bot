from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, executor, types
import asyncio
import os

TOKEN = os.getenv("BOT_TOKEN")  # Set in Render later

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    await message.reply("Hello from Render bot!")

def start_bot():
    loop = asyncio.get_event_loop()
    loop.create_task(dp.start_polling())

if __name__ == '__main__':
    keep_alive()
    print("✅ Bot is running...")
    start_bot()
