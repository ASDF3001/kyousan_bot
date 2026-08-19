import sqlite3
import logging
import time
from config import DB_PATH, DEFAULT_RACE_CHANNEL_ID

logger = logging.getLogger(__name__)

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS user_activity (user_id INTEGER PRIMARY KEY, total_msg_count INTEGER DEFAULT 0)")
        cursor.execute("CREATE TABLE IF NOT EXISTS thread_activity (thread_id INTEGER PRIMARY KEY, thread_name TEXT, msg_count INTEGER DEFAULT 0)")
        cursor.execute("CREATE TABLE IF NOT EXISTS akeome_records (user_id INTEGER, date_str TEXT, response_ms REAL, is_flying INTEGER, PRIMARY KEY (user_id, date_str))")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_akeome_perf ON akeome_records (date_str, is_flying, response_ms);")
        cursor.execute("CREATE TABLE IF NOT EXISTS scan_targets (channel_id INTEGER PRIMARY KEY, notify INTEGER DEFAULT 1)")
        cursor.execute("CREATE TABLE IF NOT EXISTS bot_config (key TEXT PRIMARY KEY, value TEXT)")
        
        # ポイント＆ログイン機能テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_points (
                user_id INTEGER PRIMARY KEY,
                monthly_points INTEGER DEFAULT 0,
                consecutive_days INTEGER DEFAULT 0,
                last_login_date TEXT,
                last_msg_content TEXT,
                current_month TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monthly_point_history (
                user_id INTEGER,
                month_str TEXT,
                final_points INTEGER,
                PRIMARY KEY (user_id, month_str)
            )
        """)
        conn.commit()

def get_config(key: str, default=None):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM bot_config WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

def set_config(key: str, value):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO bot_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value))
        )
        conn.commit()

def get_scan_targets():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT channel_id, notify FROM scan_targets")
        return cur.fetchall()

def get_race_channel_id() -> int:
    val = get_config("race_channel")
    return int(val) if val else DEFAULT_RACE_CHANNEL_ID

def increment_msg_count(user_id: int, thread_id: int = None, thread_name: str = None):
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO user_activity (user_id, total_msg_count)
            VALUES (?, 1) ON CONFLICT(user_id) DO UPDATE SET total_msg_count = total_msg_count + 1
        """, (user_id,))
        if thread_id and thread_name:
            conn.execute("""
                INSERT INTO thread_activity (thread_id, thread_name, msg_count)
                VALUES (?, ?, 1) ON CONFLICT(thread_id) DO UPDATE SET msg_count = msg_count + 1, thread_name = ?
            """, (thread_id, thread_name, thread_name))
        conn.commit()

def save_akeome_record(user_id: int, date_str: str, ms: float, is_flying: int):
    with get_db_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO akeome_records (user_id, date_str, response_ms, is_flying) VALUES (?, ?, ?, ?)",
                (user_id, date_str, ms, is_flying)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            pass

def get_akeome_today_rank(user_id: int, date_str: str):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM akeome_records WHERE date_str = ? AND is_flying = 0 AND response_ms <= (SELECT response_ms FROM akeome_records WHERE user_id = ? AND date_str = ? AND is_flying = 0)",
            (date_str, user_id, date_str)
        )
        row = cur.fetchone()
        return row[0] if row else None

def bulk_save_thread_activity(thread_counts: dict):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM thread_activity")
        for tid, data in thread_counts.items():
            conn.execute(
                "INSERT INTO thread_activity (thread_id, thread_name, msg_count) VALUES (?, ?, ?)",
                (tid, data["name"], data["count"])
            )
        conn.commit()

def fetch_daily_akeome_data(today_str: str):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, response_ms FROM akeome_records WHERE date_str = ? AND is_flying = 0 ORDER BY response_ms ASC", (today_str,))
        success = cur.fetchall()
        cur.execute("SELECT user_id, response_ms FROM akeome_records WHERE date_str = ? AND is_flying = 1 ORDER BY response_ms DESC", (today_str,))
        flying = cur.fetchall()
        return success, flying

def fetch_ranking_data(user_limit: int, thread_limit: int):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, total_msg_count FROM user_activity ORDER BY total_msg_count DESC LIMIT ?", (user_limit,))
        u_ranks = cur.fetchall()
        cur.execute("SELECT thread_id, thread_name, msg_count FROM thread_activity ORDER BY msg_count DESC LIMIT ?", (thread_limit,))
        t_ranks = cur.fetchall()
        return u_ranks, t_ranks

def fetch_monthly_akeome_rank(prefix: str):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, MIN(response_ms) as best_ms FROM akeome_records WHERE date_str LIKE ? AND is_flying = 0 GROUP BY user_id ORDER BY best_ms ASC LIMIT 15",
            (f"{prefix}%",)
        )
        return cur.fetchall()

def fetch_user_stats(uid: int):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT total_msg_count FROM user_activity WHERE user_id = ?", (uid,))
        row = cur.fetchone()
        count = row[0] if row else 0
        cur.execute("SELECT COUNT(*) FROM user_activity WHERE total_msg_count > ?", (count,))
        higher = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM user_activity")
        total = cur.fetchone()[0]
        
        # ポイント情報取得
        cur.execute("SELECT monthly_points, consecutive_days FROM user_points WHERE user_id = ?", (uid,))
        p_row = cur.fetchone()
        pts = p_row[0] if p_row else 0
        consecutive = p_row[1] if p_row else 0
        
        cur.execute("SELECT COUNT(*) FROM user_points WHERE monthly_points > ?", (pts,))
        pts_rank = cur.fetchone()[0] + 1
        
        return count, higher + 1, total, pts, pts_rank, consecutive

def add_scan_target(channel_id: int):
    with get_db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO scan_targets (channel_id, notify) VALUES (?, 1)", (channel_id,))
        conn.commit()

def remove_scan_target(channel_id: int):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM scan_targets WHERE channel_id = ?", (channel_id,))
        conn.commit()

def toggle_scan_target_notify(channel_id: int) -> int:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT notify FROM scan_targets WHERE channel_id = ?", (channel_id,))
        row = cur.fetchone()
        if not row:
            return None
        new_val = 0 if row[0] else 1
        conn.execute("UPDATE scan_targets SET notify = ? WHERE channel_id = ?", (new_val, channel_id))
        conn.commit()
        return new_val

def process_user_login_and_points(user_id: int, msg_content: str, today_date, current_month_str: str):
    """
    ユーザーのメッセージ受信時に呼び出し。
    月跨ぎチェック、デイリーログインチェック、同一内容スパムチェックを行い、ポイントを加算する。
    戻り値: (is_first_login: bool, consecutive_days: int, total_points: int)
    """
    today_str = today_date.strftime("%Y-%m-%d")
    yesterday_str = (today_date - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT monthly_points, consecutive_days, last_login_date, last_msg_content, current_month FROM user_points WHERE user_id = ?",
            (user_id,)
        )
        row = cur.fetchone()

        if not row:
            monthly_points = 0
            consecutive_days = 0
            last_login_date = None
            last_msg_content = None
            db_month = current_month_str
        else:
            monthly_points, consecutive_days, last_login_date, last_msg_content, db_month = row

        # 月跨ぎ判定 (月が替わった場合リセット & 履歴保存)
        if db_month != current_month_str:
            if db_month and monthly_points > 0:
                conn.execute(
                    "INSERT INTO monthly_point_history (user_id, month_str, final_points) VALUES (?, ?, ?) ON CONFLICT(user_id, month_str) DO UPDATE SET final_points = excluded.final_points",
                    (user_id, db_month, monthly_points)
                )
            monthly_points = 0
            # 月が変わっても連続ログイン日数はリセットしない！
            db_month = current_month_str

        is_first_login = False
        # 初日ログイン判定
        if last_login_date != today_str:
            is_first_login = True
            if last_login_date == yesterday_str:
                consecutive_days += 1
            else:
                consecutive_days = 1
            
            # ログインボーナス (基本 10pt + 連続日数 * 2pt)
            login_bonus = 10 + (consecutive_days * 2)
            monthly_points += login_bonus
            last_login_date = today_str

        # スパム対策：連続して全く同じ内容を連投した場合は発言ポイントなし
        clean_content = msg_content.strip()
        if last_msg_content is None or clean_content != last_msg_content:
            monthly_points += 1
            last_msg_content = clean_content

        conn.execute("""
            INSERT INTO user_points (user_id, monthly_points, consecutive_days, last_login_date, last_msg_content, current_month)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                monthly_points = excluded.monthly_points,
                consecutive_days = excluded.consecutive_days,
                last_login_date = excluded.last_login_date,
                last_msg_content = excluded.last_msg_content,
                current_month = excluded.current_month
        """, (user_id, monthly_points, consecutive_days, last_login_date, last_msg_content, db_month))
        conn.commit()

        return is_first_login, consecutive_days, monthly_points
