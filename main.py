import os
import sqlite3
import datetime
import asyncio
import random
import gc
import discord
from discord.ext import commands, tasks
from discord import app_commands

# ==============================================================================
# 0. Keitocloud対策：DBファイルの絶対パス完全固定
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "kyosan_bot.db")

TOKEN = os.getenv("DISCORD_TOKEN")

# 1. 設定 (IDはすべてint型に統一してバグを排除)
JST = datetime.timezone(datetime.timedelta(hours=9))

RANKING_CHANNEL_ID = 1460245743922057310

ALLOWED_ROLES = (
    1469555399756615835, 1398110342860509409, 1433062261903069374,
    1427967221593931826, 1467161693036482683, 1408779185681338448
)

# race_channel / 各種設定は起動時に bot_config から読み込む（未設定時の既定値）
DEFAULT_RACE_CHANNEL_ID = 1370574936963285055

# あけおめ判定に使うカスタムスタンプの絵文字ID
AKEOME_STAMP_ID = 1515228180343160943

NUMBER_EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]

# --- メモリ極限軽量化のためのインテント＆キャッシュ制限 ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    member_cache_flags=discord.MemberCacheFlags.none(), # メンバーキャッシュ封印
    chunk_guilds_at_startup=False,                    # 起動時の一括キャッシュ禁止
    max_messages=5                                    # メッセージ保持数最小化
)

# ==============================================================================
# 2. データベース統制
# ==============================================================================
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
        conn.commit()

# ★ 決定打：Bot接続「前」にDBとテーブルを物理生成する（競合エラー完全消滅）
init_db()

def get_config(key: str, default=None):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM bot_config WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

def set_config(key: str, value):
    with get_db_connection() as conn:
        conn.execute("INSERT INTO bot_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))
        conn.commit()

def get_scan_targets():
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT channel_id, notify FROM scan_targets")
        return cur.fetchall()

def get_race_channel_id():
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
            conn.execute("INSERT INTO akeome_records (user_id, date_str, response_ms, is_flying) VALUES (?, ?, ?, ?)", (user_id, date_str, ms, is_flying))
            conn.commit()
        except sqlite3.IntegrityError: pass

def get_akeome_today_rank(user_id: int, date_str: str):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM akeome_records WHERE date_str = ? AND is_flying = 0 AND response_ms <= (SELECT response_ms FROM akeome_records WHERE user_id = ? AND date_str = ? AND is_flying = 0)", (date_str, user_id, date_str))
        row = cur.fetchone()
        return row[0] if row else None

# ==============================================================================
# 3. メッセージ監視
# ==============================================================================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    thread_id = message.channel.id if isinstance(message.channel, discord.Thread) else None
    thread_name = message.channel.name if thread_id else None
    await asyncio.to_thread(increment_msg_count, message.author.id, thread_id, thread_name)

    await bot.process_commands(message)

@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    if user.bot: return
    # カスタムスタンプ以外（通常絵文字等）は無視
    emoji_id = getattr(reaction.emoji, "id", None)
    if emoji_id != AKEOME_STAMP_ID:
        return

    msg = reaction.message
    race_channel_id = get_race_channel_id()
    if race_channel_id != 0 and msg.channel.id != race_channel_id:
        return

    msg_time = msg.created_at.astimezone(JST)
    today_00 = datetime.datetime.combine(msg_time.date(), datetime.time.min, tzinfo=JST)
    tomorrow_00 = today_00 + datetime.timedelta(days=1)

    # フライング：前日 23:59:00 〜 23:59:59（秒閾値なし、全秒記録）
    if msg_time.hour == 23 and msg_time.minute == 59:
        save_akeome_record(user.id, tomorrow_00.strftime("%Y-%m-%d"), (msg_time - tomorrow_00).total_seconds() * 1000, 1)
        return
    # 成功：当日 0:00:00 〜 0:01:00（JST、window拡張）
    if msg_time.hour == 0 and msg_time.minute <= 1:
        date_str = today_00.strftime("%Y-%m-%d")
        ms = (msg_time - today_00).total_seconds() * 1000
        save_akeome_record(user.id, date_str, ms, 0)
        await announce_akeome_rank(msg, user, date_str)

async def announce_akeome_rank(message: discord.Message, user: discord.User, date_str: str):
    rank = get_akeome_today_rank(user.id, date_str)
    if rank is None: return

    if 1 <= rank <= 9:
        try: await message.add_reaction(NUMBER_EMOJIS[rank - 1])
        except: pass
    else:
        try: await message.channel.send(f"{user.mention} **{rank}位！**")
        except: pass

# ==============================================================================
# 4. 走査ロジック（省メモリ高速化）
# ==============================================================================
async def perform_thread_sync(target_channel, notify_channel=None):
    thread_counts = {}

    threads_dict = {t.id: t for t in target_channel.threads}
    async for thread in target_channel.archived_threads(limit=None):
        threads_dict[thread.id] = thread
    threads = list(threads_dict.values())

    total = len(threads)
    status_msg = None
    if notify_channel:
        try:
            status_msg = await notify_channel.send(f"📊 **走査開始... (重複排除済: 全 {total} スレッドを処理予定)**")
        except: pass

    for i, thread in enumerate(threads):
        if status_msg and i > 0 and i % 10 == 0:
            pct = int((i / total) * 100) if total else 100
            try:
                await status_msg.edit(content=f"🔄 走査中... ({i}/{total} スレッド完了) ({pct}%)")
            except: pass
        try:
            cnt = 0
            async for msg in thread.history(limit=None):
                if not msg.author.bot: cnt += 1
            thread_counts[thread.id] = {"name": thread.name, "count": cnt}
        except Exception: pass
        await asyncio.sleep(0.1)

    def _bulk_save():
        with get_db_connection() as conn:
            conn.execute("DELETE FROM thread_activity")
            for tid, data in thread_counts.items():
                conn.execute("INSERT INTO thread_activity (thread_id, thread_name, msg_count) VALUES (?, ?, ?)", (tid, data["name"], data["count"]))
            conn.commit()

    await asyncio.to_thread(_bulk_save)

    if status_msg:
        try:
            await status_msg.edit(content=f"✅ **計画経済達成。DBを浄化し、全 {total} スレッドの正確な再構築が完了した。**")
        except: pass
    gc.collect()

async def run_all_scans(notify_channel=None):
    targets = get_scan_targets()
    if not targets:
        if notify_channel:
            try: await notify_channel.send("⚠️ 走査対象チャンネルが未登録です。`/setting add_target` で登録してください。")
            except: pass
        return
    for channel_id, notify in targets:
        channel = bot.get_channel(channel_id)
        if not channel:
            continue
        target_notify = notify_channel if (notify and notify_channel) else None
        await perform_thread_sync(channel, target_notify)

# ==============================================================================
# 5. 各種自動タスク
# ==============================================================================
@tasks.loop(time=datetime.time(hour=0, minute=0, second=30, tzinfo=JST))
async def announce_daily_akeome():
    race_channel_id = get_race_channel_id()
    if not race_channel_id: return
    channel = bot.get_channel(race_channel_id)
    if not channel: return
    today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")
    def _fetch_data():
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, response_ms FROM akeome_records WHERE date_str = ? AND is_flying = 0 ORDER BY response_ms ASC", (today_str,))
            success = cur.fetchall()
            cur.execute("SELECT user_id, response_ms FROM akeome_records WHERE date_str = ? AND is_flying = 1 ORDER BY response_ms DESC", (today_str,))
            return success, cur.fetchall()
    success_records, flying_records = await asyncio.to_thread(_fetch_data)
    embed = discord.Embed(title=f"あけおめ計測結果 ({today_str})", color=discord.Color.red())

    s_lines = []
    for idx, (uid, ms) in enumerate(success_records, 1):
        u = bot.get_user(uid) or await bot.fetch_user(uid)
        s_lines.append(f"{idx}位: {u.display_name} ( +{ms:.3f} ms )\n")

    f_lines = []
    for uid, ms in flying_records:
        u = bot.get_user(uid) or await bot.fetch_user(uid)
        f_lines.append(f"{u.display_name} ( {ms:.3f} ms )\n")

    embed.add_field(name="成功者 (最速順)", value="".join(s_lines) or "データなし", inline=False)
    if f_lines: embed.add_field(name="フライング (シベリア行き)", value="".join(f_lines), inline=False)
    await channel.send(embed=embed)

@tasks.loop(time=datetime.time(hour=20, minute=0, second=0, tzinfo=JST))
async def weekly_ranking_post():
    if datetime.datetime.now(JST).weekday() != 4: return
    if not RANKING_CHANNEL_ID: return
    channel = bot.get_channel(RANKING_CHANNEL_ID)
    if not channel: return
    embeds = await generate_ranking_embeds(hide_user=False)
    await channel.send(content="**【定時連絡】今週の労働・活動実績を配給する。**", embed=embeds[0])
    for emb in embeds[1:]:
        await channel.send(embed=emb)

@tasks.loop(time=datetime.time(hour=4, minute=0, second=0, tzinfo=JST))
async def automated_thread_sync():
    if datetime.datetime.now(JST).toordinal() % 3 != 0: return
    notify_channel = bot.get_channel(RANKING_CHANNEL_ID)
    if notify_channel:
        try: await notify_channel.send("⏱️ **【定時連絡】深夜4時の定期スレッド自動走査を開始する。**")
        except: pass
    await run_all_scans(notify_channel)

async def generate_ranking_embeds(hide_user: bool = False):
    user_limit = 30
    thread_limit = 34

    def _fetch_ranking():
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, total_msg_count FROM user_activity ORDER BY total_msg_count DESC LIMIT ?", (user_limit,))
            u_ranks = cur.fetchall()
            cur.execute("SELECT thread_id, thread_name, msg_count FROM thread_activity ORDER BY msg_count DESC LIMIT ?", (thread_limit,))
            return u_ranks, cur.fetchall()

    user_ranks, thread_ranks = await asyncio.to_thread(_fetch_ranking)

    u_text = ""
    if not hide_user:
        for idx, (uid, count) in enumerate(user_ranks, 1):
            user = bot.get_user(uid)
            name = user.display_name if user else f"同志({uid})"
            u_text += f"➡️ {idx}位 {name} : {count}\n"
            if idx % 10 == 0 and idx != len(user_ranks):
                u_text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"

    t_text = ""
    for idx, (tid, tname, count) in enumerate(thread_ranks, 1):
        t_text += f"➡️ {idx}位 {tname} {count}\n"
        if idx % 10 == 0 and idx != len(thread_ranks):
            t_text += "━━━━━━━━━━━━━━━━━━━━━━━━\n"

    embeds = []
    base_title = "国家労働実績ランキング"
    current_embed = discord.Embed(title=base_title, color=discord.Color.red())

    def add_long_field(name_prefix, value):
        nonlocal current_embed
        if not value: return
        lines = value.strip().split('\n')
        current_chunk = ""
        part = 1
        for line in lines:
            if len(current_chunk) + len(line) + 1 > 1000:
                field_name = f"{name_prefix} (その{part})" if part > 1 else name_prefix
                if len(current_embed) + len(field_name) + len(current_chunk) > 5500:
                    embeds.append(current_embed)
                    current_embed = discord.Embed(title=f"{base_title} (続き)", color=discord.Color.red())
                current_embed.add_field(name=field_name, value=current_chunk, inline=False)
                current_chunk = line + "\n"
                part += 1
            else: current_chunk += line + "\n"

        if current_chunk:
            field_name = f"{name_prefix} (その{part})" if part > 1 else name_prefix
            if len(current_embed) + len(field_name) + len(current_chunk) > 5500:
                embeds.append(current_embed)
                current_embed = discord.Embed(title=f"{base_title} (続き)", color=discord.Color.red())
            current_embed.add_field(name=field_name, value=current_chunk, inline=False)

    if not hide_user:
        add_long_field(f"優秀労働者 (Top {user_limit})", u_text)
    add_long_field(f"活発なコルホーズ (Top {thread_limit})", t_text)

    embeds.append(current_embed)
    return embeds

# ==============================================================================
# 6. コマンド群
# ==============================================================================
@bot.tree.command(name="activity_ranking", description="現在のチャット労働実績（ランキング）を表示します")
@app_commands.describe(hide_user="Trueにするとユーザーランキングを非表示にし、スレッドのみにします")
async def activity_ranking(interaction: discord.Interaction, hide_user: bool = False):
    await interaction.response.defer()
    embeds = await generate_ranking_embeds(hide_user=hide_user)
    for emb in embeds: await interaction.followup.send(embed=emb)

@bot.tree.command(name="akeome_ranking", description="今月のあけおめ最速ランキングを表示します")
async def akeome_ranking(interaction: discord.Interaction):
    await interaction.response.defer()
    now = datetime.datetime.now(JST)
    prefix = now.strftime("%Y-%m-")
    def _get_monthly_rank():
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT user_id, MIN(response_ms) as best_ms FROM akeome_records WHERE date_str LIKE ? AND is_flying = 0 GROUP BY user_id ORDER BY best_ms ASC LIMIT 15", (f"{prefix}%",))
            return cur.fetchall()
    rankings = await asyncio.to_thread(_get_monthly_rank)
    if not rankings: return await interaction.followup.send("今月の正常な記録はまだ存在しない。")

    embed = discord.Embed(title=f"月間最速ランキング ({now.strftime('%Y-%m')})", color=discord.Color.dark_red())
    desc_lines = []
    for idx, (uid, best_ms) in enumerate(rankings, 1):
        u = bot.get_user(uid)
        u_name = u.display_name if u else f"同志({uid})"
        desc_lines.append(f"[{idx}位] {u_name} : +{best_ms:.3f} ms\n")

    embed.description = "".join(desc_lines)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="omikuji", description="今日の君の運勢（党からの評価）を占う")
async def omikuji(interaction: discord.Interaction):
    results = [
        ("🌟 大吉 (書記長)", "同志よ、君の指導力は最高潮だ。五カ年計画は1年で達成されるだろう！", 0xffd700),
        ("📈 中吉 (中央委員)", "順調な労働 of 成果が出ている。党からの評価も上々だ。", 0xffa500),
        ("🔨 小吉 (模範労働者)", "地道なトラクター生産が実を結ぶ日も近い。ノルマ達成に向けて邁進せよ。", 0xadd8e6),
        ("☁️ 末吉 (一般党員)", "資本主義の誘惑に負けず、配給の列に並ぶのだ。", 0x808080),
        ("📉 凶 (自己批判)", "ブルジョワ的傾向が見られる。直ちに自己批判書を提出せよ。", 0x8b0000),
        ("💀 大凶 (シベリア送り)", "KGBが君のドアをノックしている。暖かい衣服を用意したまえ……", 0x000000),
        ("💥 粛清", "君は最初から写真に写っていなかった。いいね？", 0xff0000)
    ]
    title, desc, color = random.choice(results)
    embed = discord.Embed(title=f"運勢: {title}", description=desc, color=color)
    embed.set_footer(text="※党の決定は絶対です。")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="stats", description="あなたの労働実績（総発言数と順位）を表示します")
async def stats(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    uid = interaction.user.id
    def _fetch():
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT total_msg_count FROM user_activity WHERE user_id = ?", (uid,))
            row = cur.fetchone()
            count = row[0] if row else 0
            cur.execute("SELECT COUNT(*) FROM user_activity WHERE total_msg_count > ?", (count,))
            higher = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM user_activity")
            total = cur.fetchone()[0]
            return count, higher + 1, total
    count, rank, total_users = await asyncio.to_thread(_fetch)
    embed = discord.Embed(title="📋 あなたの労働実績", color=discord.Color.red())
    embed.add_field(name="総発言数", value=f"{count} 回", inline=True)
    embed.add_field(name="全体順位", value=f"{rank} 位 / {total_users} 名中", inline=True)
    await interaction.followup.send(embed=embed)

def is_authorized_for_censor(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator: return True
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(role_id in user_role_ids for role_id in ALLOWED_ROLES)

@bot.tree.command(name="censor", description="【管理者/権限ロール専用】指定ユーザーのメッセージを粛清する")
async def censor(interaction: discord.Interaction, target: discord.Member, limit: int = 50):
    if not is_authorized_for_censor(interaction):
        return await interaction.response.send_message("❌ 権限がありません。KGBに通報しました。", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=limit, check=lambda m: m.author.id == target.id)
    await interaction.followup.send(f"粛清完了: {target.display_name} の痕跡を {len(deleted)} 件消し去った。")

@bot.tree.command(name="setting", description="【管理者/権限ロール専用】走査設定を管理します")
@app_commands.describe(
    action="操作の種類",
    channel="add_target/remove_target/set_race_channel で指定するチャンネル",
    notify="toggle_notify で通知を有効にするか"
)
@app_commands.choices(action=[
    app_commands.Choice(name="add_target", value="add_target"),
    app_commands.Choice(name="remove_target", value="remove_target"),
    app_commands.Choice(name="toggle_notify", value="toggle_notify"),
    app_commands.Choice(name="list_targets", value="list_targets"),
    app_commands.Choice(name="set_race_channel", value="set_race_channel"),
])
async def setting(
    interaction: discord.Interaction,
    action: app_commands.Choice[str],
    channel: discord.TextChannel = None,
    notify: bool = True
):
    if not is_authorized_for_censor(interaction):
        return await interaction.response.send_message("❌ 権限がありません。KGBに通報しました。", ephemeral=True)
    await interaction.response.defer(ephemeral=True)

    act = action.value
    if act == "add_target":
        if not channel:
            return await interaction.followup.send("❌ チャンネルを指定してください。")
        with get_db_connection() as conn:
            conn.execute("INSERT OR IGNORE INTO scan_targets (channel_id, notify) VALUES (?, 1)", (channel.id,))
            conn.commit()
        await interaction.followup.send(f"✅ 走査対象に追加: {channel.mention}")

    elif act == "remove_target":
        if not channel:
            return await interaction.followup.send("❌ チャンネルを指定してください。")
        with get_db_connection() as conn:
            conn.execute("DELETE FROM scan_targets WHERE channel_id = ?", (channel.id,))
            conn.commit()
        await interaction.followup.send(f"🗑️ 走査対象から削除: {channel.mention}")

    elif act == "toggle_notify":
        if not channel:
            return await interaction.followup.send("❌ チャンネルを指定してください。")
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT notify FROM scan_targets WHERE channel_id = ?", (channel.id,))
            row = cur.fetchone()
            if not row:
                return await interaction.followup.send("❌ そのチャンネルは走査対象に登録されていません。")
            new_val = 0 if row[0] else 1
            conn.execute("UPDATE scan_targets SET notify = ? WHERE channel_id = ?", (new_val, channel.id))
            conn.commit()
        state = "有効" if new_val else "無効"
        await interaction.followup.send(f"🔔 {channel.mention} の走査通知: {state}")

    elif act == "list_targets":
        targets = get_scan_targets()
        if not targets:
            return await interaction.followup.send("📭 走査対象チャンネルは未登録です。")
        lines = []
        for cid, notify in targets:
            ch = bot.get_channel(cid)
            name = ch.mention if ch else f"#{cid}"
            lines.append(f"{name} (通知: {'有効' if notify else '無効'})")
        race_id = get_race_channel_id()
        race_ch = bot.get_channel(race_id)
        race_name = race_ch.mention if race_ch else f"#{race_id}"
        await interaction.followup.send(
            f"📋 **走査対象チャンネル**\n" + "\n".join(lines) + f"\n\n🎯 **あけおめ受付チャンネル**: {race_name}"
        )

    elif act == "set_race_channel":
        if not channel:
            return await interaction.followup.send("❌ チャンネルを指定してください。")
        set_config("race_channel", channel.id)
        await interaction.followup.send(f"🎯 あけおめ受付チャンネルを {channel.mention} に設定しました。")

@bot.tree.command(name="soviet_sync", description="【管理者専用】指定スレッドの全ログを手動で回収し、DBを浄化する")
async def soviet_sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ 管理者権限がありません。シベリアへ送ります。", ephemeral=True)
    await interaction.response.send_message("国家総動員計画発動。走査を開始する。")
    notify_channel = interaction.channel
    bot.loop.create_task(run_all_scans(notify_channel))

@bot.event
async def on_ready():
    await bot.tree.sync()
    if not announce_daily_akeome.is_running(): announce_daily_akeome.start()
    if not weekly_ranking_post.is_running(): weekly_ranking_post.start()
    if not automated_thread_sync.is_running(): automated_thread_sync.start()
    print(f"システム稼働。共産趣味ボット統制下オンライン。({bot.user})")

if __name__ == "__main__":
    bot.run(TOKEN)
