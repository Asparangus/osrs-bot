import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone
import aiosqlite
import asyncio

from database import (
    DB_PATH,
    current_week_start_utc,
)

ADMIN_IDS = {1342238193466085387, 1343878526973120563}
ROLE_ID = 9876543210        # Weekly MVP role
CHANNEL_ID = 1234567890     # Announcement channel


class WeeklyTasks(commands.Cog):
    """Weekly MVP rotation and announcement."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cog_unload(self):
        if self.run_weekly.is_running():
            self.run_weekly.cancel()

    # -------------------------
    # Core logic
    # -------------------------
    async def rotate_role(self) -> str | None:
        week = current_week_start_utc()

        try:
            async with aiosqlite.connect(DB_PATH) as db:
                cur = await db.execute(
                    """
                    SELECT discord_id, xp_gained
                    FROM weekly_tracking
                    WHERE week_start = ?
                    ORDER BY xp_gained DESC
                    LIMIT 1
                    """,
                    (week,),
                )
                row = await cur.fetchone()

                if not row:
                    return None

                winner_id = row[0]

                await db.execute(
                    """
                    INSERT OR REPLACE INTO weekly_role_state
                    (week_start, discord_id, role_id, assigned_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        week,
                        winner_id,
                        ROLE_ID,
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                await db.commit()

        except Exception as db_error:
            print(f"[WeeklyTasks] DB error: {db_error}")
            return None

        # Resolve guild safely
        guild = self.bot.get_guild(self.bot.guilds[0].id) if self.bot.guilds else None
        if not guild:
            print("[WeeklyTasks] Guild not available.")
            return None

        role = guild.get_role(ROLE_ID)
        if not role:
            print("[WeeklyTasks] MVP role not found.")
            return None

        # Remove role from previous holders
        for member in role.members:
            try:
                await member.remove_roles(role, reason="Weekly MVP rotation")
            except Exception:
                pass

        # Assign role to winner
        member = guild.get_member(winner_id)
        if not member:
            print("[WeeklyTasks] Winner not found in guild.")
            return None

        try:
            await member.add_roles(role, reason="Weekly MVP winner")
        except Exception as role_error:
            print(f"[WeeklyTasks] Role assign failed: {role_error}")
            return None

        return member.display_name

    # -------------------------
    # Weekly loop
    # -------------------------
    @tasks.loop(hours=168)
    async def run_weekly(self):
        channel = self.bot.get_channel(CHANNEL_ID)
        if not channel:
            return

        winner = await self.rotate_role()
        if winner:
            await channel.send(f"🏆 **Weekly MVP:** {winner}")

    @run_weekly.before_loop
    async def before_run_weekly(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)
        print("Weekly MVP task starting...")

    # -------------------------
    # Startup hook
    # -------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.run_weekly.is_running():
            self.run_weekly.start()

    # -------------------------
    # Manual override
    # -------------------------
    @commands.command(name="force_weekly")
    async def force_weekly(self, ctx: commands.Context):
        if ctx.author.id not in ADMIN_IDS:
            return

        winner = await self.rotate_role()
        if winner:
            await ctx.send(f"🏆 Forced Weekly MVP: {winner}")


async def setup(bot: commands.Bot):
    await bot.add_cog(WeeklyTasks(bot))
