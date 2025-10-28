import os
import requests
import telebot
from datetime import datetime
import subprocess


API_TOKEN = os.environ.get('API_TOKEN')  8332384363:AAF5oAOn78qR3HR0QDn3etfvTXaKhkCbPUE
RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY')  98ec9e7c0fmshaf3582322b40dbdp19de07jsn74e80255556c

bot = telebot.TeleBot(API_TOKEN)

HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'X-RapidAPI-Key': RAPIDAPI_KEY,
    'X-RapidAPI-Host': 'tiktok-video-downloader2.p.rapidapi.com'
}

user_mode = {}
LOG_FILE = 'downloads.log'

# ---------------- Helpers ----------------
def log_event(user_id, action, url, status, note=''):
    t = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{t}\t{user_id}\t{action}\t{url}\t{status}\t{note}\n")

def extract_audio_from_mp4(mp4_bytes):
    try:
        inp = '/tmp/input_video.mp4'
        out = '/tmp/output_audio.mp3'
        with open(inp, 'wb') as f:
            f.write(mp4_bytes)
        cmd = ['ffmpeg', '-y', '-i', inp, '-vn', '-acodec', 'libmp3lame', '-q:a', '4', out]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(out, 'rb') as f:
            data = f.read()
        try:
            os.remove(inp)
            os.remove(out)
        except:
            pass
        return data
    except:
        return None

# ---------------- Bot Handlers ----------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.InlineKeyboardMarkup()
    btn1 = telebot.types.InlineKeyboardButton("🎥 Скачать видео", callback_data="download_video")
    btn2 = telebot.types.InlineKeyboardButton("🎵 Скачать аудио", callback_data="download_audio")
    markup.add(btn1, btn2)
    bot.send_message(message.chat.id, "Выбери действие:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == "download_video":
        user_mode[call.message.chat.id] = 'video'
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Отправь ссылку на TikTok видео.")
    elif call.data == "download_audio":
        user_mode[call.message.chat.id] = 'audio'
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Отправь ссылку, и я пришлю только аудио (mp3).")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    chat_id = message.chat.id
    text = (message.text or '').strip()

    if chat_id not in user_mode:
        bot.send_message(chat_id, "Сначала нажми /start и выбери действие.")
        return

    mode = user_mode.get(chat_id)
    url = text
    bot.send_message(chat_id, "Обрабатываю ссылку, это может занять несколько секунд...")

    try:
        r = requests.get(f"https://tiktok-video-downloader2.p.rapidapi.com/video?url={url}", headers=HEADERS)
        data = r.json()

        if data.get('status_code') == 200:
            video_url = data['video_url']
            video_data = requests.get(video_url).content

            if mode == 'video':
                bot.send_video(chat_id, video_data)
                log_event(chat_id, 'video', url, 'ok')
            elif mode == 'audio':
                audio_data = extract_audio_from_mp4(video_data)
                if audio_data:
                    bot.send_audio(chat_id, audio_data)
                    log_event(chat_id, 'audio', url, 'ok')
                else:
                    bot.send_message(chat_id, "Не удалось извлечь аудио.")
                    log_event(chat_id, 'audio', url, 'error', 'audio extraction failed')
        else:
            bot.send_message(chat_id, "Не удалось найти видео.")
            log_event(chat_id, mode, url, 'error', 'video not found')
    except Exception as e:
        bot.send_message(chat_id, "Произошла ошибка при обработке.")
        log_event(chat_id, mode, url, 'error', str(e))

print("Bot running...")
bot.infinity_polling()
