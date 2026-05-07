import discord
from discord import app_commands
from discord.ext import commands
from database import create_submission, get_member, add_points, get_points, DB_PATH
import re
import math
import json
import aiosqlite

SUBMIT_CHANNEL_ID = 1342464466616582167
STAFF_CHANNEL_ID = 1428725554995003423

STAFF_ROLE_IDS = {
    1349811146110271638,
    1342238193466085387,
    1343878526973120563,
    1342237912976326737,
}

EXCEPTIONS = {
    "pet": 50, "cm kit": 50, "tob kit": 50, "dust": 50, "toa metamorphosis": 50,
    "zulrah mutagen": 50, "any jar": 10, "parasitic egg": 30, "bludgeon piece": 4,
    "brimstone ring piece": 2, "arcane prayer scroll": 10, "justiciar armour piece": 20,
    "dt2 axe piece": 50, "lightbearer": 5, "champions scroll": 25, "hard diary": 25,
    "elite diary": 50, "combat achievement hard": 25, "combat achievement elite": 50,
    "combat achievement master": 75, "combat achievement gm": 150, "99 stat": 20,
    "maxing": 200, "firecape": 25, "inferno cape": 50, "fish sack": 40,
    "aerial fishing": 40, "helmet of the moon": 150, "quiver": 50,
}


def parse_participants(participants_str: str | None):
    if not participants_str:
        return []

    ids = set()
    for part in participants_str.split(","):
        p = part.strip()
        m = re.search(r"(\d{17,20})", p)
        if m:
            ids.add(int(m.group(1)))
        elif p.isdigit():
            ids.add(int(p))

    return list(ids)


def calculate_points(value: int, description: str):
    desc = description.lower().strip()

    if desc in EXCEPTIONS:
        return EXCEPTIONS[desc], False

    is_xp = "xp" in desc
    points = value / (50_000 if is_xp else 1_000_000)

    points = math.floor(points + 0.5)
    return points, is_xp


class SubmitCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="submit", description="Submit a drop or XP for clan points")
    async def submit(
        self,
        interaction: discord.Interaction,
        value: int,
        description: str,
        screenshot: discord.Attachment,
        participants: str | None = None,
    ):
        await interaction.response.defer(thinking=True)

        if interaction.channel.id != SUBMIT_CHANNEL_ID:
            await interaction.followup.send(
                f"Please use <#{SUBMIT_CHANNEL_ID}> to submit.",
                ephemeral=True,
            )
            return

        member = await get_member(interaction.user.id)
        if not member:
            await interaction.followup.send(
                "You must register first using `/register`.",
                ephemeral=True,
            )
            return

        parsed = parse_participants(participants)
        all_members = list({interaction.user.id, *parsed})
        participants_db = ",".join(str(x) for x in all_members)

        base_points, is_xp = calculate_points(value, description)
        per_person = min(math.ceil(base_points / len(all_members)), 200)

        sub_id = await create_submission(
            interaction.user.id,
            value,
            description,
            screenshot.url,
            is_xp=is_xp,
            is_boss=False,
            boss_name="",
            participants=participants_db,
        )

        staff_channel = self.bot.get_channel(STAFF_CHANNEL_ID)
        submit_channel = self.bot.get_channel(SUBMIT_CHANNEL_ID)

        staff_ping = " ".join(f"<@&{rid}>" for rid in STAFF_ROLE_IDS)
        participant_mentions = " ".join(f"<@{p}>" for p in all_members)

        embed = discord.Embed(
            title="📨 New Submission Pending Approval",
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="Submitter",
            value=f"{interaction.user.mention} ({interaction.user.id})",
            inline=False,
        )
        embed.add_field(name="Description", value=description, inline=False)
        embed.add_field(name="Value", value=f"{value:,}", inline=True)
        embed.add_field(name="Participants", value=participant_mentions, inline=False)
        embed.add_field(name="Screenshot", value=screenshot.url, inline=False)
        embed.set_footer(text=f"Submission ID: {sub_id}")

        # -------------------------
        # APPROVAL VIEW (UPDATED)
        # -------------------------

        class ApprovalView(discord.ui.View):
            def __init__(self, cog, sub_id, all_members, per_person, description, submit_channel):
                super().__init__(timeout=None)
                self.cog = cog
                self.sub_id = sub_id
                self.all_members = all_members
                self.per_person = per_person
                self.description = description
                self.submit_channel = submit_channel

            async def _check_staff(self, i: discord.Interaction):
                user_role_ids = {r.id for r in i.user.roles}

                allowed = (
                    i.user.guild_permissions.administrator or
                    STAFF_ROLE_IDS.intersection(user_role_ids)
                )

                if not allowed:
                    await i.response.send_message(
                        "You are not authorized to approve submissions.",
                        ephemeral=True,
                    )
                    return False

                return True

            @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
            async def approve(self, i: discord.Interaction, _):
                if not await self._check_staff(i):
                    return

                await i.response.defer(ephemeral=True)

                # NORMAL SYSTEM
                for pid in self.all_members:
                    await add_points(pid, self.per_person)

                # -------------------------
                # 🔥 BINGO HOOK
                # -------------------------
                try:
                    async with aiosqlite.connect(DB_PATH) as db:
                        row = await db.execute_fetchone(
                            "SELECT type, data FROM submissions WHERE submission_id=?",
                            (self.sub_id,)
                        )

                    if row and row[0] == "bingo":
                        data = json.loads(row[1])

                        team = data.get("team")
                        tile = data.get("tile")

                        bingo_cog = self.cog.bot.get_cog("Bingo")

                        if bingo_cog and team is not None and tile is not None:
                            await bingo_cog.process_bingo_approval({
                                "team": team,
                                "tile": tile,
                                "channel_id": i.channel.id
                            })

                except Exception as e:
                    print("Bingo error:", e)

                # MESSAGE
                if self.submit_channel:
                    await self.submit_channel.send(
                        f"✅ Submission **#{self.sub_id}** approved by {i.user.mention}. "
                        f"Each participant earned **{self.per_person} points** for `{self.description}`."
                    )

                for c in self.children:
                    c.disabled = True
                await i.message.edit(view=self)

            @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
            async def reject(self, i: discord.Interaction, _):
                if not await self._check_staff(i):
                    return

                await i.response.defer(ephemeral=True)

                if self.submit_channel:
                    await self.submit_channel.send(
                        f"❌ Submission **#{self.sub_id}** was rejected by {i.user.mention}."
                    )

                for c in self.children:
                    c.disabled = True
                await i.message.edit(view=self)

        if staff_channel:
            await staff_channel.send(
                content=staff_ping,
                embed=embed,
                view=ApprovalView(self, sub_id, all_members, per_person, description, submit_channel),
            )

        await interaction.followup.send(
            f"✅ Submission sent for staff approval. **ID: {sub_id}**"
        )

    @app_commands.command(name="points", description="Check a user's points")
    async def points(
        self,
        interaction: discord.Interaction,
        user: discord.User | None = None,
    ):
        await interaction.response.defer(thinking=True)

        target = user or interaction.user
        member = await get_member(target.id)

        if not member:
            await interaction.followup.send(
                f"{target.mention} is not registered.",
                ephemeral=True,
            )
            return

        pts = await get_points(target.id)

        await interaction.followup.send(
            f"🏆 **{target.display_name}** has **{pts} points**."
        )


async def setup(bot):
    await bot.add_cog(SubmitCog(bot))