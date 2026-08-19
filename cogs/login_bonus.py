import asyncio
import datetime
import logging
import discord
from discord.ext import commands
import database
from config import JST

logger = logging.getLogger(__name__)

WASTEBASKET_EMOJI = "🗑️"

class LoginBonusCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        now_jst = datetime.datetime.now(JST)
        today_date = now_jst.date()
        current_month_str = now_jst.strftime("%Y-%m")

        # 画像やスタンプ等のみでテキストが空の場合の対応
        msg_text = message.content.strip()
        if not msg_text:
            if message.attachments:
                msg_text = f"[Attachment: {len(message.attachments)}]"
            elif message.stickers:
                msg_text = f"[Sticker: {message.stickers[0].id}]"
            else:
                msg_text = "[Empty Media]"

        is_first_login, consecutive_days, total_points = await asyncio.to_thread(
            database.process_user_login_and_points,
            message.author.id,
            msg_text,
            today_date,
            current_month_str
        )

        if is_first_login:
            reply_text = f"-# ログインしました！\n-# {consecutive_days}日連続 | {total_points}point"
            try:
                # 環境変数でログイン通知先が指定されていればそこへ、なければ発言したチャンネルへ
                target_channel = message.channel
                from config import LOGIN_NOTIFY_CHANNEL_ID
                if LOGIN_NOTIFY_CHANNEL_ID:
                    ch = self.bot.get_channel(LOGIN_NOTIFY_CHANNEL_ID)
                    if ch:
                        target_channel = ch
                        
                sent_msg = await target_channel.send(reply_text)
                await sent_msg.add_reaction(WASTEBASKET_EMOJI)
            except discord.HTTPException as e:
                logger.warning("ログイン通知の送信またはリアクション付与に失敗しました: %s", e)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Bot自身のリアクションイベントは無視（ただし誰かが後から押したリアクションを処理）
        if payload.user_id == self.bot.user.id:
            return

        emoji_str = str(payload.emoji)
        if emoji_str not in ("🗑️", "🗑"):
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(payload.channel_id)
            except discord.HTTPException:
                return

        try:
            msg = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            return

        if msg.author.id == self.bot.user.id and "ログインしました！" in msg.content:
            try:
                await msg.delete()
            except discord.HTTPException as e:
                logger.warning("ログイン通知メッセージの自動削除に失敗しました: %s", e)

async def setup(bot: commands.Bot):
    await bot.add_cog(LoginBonusCog(bot))
