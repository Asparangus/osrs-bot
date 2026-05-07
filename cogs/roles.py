import asyncio
import logging
import discord
from discord.ext import commands, tasks
from discord import app_commands

from database import get_all_members, get_member_points

# ---------------------------
# 🔢 Role thresholds (HIGH → LOW)
# ---------------------------
ROLE_THRESHOLDS = [
    (19000, "Zarosian 😈"),
    (16500, "Saradominist ˚ʚ♡ɞ˚"),
    (14000, "Zamorakian 👹"),
    (11500, "Guthixian 💚"),
    (9000,  "Soul 🪽"),
    (7500,  "Firestater ☄️"),
    (6000,  "Ignitor 🚬"),
    (4500,  "Burnt 🥵"),
    (3000,  "Artisan✎ ⋆⑅˚₊"),
    (2000,  "Specialist ☣️"),
    (1000,  "Legacy 💯"),
    (500,   "Firemaker 🐦‍🔥"),
    (250,   "Pyromancer 𖦹"),
    (100,   "Prodigy (•_•)"),
    (0,     "Fire 🔥"),
]

# ---------------------------
# 📜 Logger
# ---------------------------
log = logging.getLogger("roles")
log.setLevel(logging.INFO)


class RolesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.role_queue: asyncio.Queue[tuple[int, int]] = asyncio.Queue()
        self.worker_task: asyncio.Task | None = None

    # ---------------------------
    # ⚙️ Lifecycle
    # ---------------------------
    async def cog_load(self):
        self.worker_task = asyncio.create_task(self.role_worker())
        self.bulk_loop.start()
        log.info("RolesCog loaded.")

    async def cog_unload(self):
        self.bulk_loop.cancel()
        if self.worker_task:
            self.worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.worker_task

    # ---------------------------
    # 🧵 Worker
    # ---------------------------
    async def role_worker(self):
        await self.bot.wait_until_ready()

        while True:
            try:
                guild_id, member_id = await self.role_queue.get()

                guild = self.bot.get_guild(guild_id)
                if not guild:
                    continue

                member = guild.get_member(member_id)
                if not member:
                    continue

                points = await get_member_points(member_id)
                await self._apply_role(member, points)

            except asyncio.CancelledError:
                break

            except Exception:
                log.exception(f"Role update failed for member {member_id}")

            finally:
                await asyncio.sleep(0.4)
                self.role_queue.task_done()

    # ---------------------------
    # 🧠 Role Logic
    # ---------------------------
    async def _apply_role(self, member: discord.Member, points: int):
        guild = member.guild

        target_role_name = next(
            (name for threshold, name in ROLE_THRESHOLDS if points >= threshold),
            None,
        )
        if not target_role_name:
            return

        target_role = discord.utils.get(guild.roles, name=target_role_name)
        if not target_role:
            target_role = await guild.create_role(
                name=target_role_name,
                reason="Auto-created by role system",
            )
            log.info(f"Created role: {target_role_name}")

        remove_roles = [
            r for _, rn in ROLE_THRESHOLDS
            if (r := discord.utils.get(guild.roles, name=rn))
            and r in member.roles
            and r != target_role
        ]

        if remove_roles:
            for r in remove_roles:
                await member.remove_roles(r, reason="Role threshold update")
                await asyncio.sleep(0.2)

        if target_role not in member.roles:
            await member.add_roles(target_role, reason="Role threshold update")
            log.info(
                f"Assigned {target_role.name} to {member.display_name} ({member.id})"
            )

    # ---------------------------
    # ➕ Queue API
    # ---------------------------
    async def enqueue_member(self, guild_id: int, member_id: int):
        await self.role_queue.put((guild_id, member_id))

    async def enqueue_bulk(self, guild: discord.Guild):
        members = await get_all_members()
        for discord_id, *_ in members:
            await self.role_queue.put((guild.id, discord_id))

    # ---------------------------
    # 🕒 Scheduled Bulk Update
    # ---------------------------
    @tasks.loop(hours=6)
    async def bulk_loop(self):
        if not self.bot.guilds:
            return

        guild = self.bot.guilds[0]
        log.info("Scheduled bulk role update started")
        await self.enqueue_bulk(guild)

    # ---------------------------
    # 🔧 Admin Command
    # ---------------------------
    @app_commands.command(
        name="updateroles",
        description="Queue a full role update (admin only)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def updateroles(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True)

        await self.enqueue_bulk(interaction.guild)

        await interaction.followup.send(
            "✅ Role update queued and processing in background.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(RolesCog(bot))
