import asyncio
import datetime
import logging
import discord
from discord.ext import commands, tasks
from discord import app_commands
import database
from config import JST, RANKING_CHANNEL_ID

logger = logging.getLogger(__name__)

async def generate_ranking_embeds(bot: commands.Bot, hide_user: bool = False):
    user_limit = 30
    thread_limit = 34

    user_ranks, thread_ranks = await asyncio.to_thread(database.fetch_ranking_data, user_limit, thread_limit)

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
        if not value:
            return
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
            else:
                current_chunk += line + "\n"

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

class ActivityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.weekly_ranking_post.start()

    def cog_unload(self):
        self.weekly_ranking_post.cancel()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        thread_id = message.channel.id if isinstance(message.channel, discord.Thread) else None
        thread_name = message.channel.name if thread_id else None
        await asyncio.to_thread(database.increment_msg_count, message.author.id, thread_id, thread_name)

    @app_commands.command(name="activity_ranking", description="現在のチャット労働実績（ランキング）を表示します")
    @app_commands.describe(hide_user="Trueにするとユーザーランキングを非表示にし、スレッドのみにします")
    async def activity_ranking(self, interaction: discord.Interaction, hide_user: bool = False):
        await interaction.response.defer()
        embeds = await generate_ranking_embeds(self.bot, hide_user=hide_user)
        for emb in embeds:
            await interaction.followup.send(embed=emb)

    @app_commands.command(name="stats", description="あなたの労働実績（総発言数・獲得ポイント・順位）を表示します")
    async def stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        uid = interaction.user.id
        count, rank, total_users, pts, pts_rank, consecutive = await asyncio.to_thread(database.fetch_user_stats, uid)
        embed = discord.Embed(title="📋 あなたの労働実績", color=discord.Color.red())
        embed.add_field(name="総発言数", value=f"{count} 回 ({rank}位 / {total_users}名中)", inline=False)
        embed.add_field(name="今月のポイント", value=f"{pts} point ({pts_rank}位)", inline=True)
        embed.add_field(name="連続ログイン", value=f"{consecutive} 日", inline=True)
        await interaction.followup.send(embed=embed)

    @tasks.loop(time=datetime.time(hour=20, minute=0, second=0, tzinfo=JST))
    async def weekly_ranking_post(self):
        if datetime.datetime.now(JST).weekday() != 4:
            return
        if not RANKING_CHANNEL_ID:
            return
        channel = self.bot.get_channel(RANKING_CHANNEL_ID)
        if not channel:
            return
        embeds = await generate_ranking_embeds(self.bot, hide_user=False)
        await channel.send(content="**【定時連絡】今週の労働・活動実績を配給する。**", embed=embeds[0])
        for emb in embeds[1:]:
            await channel.send(embed=emb)

    @weekly_ranking_post.before_loop
    async def before_weekly_ranking_post(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityCog(bot))
