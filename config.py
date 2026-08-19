import os
import datetime
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "kyosan_bot.db")

TOKEN = os.getenv("DISCORD_TOKEN")

JST = datetime.timezone(datetime.timedelta(hours=9))

def parse_int_env(key: str, default: int) -> int:
    val = os.getenv(key)
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return default

def parse_int_list_env(key: str, default: tuple) -> tuple:
    val = os.getenv(key)
    if val:
        try:
            return tuple(int(x.strip()) for x in val.split(",") if x.strip())
        except ValueError:
            pass
    return default

RANKING_CHANNEL_ID = parse_int_env("RANKING_CHANNEL_ID", 1460245743922057310)

ALLOWED_ROLES = parse_int_list_env(
    "ALLOWED_ROLES",
    (
        1469555399756615835, 1398110342860509409, 1433062261903069374,
        1427967221593931826, 1467161693036482683, 1408779185681338448
    )
)

DEFAULT_RACE_CHANNEL_ID = parse_int_env("DEFAULT_RACE_CHANNEL_ID", 1370574936963285055)
AKEOME_STAMP_ID = parse_int_env("AKEOME_STAMP_ID", 1515228180343160943)

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
