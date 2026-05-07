# cogs/pet_hunt.py

import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiosqlite
import asyncio
from datetime import datetime, timezone, timedelta
import random

from database import DB_PATH, add_points

PET_CHANNEL_ID = 1432885524716327114
STAFF_CHANNEL_ID = 1428725554995003423
ENTRY_FEE = 0

OSRS_PETS = [
    "Baby mole", "Beaver", "Heron", "Rock golem", "Pet Snakling",
    "Vorki", "Tzrek-Jad", "Phoenix", "Ikkle Hydra", "Abyssal orphan",
    "Giant squirrel", "Tangleroot", "Rocky", "Rift Guardian",
    "Olmlet", "Kalphite Princess", "Lil’ Zik", "Bloodhound", "Skotos"
]

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def current_week_start() -> str:
    now = datetime.now(timezone.utc)
    days = (now.weekday() + 1) % 7
    return (now - timedelta(days=days)).date().isoformat()

async def ensure_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS pet_hunts (
            week_start TEXT PRIMARY KEY,
            pet_name TEXT,
            active INTEGER,
            winner_id INTEGER,
            prize_pool INTEGER
        );

        CREATE TABLE IF NOT EXISTS pet_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            week_start TEXT,
            approved INTEGER,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS pet_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            week_start TEXT,
            pet_name TEXT,
            screenshot TEXT,
            approved INTEGER,
            created_at TEXT
        );
        """)
        await db.commit()

# --------------------------------------------------
# Cog
# --------------------------------------------------

class PetHuntCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.weekly_task.start()

    def cog_unload(self):
        self.weekly_task.cancel()

    # -------------------- Weekly loop --------------------

    @tasks.loop(hours=1)
    async def weekly_task(self):
        await self.bot.wait_until_ready()
        await ensure_tables()

        week = current_week_start()

        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT 1 FROM pet_hunts WHERE week_start = ?",
                (week,)
            )
            if await cur.fetchone():
                return

            pet = random.choice(OSRS_PETS)
            await db.execute(
                "INSERT INTO pet_hunts VALUES (?, ?, 1, NULL, 0)",
                (week, pet)
            )
            await db.commit()

        channel = self.bot.get_channel(PET_CHANNEL_ID)
        if channel:
            await channel.send(
                f"🎯 **New Pet Hunt Started!**\n"
                f"Pet: **{pet}**\n"
                f"Use `/petentry` to apply."
            )

    # -------------------- Commands --------------------

    @app_commands.command(name="petentry")
    async def petentry(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await ensure_tables()

        week = current_week_start()

        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT active FROM pet_hunts WHERE week_start = ?",
                (week,)
            )
            row = await cur.fetchone()
            if not row or row[0] == 0:
                await interaction.followup.send("No active Pet Hunt.")
                return

            await db.execute(
                "INSERT INTO pet_entries VALUES (NULL, ?, ?, 0, ?)",
                (interaction.user.id, week, datetime.now(timezone.utc).isoformat())
            )
            await db.commit()

        staff = self.bot.get_channel(STAFF_CHANNEL_ID)
        if staff:
            await staff.send(
                f"📝 Pet Hunt entry pending approval:\n"
                f"User: {interaction.user.mention}\n"
                f"Week: {week}"
            )

        await interaction.followup.send("Your entry was sent for staff approval.")

    @app_commands.command(name="submitpet")
    async def submitpet(
        self,
        interaction: discord.Interaction,
        pet_name: str,
        screenshot: discord.Attachment
    ):
        await interaction.response.defer(ephemeral=True)
        await ensure_tables()

        week = current_week_start()

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO pet_submissions VALUES (NULL, ?, ?, ?, ?, 0, ?)",
                (
                    interaction.user.id,
                    week,
                    pet_name,
                    screenshot.url,
                    datetime.now(timezone.utc).isoformat()
                )
            )
            await db.commit()

        staff = self.bot.get_channel(STAFF_CHANNEL_ID)
        if staff:
            await staff.send(
                f"📸 Pet submission pending:\n"
                f"User: {interaction.user.mention}\n"
                f"Pet: {pet_name}\n"
                f"{screenshot.url}"
            )

        await interaction.followup.send("Submission sent for approval.")

    @app_commands.command(name="petstatus")
    async def petstatus(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await ensure_tables()

        week = current_week_start()

        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "SELECT pet_name, active, prize_pool, winner_id FROM pet_hunts WHERE week_start = ?",
                (week,)
            )
            row = await cur.fetchone()

        if not row:
            await interaction.followup.send("No Pet Hunt found.")
            return

        pet, active, pool, winner = row
        msg = (
            f"🐾 **Pet Hunt Status**\n"
            f"Pet: **{pet}**\n"
            f"Status: {'Active' if active else 'Finished'}\n"
            f"Prize Pool: {pool:,} GP"
        )
        if winner:
            msg += f"\nWinner: <@{winner}>"

        await interaction.followup.send(msg)

# --------------------------------------------------

async def setup(bot):
    await bot.add_cog(PetHuntCog(bot))
