import discord
from discord import app_commands
from discord.ext import commands

from database import create_submission, get_member, update_member_username

STAFF_CHANNEL_ID = 1428725554995003423

STAFF_ROLE_IDS = {
    1349811146110271638,
    1342238193466085387,
    1343878526973120563,
    1342237912976326737,
}


class ChangeUsernameCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------
    # 🔄 Change Username Request
    # ---------------------------

    @app_commands.command(
        name="change_username",
        description="Request an OSRS username change (staff approval required)",
    )
    async def change_username(
        self,
        interaction: discord.Interaction,
        new_name: str,
        screenshot: discord.Attachment,
    ):
        await interaction.response.defer(thinking=True)

        if not screenshot:
            await interaction.followup.send(
                "❌ You must attach a screenshot.",
                ephemeral=True,
            )
            return

        member = await get_member(interaction.user.id)
        if not member:
            await interaction.followup.send(
                "❌ You must register first using `/register`.",
                ephemeral=True,
            )
            return

        sub_id = await create_submission(
            interaction.user.id,
            value=0,
            description=f"Username change → {new_name}",
            screenshot=screenshot.url,
            is_xp=False,
            is_boss=False,
            boss_name="",
            participants="",
        )

        staff_channel = self.bot.get_channel(STAFF_CHANNEL_ID)
        staff_ping = " ".join(f"<@&{rid}>" for rid in STAFF_ROLE_IDS)

        embed = discord.Embed(
            title="🔄 Username Change Request",
            description=(
                f"{interaction.user.mention} requests to change "
                f"their OSRS name to **`{new_name}`**"
            ),
            color=discord.Color.blue(),
        )
        embed.set_image(url=screenshot.url)
        embed.set_footer(text=f"Submission ID: {sub_id}")

        # ---------------------------
        # Approval View
        # ---------------------------

        class ApprovalView(discord.ui.View):
            def __init__(self, user_id: int, new_name: str):
                super().__init__(timeout=None)
                self.user_id = user_id
                self.new_name = new_name
                self.locked = False

            def _is_staff(self, user: discord.Member) -> bool:
                role_ids = {r.id for r in user.roles}
                return (
                    user.guild_permissions.administrator or
                    STAFF_ROLE_IDS.intersection(role_ids)
                )

            async def _lock(self):
                self.locked = True
                for c in self.children:
                    c.disabled = True

            @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
            async def approve(self, i: discord.Interaction, _):
                if self.locked:
                    return

                if not self._is_staff(i.user):
                    await i.response.send_message(
                        "❌ You are not authorized to approve this.",
                        ephemeral=True,
                    )
                    return

                await i.response.defer(ephemeral=True)

                success = await update_member_username(
                    self.user_id,
                    self.new_name
                )

                nick_changed = False
                guild = i.guild
                member = guild.get_member(self.user_id) if guild else None

                if member:
                    try:
                        await member.edit(nick=self.new_name)
                        nick_changed = True
                    except discord.Forbidden:
                        pass

                if success:
                    msg = (
                        f"✅ Username updated to `{self.new_name}`"
                        + (" (DB + nickname)." if nick_changed else " (DB only).")
                    )
                else:
                    msg = "❌ Failed to update username in database."

                await i.followup.send(msg, ephemeral=False)

                await self._lock()
                await i.message.edit(view=self)

            @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
            async def reject(self, i: discord.Interaction, _):
                if self.locked:
                    return

                if not self._is_staff(i.user):
                    await i.response.send_message(
                        "❌ You are not authorized to reject this.",
                        ephemeral=True,
                    )
                    return

                await i.response.defer(ephemeral=True)

                await i.followup.send(
                    "❌ Username change request rejected.",
                    ephemeral=False,
                )

                await self._lock()
                await i.message.edit(view=self)

        if staff_channel:
            await staff_channel.send(
                content=staff_ping,
                embed=embed,
                view=ApprovalView(interaction.user.id, new_name),
            )

        await interaction.followup.send(
            f"✅ Username change request submitted for approval. (ID: {sub_id})",
            ephemeral=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ChangeUsernameCog(bot))
