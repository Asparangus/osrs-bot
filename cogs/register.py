import discord
from discord.ext import commands
from discord import app_commands

from database import (
    register_member,
    get_member,
    get_all_members,
    add_points,
    remove_points,
    remove_member,
)

# ---------------------------
# 👮 Staff Role IDs (your same IDs)
# ---------------------------
STAFF_ROLE_IDS = {
    1342238193466085387,
    1343878526973120563,
    1342237912976326737,
    1349811146110271638,
}


def is_staff(member: discord.Member) -> bool:
    role_ids = {r.id for r in member.roles}
    return (
        member.guild_permissions.administrator or
        STAFF_ROLE_IDS.intersection(role_ids)
    )


class RegisterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------
    # 📝 Register
    # ---------------------------
    @app_commands.command(name="register", description="Register your OSRS name")
    async def register(self, interaction: discord.Interaction, osrs_name: str):
        await interaction.response.defer(thinking=True, ephemeral=True)

        existing = await get_member(interaction.user.id)
        if existing:
            await interaction.followup.send(
                f"⚠️ You are already registered as `{existing[2]}`.",
                ephemeral=True,
            )
            return

        await register_member(
            interaction.user.id,
            str(interaction.user),
            osrs_name,
        )

        await interaction.followup.send(
            f"✅ Registered as `{osrs_name}`!",
            ephemeral=False,
        )

    # ---------------------------
    # ❌ Remove Member (Staff/Admin)
    # ---------------------------
    @app_commands.command(
        name="remove",
        description="Remove a member from the clan database (staff only)",
    )
    async def remove(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)

        if not is_staff(interaction.user):
            await interaction.followup.send(
                "❌ Staff permission required.",
                ephemeral=True,
            )
            return

        existing = await get_member(member.id)
        if not existing:
            await interaction.followup.send(
                f"⚠️ {member.display_name} is not registered.",
                ephemeral=True,
            )
            return

        await remove_member(member.id)

        await interaction.followup.send(
            f"✅ Removed **{member.display_name}** from database.",
            ephemeral=False,
        )

    # ---------------------------
    # ➕ Add Points (Admin)
    # ---------------------------
    @app_commands.command(
        name="addpoints",
        description="Add points to a member (admin only)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def addpoints(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        points: int,
    ):
        await interaction.response.defer(thinking=True)

        if points <= 0:
            await interaction.followup.send("❌ Points must be positive.")
            return

        await add_points(member.id, points)

        await interaction.followup.send(
            f"✅ Added **{points}** points to **{member.display_name}**."
        )

    # ---------------------------
    # ➖ Remove Points (Admin)
    # ---------------------------
    @app_commands.command(
        name="removepoints",
        description="Remove points from a member (admin only)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def removepoints(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        points: int,
    ):
        await interaction.response.defer(thinking=True)

        if points <= 0:
            await interaction.followup.send("❌ Points must be positive.")
            return

        await remove_points(member.id, points)

        await interaction.followup.send(
            f"⚠️ Removed **{points}** points from **{member.display_name}**."
        )

    # ---------------------------
    # 📋 Members List (Admin)
    # ---------------------------
    @app_commands.command(
        name="members",
        description="Show all registered members (admin only)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def members(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        members = await get_all_members()
        if not members:
            await interaction.followup.send("📭 No members registered.")
            return

        lines = [
            f"**{m[2]}** — {m[3]} pts ({m[1]})"
            for m in members
        ]

        text = "\n".join(lines)

        for i in range(0, len(text), 4000):
            embed = discord.Embed(
                title="🧾 Registered Members",
                description=text[i:i+4000],
                color=discord.Color.blurple(),
            )
            await interaction.followup.send(embed=embed)

    # ---------------------------
    # 🏆 Leaderboard
    # ---------------------------
    @app_commands.command(
        name="leaderboard",
        description="Show points leaderboard",
    )
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        members = await get_all_members()
        if not members:
            await interaction.followup.send("📭 No members found.")
            return

        sorted_members = sorted(members, key=lambda x: x[3], reverse=True)

        for page in range(0, len(sorted_members), 10):
            chunk = sorted_members[page:page+10]

            desc = "\n".join(
                f"**{page+i+1}. {m[2]}** — {m[3]} pts ({m[1]})"
                for i, m in enumerate(chunk)
            )

            embed = discord.Embed(
                title=f"🔥 Leaderboard — Page {page//10 + 1}",
                description=desc,
                color=discord.Color.gold(),
            )

            await interaction.followup.send(embed=embed)

    # ---------------------------
    # 🚪 Auto-remove on Leave
    # ---------------------------
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        existing = await get_member(member.id)
        if not existing:
            return

        await remove_member(member.id)
        print(f"[AUTO-REMOVE] {member} removed from database")


async def setup(bot: commands.Bot):
    await bot.add_cog(RegisterCog(bot))
