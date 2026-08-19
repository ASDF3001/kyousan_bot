import os
import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "kyosan_bot.db")

TOKEN = os.getenv("DISCORD_TOKEN")

JST = datetime.timezone(datetime.timedelta(hours=9))

def parse_int_env(key: str, default=None):
    val = os.getenv(key)
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return default

def parse_int_list_env(key: str, default=None):
    if default is None:
        default = tuple()
    val = os.getenv(key)
    if val:
        try:
            return tuple(int(x.strip()) for x in val.split(",") if x.strip())
        except ValueError:
            pass
    return default

RANKING_CHANNEL_ID = parse_int_env("RANKING_CHANNEL_ID")
DEFAULT_RACE_CHANNEL_ID = parse_int_env("DEFAULT_RACE_CHANNEL_ID")
AKEOME_STAMP_ID = parse_int_env("AKEOME_STAMP_ID")

# ログイン通知を特定のチャンネルに固定したい場合はこれを設定
LOGIN_NOTIFY_CHANNEL_ID = parse_int_env("LOGIN_NOTIFY_CHANNEL_ID")

ALLOWED_ROLES = parse_int_list_env("ALLOWED_ROLES")

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
