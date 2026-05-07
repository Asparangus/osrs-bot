import os
import asyncio
import traceback
import discord

from dotenv import load_dotenv
from discord.ext import commands
from pathlib import Path

from database import init_db

# =========================
# LOAD ENVIRONMENT VARIABLES
# =========================

load_dotenv()

# =========================
# CONFIG
# =========================

TOKEN = os.getenv("DISCORD_TOKEN")
DEV_GUILD_ID = 929545432936361984

COG_DIR = "cogs"

INTENTS = discord.Intents.all()

# Ensure database exists
Path("data.db").touch(exist_ok=True)

# =========================
# BOT CLASS
# =========================

class IonicBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=INTENTS,
            help_command=None
        )

    # =========================
    # STARTUP
    # =========================

    async def setup_hook(self):
        print("\n⚡ Starting Ionic Order...")
        print("⚡ Initializing database...")

        await init_db()

        print("📦 Loading cogs...")

        await self.load_all_cogs()

        print("🧠 Registering persistent views...")

        await self.register_persistent_views()

        print("🔄 Syncing slash commands...")

        await self.sync_commands()

    # =========================
    # LOAD ALL COGS
    # =========================

    async def load_all_cogs(self):
        for file in os.listdir(COG_DIR):

            if not file.endswith(".py"):
                continue

            if file.startswith("_"):
                continue

            if file in {"utils.py", "wom_safe.py"}:
                continue

            extension = f"{COG_DIR}.{file[:-3]}"

            try:
                await self.load_extension(extension)
                print(f"✅ Loaded cog: {file}")

            except Exception as e:
                print(f"❌ Failed to load {file}")

                traceback.print_exception(
                    type(e),
                    e,
                    e.__traceback__
                )

    # =========================
    # PERSISTENT VIEWS
    # =========================

    async def register_persistent_views(self):
        try:
            from cogs.bingo import Bingo

            cog = self.get_cog("Bingo")

            if cog:
                self.add_view(cog.RegisterView(cog))
                self.add_view(cog.BoardView(cog))

                print("✅ Persistent views registered")

        except Exception as e:
            print("⚠️ Persistent view registration failed")

            traceback.print_exception(
                type(e),
                e,
                e.__traceback__
            )

    # =========================
    # SLASH COMMAND SYNC
    # =========================

    async def sync_commands(self):
        try:
            if DEV_GUILD_ID:
                guild = discord.Object(id=DEV_GUILD_ID)

                self.tree.copy_global_to(guild=guild)

                synced = await self.tree.sync(guild=guild)

            else:
                synced = await self.tree.sync()

            print(f"✅ Synced {len(synced)} commands")

        except Exception as e:
            print("❌ Slash sync failed")

            traceback.print_exception(
                type(e),
                e,
                e.__traceback__
            )

    # =========================
    # READY EVENT
    # =========================

    async def on_ready(self):
        print("\n============================")
        print(f"✅ Logged in as: {self.user}")
        print(f"🆔 Bot ID: {self.user.id}")
        print("🚀 Ionic Order is online")
        print("============================\n")

    # =========================
    # COMMAND ERROR HANDLER
    # =========================

    async def on_command_error(self, ctx, error):
        print("\n❌ Command Error Detected")

        traceback.print_exception(
            type(error),
            error,
            error.__traceback__
        )

# =========================
# MAIN LOOP
# =========================

async def main():
    if not TOKEN:
        raise ValueError(
            "DISCORD_TOKEN environment variable is missing!"
        )

    while True:
        try:
            bot = IonicBot()

            async with bot:
                await bot.start(TOKEN)

        except Exception as e:
            print("\n🚨 Bot crashed")

            traceback.print_exception(
                type(e),
                e,
                e.__traceback__
            )

            print("🔄 Restarting in 5 seconds...\n")

            await asyncio.sleep(5)

# =========================
# ENTRYPOINT
# =========================

if __name__ == "__main__":
    asyncio.run(main())