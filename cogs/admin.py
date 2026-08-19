import asyncio
import datetime
import gc
import logging
import discord
from discord.ext import commands, tasks
from discord import app_commands
import database
from config import JST, ALLOWED_ROLES, RANKING_CHANNEL_ID

logger = logging.getLogger(__name__)

def is_authorized_for_censor(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    user_role_ids = [role.id for role in interaction.user.roles]
    return any(role_id in user_role_ids for role_id in ALLOWED_ROLES)

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.automated_thread_sync.start()

    def cog_unload(self):
        self.automated_thread_sync.cancel()

    async def perform_thread_sync(self, target_channel: discord.TextChannel, notify_channel: discord.TextChannel = None):
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
            except discord.HTTPException as e:
                logger.warning("ステータスメッセージの送信失敗: %s", e)

        for i, thread in enumerate(threads):
            if status_msg and i > 0 and i % 10 == 0:
                pct = int((i / total) * 100) if total else 100
                try:
                    await status_msg.edit(content=f"🔄 走査中... ({i}/{total} スレッド完了) ({pct}%)")
                except discord.HTTPException as e:
                    logger.warning("ステータス更新失敗: %s", e)
            try:
                cnt = 0
                async for msg in thread.history(limit=None):
                    if not msg.author.bot:
                        cnt += 1
                thread_counts[thread.id] = {"name": thread.name, "count": cnt}
            except Exception as e:
                logger.warning("スレッド %s の履歴取得失敗: %s", thread.id, e)
            await asyncio.sleep(0.1)

        await asyncio.to_thread(database.bulk_save_thread_activity, thread_counts)

        if status_msg:
            try:
                await status_msg.edit(content=f"✅ **計画経済達成。DBを浄化し、全 {total} スレッドの正確な再構築が完了した。**")
            except discord.HTTPException as e:
                logger.warning("完了メッセージの送信失敗: %s", e)
        gc.collect()

    async def run_all_scans(self, notify_channel: discord.TextChannel = None):
        targets = await asyncio.to_thread(database.get_scan_targets)
        if not targets:
            if notify_channel:
                try:
                    await notify_channel.send("⚠️ 走査対象チャンネルが未登録です。`/setting add_target` で登録してください。")
                except discord.HTTPException:
                    pass
            return
        for channel_id, notify in targets:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue
            target_notify = notify_channel if (notify and notify_channel) else None
            await self.perform_thread_sync(channel, target_notify)

    @app_commands.command(name="censor", description="【管理者/権限ロール専用】指定ユーザーのメッセージを粛清する")
    async def censor(self, interaction: discord.Interaction, target: discord.Member, limit: int = 50):
        if not is_authorized_for_censor(interaction):
            return await interaction.response.send_message("❌ 権限がありません。KGBに通報しました。", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=limit, check=lambda m: m.author.id == target.id)
        await interaction.followup.send(f"粛清完了: {target.display_name} の痕跡を {len(deleted)} 件消し去った。")

    @app_commands.command(name="setting", description="【管理者/権限ロール専用】走査設定を管理します")
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
        self,
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
            await asyncio.to_thread(database.add_scan_target, channel.id)
            await interaction.followup.send(f"✅ 走査対象に追加: {channel.mention}")

        elif act == "remove_target":
            if not channel:
                return await interaction.followup.send("❌ チャンネルを指定してください。")
            await asyncio.to_thread(database.remove_scan_target, channel.id)
            await interaction.followup.send(f"🗑️ 走査対象から削除: {channel.mention}")

        elif act == "toggle_notify":
            if not channel:
                return await interaction.followup.send("❌ チャンネルを指定してください。")
            res = await asyncio.to_thread(database.toggle_scan_target_notify, channel.id)
            if res is None:
                return await interaction.followup.send("❌ そのチャンネルは走査対象に登録されていません。")
            state = "有効" if res else "無効"
            await interaction.followup.send(f"🔔 {channel.mention} の走査通知: {state}")

        elif act == "list_targets":
            targets = await asyncio.to_thread(database.get_scan_targets)
            if not targets:
                return await interaction.followup.send("📭 走査対象チャンネルは未登録です。")
            lines = []
            for cid, notify_flag in targets:
                ch = self.bot.get_channel(cid)
                name = ch.mention if ch else f"#{cid}"
                lines.append(f"{name} (通知: {'有効' if notify_flag else '無効'})")
            race_id = await asyncio.to_thread(database.get_race_channel_id)
            race_ch = self.bot.get_channel(race_id)
            race_name = race_ch.mention if race_ch else f"#{race_id}"
            await interaction.followup.send(
                f"📋 **走査対象チャンネル**\n" + "\n".join(lines) + f"\n\n🎯 **あけおめ受付チャンネル**: {race_name}"
            )

        elif act == "set_race_channel":
            if not channel:
                return await interaction.followup.send("❌ チャンネルを指定してください。")
            await asyncio.to_thread(database.set_config, "race_channel", channel.id)
            await interaction.followup.send(f"🎯 あけおめ受付チャンネルを {channel.mention} に設定しました。")

    @app_commands.command(name="soviet_sync", description="【管理者専用】指定スレッドの全ログを手動で回収し、DBを浄化する")
    async def soviet_sync(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ 管理者権限がありません。シベリアへ送ります。", ephemeral=True)
        await interaction.response.send_message("国家総動員計画発動。走査を開始する。")
        notify_channel = interaction.channel
        self.bot.loop.create_task(self.run_all_scans(notify_channel))

    @tasks.loop(time=datetime.time(hour=4, minute=0, second=0, tzinfo=JST))
    async def automated_thread_sync(self):
        if datetime.datetime.now(JST).toordinal() % 3 != 0:
            return
        notify_channel = self.bot.get_channel(RANKING_CHANNEL_ID)
        if notify_channel:
            try:
                await notify_channel.send("⏱️ **【定時連絡】深夜4時の定期スレッド自動走査を開始する。**")
            except discord.HTTPException:
                pass
        await self.run_all_scans(notify_channel)

    @automated_thread_sync.before_loop
    async def before_automated_thread_sync(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
