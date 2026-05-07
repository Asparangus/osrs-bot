from discord.ext import commands, tasks
from datetime import datetime, timezone
import asyncio

from database import get_all_members, add_weekly_xp, add_points
from cogs.wom_safe import fetch_wom_player_safe  # ✅ FIXED IMPORT


class TasksDaily(commands.Cog):
    """Daily tasks for updating XP, points, and logging activity."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_unload(self):
        if self.daily_update.is_running():
            self.daily_update.cancel()

    # -------------------------
    # Daily loop task
    # -------------------------
    @tasks.loop(hours=24)
    async def daily_update(self):
        try:
            members = await get_all_members()
        except Exception as e:
            print(f"Failed to fetch members from DB: {e}")
            return

        for discord_id, discord_name, osrs_name, points in members:
            try:
                data = await fetch_wom_player_safe(osrs_name)
                if not data:
                    continue

                current_xp = data.get("totalXp", 0)

                await add_weekly_xp(discord_id, current_xp)
                await add_points(discord_id, 10)

            except Exception as member_error:
                print(
                    f"Daily task failed for {discord_name} "
                    f"({discord_id}): {member_error}"
                )
                continue

        print(f"[{datetime.now(timezone.utc).isoformat()}] Daily update completed.")

    # -------------------------
    # Loop bootstrap
    # -------------------------
    @daily_update.before_loop
    async def before_daily_update(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)
        print("Daily update loop starting...")

    # -------------------------
    # Cog ready hook
    # -------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.daily_update.is_running():
            self.daily_update.start()


# -------------------------
# Cog setup
# -------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(TasksDaily(bot))
