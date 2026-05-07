import os
import asyncio
import discord
from discord.ext import commands
from pathlib import Path

from database import init_db

# =====================
# CONFIG
# =====================

TOKEN = os.getenv("DISCORD_TOKEN")
DEV_GUILD_ID = 929545432936361984

INTENTS = discord.Intents.all()
COG_DIR = "cogs"

Path("data.db").touch(exist_ok=True)

# =====================
# BOT CLASS
# =====================

class IonicBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=INTENTS
        )

    async def setup_hook(self):
        print("⚡ Initializing database...")
        await init_db()

        print("📦 Loading cogs...")

        for file in os.listdir(COG_DIR):
            if not file.endswith(".py"):
                continue

            if file.startswith("_"):
                continue

            if file in {"utils.py", "wom_safe.py"}:
                continue

            ext = f"{COG_DIR}.{file[:-3]}"

            try:
                await self.load_extension(ext)
                print(f"✅ Loaded cog: {file}")

            except Exception as e:
                print(f"❌ Failed to load {file}: {e}")

        # =====================
        # PERSISTENT VIEWS
        # =====================

        try:
            from cogs.bingo import Bingo

            cog = self.get_cog("Bingo")

            if cog:
                self.add_view(cog.RegisterView(cog))
                self.add_view(cog.BoardView(cog))
                print("✅ Persistent views registered")

        except Exception as e:
            print(f"⚠️ View error: {e}")

        # =====================
        # SLASH COMMAND SYNC
        # =====================

        print("🔄 Syncing commands...")

        try:
            if DEV_GUILD_ID:
                guild = discord.Object(id=DEV_GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
            else:
                synced = await self.tree.sync()

            print(f"✅ Synced {len(synced)} commands")

        except Exception as e:
            print(f"❌ Sync failed: {e}")

    async def on_ready(self):
        print(f"\n✅ Logged in as {self.user}")
        print("🚀 Bot is online")

# =====================
# ENTRYPOINT
# =====================

async def main():
    if not TOKEN:
        raise ValueError("DISCORD_TOKEN environment variable is missing!")

    bot = IonicBot()

    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())