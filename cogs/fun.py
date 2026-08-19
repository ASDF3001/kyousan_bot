import random
import discord
from discord.ext import commands
from discord import app_commands

class FunCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="omikuji", description="今日の君の運勢（党からの評価）を占う")
    async def omikuji(self, interaction: discord.Interaction):
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

async def setup(bot: commands.Bot):
    await bot.add_cog(FunCog(bot))
