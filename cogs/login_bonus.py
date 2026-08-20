import asyncio
import datetime
import logging
import discord
from discord.ext import commands
import database
from config import JST

logger = logging.getLogger(__name__)

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
                target_channel = message.channel
                from config import LOGIN_NOTIFY_CHANNEL_ID
                if LOGIN_NOTIFY_CHANNEL_ID:
                    ch = self.bot.get_channel(LOGIN_NOTIFY_CHANNEL_ID)
                    if ch:
                        target_channel = ch
                        
                await target_channel.send(reply_text, delete_after=5.0)
            except discord.HTTPException as e:
                logger.warning("ログイン通知の送信に失敗しました: %s", e)

async def setup(bot: commands.Bot):
    await bot.add_cog(LoginBonusCog(bot))
