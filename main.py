import re
import os
import json
import requests
import telebot
from datetime import datetime


API_TOKEN = '8332384363:AAF5oAOn78qR3HR0QDn3etfvTXaKhkCbPUE'
LOG_FILE = 'downloads.log'

bot = telebot.TeleBot(API_TOKEN)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9'
}

user_mode = {}

# ----------- Helpers -----------
def log_event(user_id, action, url, status, note=''):
    t = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    line = f"{t}\t{user_id}\t{action}\t{url}\t{status}\t{note}\n"
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line)

def safe_json_load(s):
    try:
        return json.loads(s)
    except Exception:
        return None

def extract_json_from_sigi(page):
    m = re.search(r'<script id=\"SIGI_STATE\">(.*?)</script>', page, re.S)
    if m:
        raw = m.group(1)
        jmatch = re.search(r'=\\s*(\\{.*\\})', raw, re.S)
        if jmatch:
            return safe_json_load(jmatch.group(1))
    return None

def find_mp4_urls_in_text(text):
    urls = re.findall(r'https?:\\\\?/\\\\?/[^\\\"\\'\\'\\s>]+\\.mp4', text)
    clean = [u.replace('\\\\/', '/').replace('\\\\u0026', '&') for u in urls]
    return clean

def extract_video_url(page_text):
    try:
        sigi = extract_json_from_sigi(page_text)
        if sigi:
            stack = [sigi]
            while stack:
                node = stack.pop()
                if isinstance(node, dict):
                    if 'downloadAddr' in node and isinstance(node['downloadAddr'], dict):
                        url = node['downloadAddr'].get('url_list') or node['downloadAddr'].get('url')
                        if isinstance(url, list) and url:
                            return url[0]
                    if 'playAddr' in node and isinstance(node['playAddr'], dict):
                        url = node['playAddr'].get('url_list') or node['playAddr'].get('url')
                        if isinstance(url, list) and url:
                            return url[0]
                    for v in node.values():
                        if isinstance(v, (dict, list)):
                            stack.append(v)
                elif isinstance(node, list):
                    for v in node:
                        if isinstance(v, (dict, list)):
                            stack.append(v)
    except Exception:
        pass

    mp4s = find_mp4_urls_in_text(page_text)
    if mp4s:
        return mp4s[0]

    m = re.search(r'\"downloadAddr\"\\s*:\\s*\"(https?:\\\\?/\\\\?/[^\\\"]+)\"', page_text)
    if m:
        return m.group(1).replace('\\\\/', '/')

    m = re.search(r'\"playAddr\"\\s*:\\s*\"(https?:\\\\?/\\\\?/[^\\\"]+)\"', page_text)
    if m:
        return m.group(1).replace('\\\\/', '/')

    return None

def extract_audio_from_mp4(mp4_bytes):
    try:
        import subprocess
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
        except Exception:
            pass
        return data
    except Exception:
        return None

# ----------- Bot Handlers -----------
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
        bot.send_message(call.message.chat.id, "Отправь ссылку, и я пришлю только аудио (mp3 если возможно).")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    chat_id = message.chat.id
    text = (message.text or '').strip()

    if chat_id not in user_mode:
        bot.send_message(chat_id, "Сначала нажми кнопку /start и выбери действие.")
        return

    mode = user_mode.get(chat_id)
    url = text
    bot.send_message(chat_id, "Обрабатываю ссылку, это может занять несколько секунд...")

    try:
        r = requests.get(url, headers=HEADERS)
        video_url = extract_video_url(r.text)
        if not video_url:
            bot.send_message(chat_id, "Не удалось найти видео.")
            log_event(chat_id, mode, url, 'error', 'video not found')
            return

        video_data = requests.get(video_url, headers=HEADERS).content
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
    except Exception as e:
        bot.send_message(chat_id, "Произошла ошибка при обработке.")
        log_event(chat_id, mode, url, 'error', str(e))

print("Bot running...")
bot.infinity_polling()
