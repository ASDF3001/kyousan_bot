import asyncio
import logging
import discord
from discord.ext import commands

import config
import database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

database.init_db()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

class KyosanBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            member_cache_flags=discord.MemberCacheFlags.none(),
            chunk_guilds_at_startup=False,
            max_messages=5
        )

    async def setup_hook(self):
        initial_extensions = [
            "cogs.activity",
            "cogs.akeome",
            "cogs.admin",
            "cogs.fun",
            "cogs.login_bonus",
        ]
        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                logger.info("Loaded extension: %s", ext)
            except Exception as e:
                logger.error("Failed to load extension %s: %s", ext, e)

        await self.tree.sync()
        logger.info("Command tree synced.")

bot = KyosanBot()

@bot.event
async def on_ready():
    logger.info("システム稼働。共産趣味ボット統制下オンライン。(%s)", bot.user)

if __name__ == "__main__":
    if not config.TOKEN:
        logger.error("DISCORD_TOKEN が設定されていません。.env または環境変数を確認してください。")
    else:
        bot.run(config.TOKEN)
