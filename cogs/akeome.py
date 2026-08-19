import asyncio
import datetime
import logging
import discord
from discord.ext import commands, tasks
from discord import app_commands
import database
from config import JST, AKEOME_STAMP_ID, NUMBER_EMOJIS

logger = logging.getLogger(__name__)

class AkeomeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.announce_daily_akeome.start()

    def cog_unload(self):
        self.announce_daily_akeome.cancel()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        if user.bot:
            return
        emoji_id = getattr(reaction.emoji, "id", None)
        if emoji_id != AKEOME_STAMP_ID:
            return

        msg = reaction.message
        race_channel_id = await asyncio.to_thread(database.get_race_channel_id)
        if race_channel_id != 0 and msg.channel.id != race_channel_id:
            return

        msg_time = msg.created_at.astimezone(JST)
        today_00 = datetime.datetime.combine(msg_time.date(), datetime.time.min, tzinfo=JST)
        tomorrow_00 = today_00 + datetime.timedelta(days=1)

        if msg_time.hour == 23 and msg_time.minute == 59:
            await asyncio.to_thread(
                database.save_akeome_record,
                user.id,
                tomorrow_00.strftime("%Y-%m-%d"),
                (msg_time - tomorrow_00).total_seconds() * 1000,
                1
            )
            return

        if msg_time.hour == 0 and msg_time.minute <= 1:
            date_str = today_00.strftime("%Y-%m-%d")
            ms = (msg_time - today_00).total_seconds() * 1000
            await asyncio.to_thread(database.save_akeome_record, user.id, date_str, ms, 0)
            await self.announce_akeome_rank(msg, user, date_str)

    async def announce_akeome_rank(self, message: discord.Message, user: discord.User, date_str: str):
        rank = await asyncio.to_thread(database.get_akeome_today_rank, user.id, date_str)
        if rank is None:
            return

        if 1 <= rank <= 9:
            try:
                await message.add_reaction(NUMBER_EMOJIS[rank - 1])
            except discord.HTTPException as e:
                logger.warning("リアクションの追加に失敗しました: %s", e)
        else:
            try:
                await message.channel.send(f"{user.mention} **{rank}位！**")
            except discord.HTTPException as e:
                logger.warning("ランクメッセージの送信に失敗しました: %s", e)

    @app_commands.command(name="akeome_ranking", description="今月のあけおめ最速ランキングを表示します")
    async def akeome_ranking(self, interaction: discord.Interaction):
        await interaction.response.defer()
        now = datetime.datetime.now(JST)
        prefix = now.strftime("%Y-%m-")
        rankings = await asyncio.to_thread(database.fetch_monthly_akeome_rank, prefix)
        if not rankings:
            return await interaction.followup.send("今月の正常な記録はまだ存在しない。")

        embed = discord.Embed(title=f"月間最速ランキング ({now.strftime('%Y-%m')})", color=discord.Color.dark_red())
        desc_lines = []
        for idx, (uid, best_ms) in enumerate(rankings, 1):
            u = self.bot.get_user(uid)
            u_name = u.display_name if u else f"同志({uid})"
            desc_lines.append(f"[{idx}位] {u_name} : +{best_ms:.3f} ms\n")

        embed.description = "".join(desc_lines)
        await interaction.followup.send(embed=embed)

    @tasks.loop(time=datetime.time(hour=0, minute=0, second=30, tzinfo=JST))
    async def announce_daily_akeome(self):
        race_channel_id = await asyncio.to_thread(database.get_race_channel_id)
        if not race_channel_id:
            return
        channel = self.bot.get_channel(race_channel_id)
        if not channel:
            return
        today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")

        success_records, flying_records = await asyncio.to_thread(database.fetch_daily_akeome_data, today_str)
        embed = discord.Embed(title=f"あけおめ計測結果 ({today_str})", color=discord.Color.red())

        s_lines = []
        for idx, (uid, ms) in enumerate(success_records, 1):
            u = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            s_lines.append(f"{idx}位: {u.display_name} ( +{ms:.3f} ms )\n")

        f_lines = []
        for uid, ms in flying_records:
            u = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            f_lines.append(f"{u.display_name} ( {ms:.3f} ms )\n")

        embed.add_field(name="成功者 (最速順)", value="".join(s_lines) or "データなし", inline=False)
        if f_lines:
            embed.add_field(name="フライング (シベリア行き)", value="".join(f_lines), inline=False)
        await channel.send(embed=embed)

    @announce_daily_akeome.before_loop
    async def before_announce_daily_akeome(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(AkeomeCog(bot))
