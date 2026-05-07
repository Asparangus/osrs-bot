import discord
from discord.ext import commands
import random, asyncio, requests, time
import aiosqlite
from database import DB_PATH
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import imagehash

TEAM_SIZE = 10
BOARD_CHANNEL_ID = 1487120877375062026
REVIEW_CHANNEL_ID = 1486866545710727199

STAFF_ROLES = {
    1342238193466085387,
    1343878526973120563,
    1342237912976326737,
    1349811146110271638
}

TASK_POOL = [
    "TwinFlame Staff & scrolls","RuneCraft 500k XP","Agility 500k XP",
    "Barbarian Assault","Kill 1 Corpreal Beast",
    "Sailing 1M XP","Nightmare Unique",
    "Kill 1 sarachins","Kill 1 Jad","Kill 1 Zulrah","Kill 1 Tempeross",
    "Get 1 Kalphaite Queen Head","Get 1 Enhanced weapon seed from Odium",
    "Dessert Treasure 2 Ring","Get 1 Scurrius Spines","Get 1 Zenyte shard",
    "Any jar","Get 1 Barrows Chest","Get 1 Pet","Get 1M loot From PK",
    "Get 1 God Wars Dungeon Unique","Get 1 Ranger Boots","Get 1 Doom Unique",
    "Get 3 Raid purples","Create Wilderness Shield"
]

# ================= HELPERS =================
def is_staff(member):
    return any(r.id in STAFF_ROLES for r in member.roles)

def generate_board():
    return [random.choice(TASK_POOL) for _ in range(25)]

def render_board(tasks, done, path):
    TILE = 150
    img = Image.new("RGB",(TILE*5,TILE*5),(30,25,15))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except:
        font = ImageFont.load_default()

    for i,task in enumerate(tasks):
        x,y=(i%5)*TILE,(i//5)*TILE
        fill = (60,140,60) if i in done else (110,90,60)

        draw.rectangle([x+5,y+5,x+TILE-5,y+TILE-5],fill=fill)
        draw.text((x+10,y+60),task[:18],fill=(255,255,0),font=font)

        if i in done:
            draw.text((x+60,y+20),"✔",fill="white",font=font)

    img.save(path)

# ================= COG =================
class Bingo(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.setup_message_id = None
        self.setup_channel_id = None
        self.leaderboard_message_id = None

    # ================= SETUP =================
    @commands.hybrid_command(name="bingo_setup")
    async def setup_cmd(self, ctx):
        embed = await self.build_setup_embed()
        msg = await ctx.send(embed=embed, view=self.RegisterView(self))

        self.setup_message_id = msg.id
        self.setup_channel_id = ctx.channel.id

    async def build_setup_embed(self):
        async with aiosqlite.connect(DB_PATH) as db:
            players = await (await db.execute(
                "SELECT discord_id FROM bingo_teams"
            )).fetchall()

        names = [f"<@{p[0]}>" for p in players]

        return discord.Embed(
            title="🎯 OSRS Bingo",
            description=f"Players ({len(names)}):\n" + ("\n".join(names) or "None")
        )

    async def update_setup_message(self):
        if not self.setup_message_id or not self.setup_channel_id:
            return

        channel = self.bot.get_channel(self.setup_channel_id)

        try:
            msg = await channel.fetch_message(self.setup_message_id)
            await msg.edit(embed=await self.build_setup_embed(), view=self.RegisterView(self))
        except Exception as e:
            print(f"[SETUP UPDATE ERROR] {e}")

    # ================= RESET =================
    @commands.hybrid_command(name="bingo_reset")
    async def reset(self, ctx):
        if not is_staff(ctx.author):
            return await ctx.send("❌ Staff only")

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM bingo_teams")
            await db.execute("DELETE FROM bingo_boards")
            await db.execute("DELETE FROM image_hashes")
            await db.commit()

        self.setup_message_id = None
        self.leaderboard_message_id = None

        await ctx.send("🧹 Bingo fully reset")

    # ================= START =================
    @commands.hybrid_command(name="bingo_start")
    async def start(self, ctx):

        async with aiosqlite.connect(DB_PATH) as db:
            players = [r[0] for r in await (await db.execute(
                "SELECT discord_id FROM bingo_teams"
            )).fetchall()]

        if not players:
            return await ctx.send("❌ No players")

        random.shuffle(players)
        teams = [players[i:i+TEAM_SIZE] for i in range(0,len(players),TEAM_SIZE)]

        preview = ""
        for i,t in enumerate(teams):
            preview += f"\n👑 Team {i+1}\n"
            preview += "\n".join([f"<@{p}>" for p in t]) + "\n"

        await ctx.send(embed=discord.Embed(title="👑 Team Preview",description=preview))

        for t_id, team in enumerate(teams):
            tasks = generate_board()

            async with aiosqlite.connect(DB_PATH) as db:
                for p in team:
                    await db.execute("UPDATE bingo_teams SET team_id=? WHERE discord_id=?", (t_id,p))

                for i,task in enumerate(tasks):
                    await db.execute("""
                        INSERT INTO bingo_boards 
                        (team_id,tile,task,completed,completed_by)
                        VALUES (?,?,?,?,?)
                    """,(t_id,i,task,0,0))

                await db.commit()

            await self.post_board(t_id)

        await self.update_leaderboard()
        await ctx.send("✅ Bingo started!")

    # ================= BOARD =================
    async def post_board(self, team):
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute(
                "SELECT tile,task,completed FROM bingo_boards WHERE team_id=? ORDER BY tile",
                (team,)
            )).fetchall()

        tasks = [r[1] for r in rows]
        done = [r[0] for r in rows if r[2] == 1]

        path = f"board_{team}_{int(time.time())}.png"
        await asyncio.to_thread(render_board, tasks, done, path)

        channel = self.bot.get_channel(BOARD_CHANNEL_ID)
        await channel.send(
            f"🎮 Team {team+1}",
            file=discord.File(path),
            view=self.BoardView(self)
        )

    async def update_board(self, team):
        await self.post_board(team)

    # ================= LEADERBOARD =================
    async def update_leaderboard(self):
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await (await db.execute("""
                SELECT team_id, tile, completed_by
                FROM bingo_boards WHERE completed=1
            """)).fetchall()

        text = ""
        for t, tile, user in rows:
            text += f"Team {t+1} • Tile {tile} → <@{user}>\n"

        channel = self.bot.get_channel(BOARD_CHANNEL_ID)

        if self.leaderboard_message_id:
            try:
                msg = await channel.fetch_message(self.leaderboard_message_id)
                await msg.edit(embed=discord.Embed(title="📊 Leaderboard",description=text))
            except:
                self.leaderboard_message_id = None

        if not self.leaderboard_message_id:
            msg = await channel.send(embed=discord.Embed(title="📊 Leaderboard",description=text))
            self.leaderboard_message_id = msg.id

    # ================= REGISTER =================
    class RegisterView(discord.ui.View):
        def __init__(self,cog):
            super().__init__(timeout=None)
            self.cog=cog

        @discord.ui.button(label="Join",style=discord.ButtonStyle.green,custom_id="bingo_join")
        async def join(self,interaction,button):
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO bingo_teams (team_id, discord_id)
                    VALUES (?, ?)
                    ON CONFLICT(discord_id) DO NOTHING
                """, (-1,interaction.user.id))
                await db.commit()

            await interaction.response.send_message("Joined!",ephemeral=True)
            await self.cog.update_setup_message()

        @discord.ui.button(label="Leave",style=discord.ButtonStyle.red,custom_id="bingo_leave")
        async def leave(self,interaction,button):
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM bingo_teams WHERE discord_id=?", (interaction.user.id,))
                await db.commit()

            await interaction.response.send_message("Left!",ephemeral=True)
            await self.cog.update_setup_message()

    # ================= BOARD VIEW =================
    class BoardView(discord.ui.View):
        def __init__(self,cog):
            super().__init__(timeout=None)
            self.cog=cog

        @discord.ui.button(label="Submit Tile",style=discord.ButtonStyle.green,custom_id="bingo_submit")
        async def submit(self,interaction,button):

            async with aiosqlite.connect(DB_PATH) as db:
                team = await (await db.execute(
                    "SELECT team_id FROM bingo_teams WHERE discord_id=?",
                    (interaction.user.id,)
                )).fetchone()

            if not team:
                return await interaction.response.send_message("❌ Not in team",ephemeral=True)

            team = team[0]

            async with aiosqlite.connect(DB_PATH) as db:
                tiles = await (await db.execute("""
                    SELECT tile,task FROM bingo_boards
                    WHERE team_id=? AND completed=0
                """,(team,))).fetchall()

            view = Bingo.TileSelect(self.cog, tiles, team)
            await interaction.response.send_message("Select tile:", view=view, ephemeral=True)

    class TileSelect(discord.ui.View):
        def __init__(self,cog,tiles,team):
            super().__init__()
            self.add_item(Bingo.TileDropdown(cog,tiles,team))

    class TileDropdown(discord.ui.Select):
        def __init__(self,cog,tiles,team):
            options=[discord.SelectOption(label=f"{t[0]}: {t[1]}",value=str(t[0])) for t in tiles]
            super().__init__(options=options)
            self.cog=cog
            self.team=team

        async def callback(self,interaction):
            tile=int(self.values[0])
            user=interaction.user

            await interaction.response.send_message("📸 Upload screenshot",ephemeral=True)

            def check(m):
                return m.author.id==user.id and m.attachments

            msg=await self.cog.bot.wait_for("message",check=check,timeout=120)
            url=msg.attachments[0].url

            img_bytes = requests.get(url).content
            hash_val=str(imagehash.phash(Image.open(BytesIO(img_bytes))))

            async with aiosqlite.connect(DB_PATH) as db:
                if await (await db.execute("SELECT 1 FROM image_hashes WHERE hash=?",(hash_val,))).fetchone():
                    return await msg.reply("Duplicate image")

                await db.execute("INSERT INTO image_hashes VALUES (?)",(hash_val,))
                await db.commit()

            review=self.cog.bot.get_channel(REVIEW_CHANNEL_ID)

            embed = discord.Embed(
                title="📸 Bingo Submission",
                description=f"{user.mention} submitted Tile {tile}"
            )
            embed.set_image(url=url)

            staff_ping = " ".join([f"<@&{r}>" for r in STAFF_ROLES])

            await review.send(
                content=staff_ping,
                embed=embed,
                view=Bingo.ReviewView(self.cog,user.id,tile)
            )

    # ================= REVIEW =================
    class ReviewView(discord.ui.View):
        def __init__(self,cog,user,tile):
            super().__init__(timeout=300)
            self.cog=cog
            self.user=user
            self.tile=tile

        def disable_all(self):
            for c in self.children:
                c.disabled=True

        @discord.ui.button(label="Approve",style=discord.ButtonStyle.green,custom_id="approve")
        async def approve(self,interaction,button):
            if not is_staff(interaction.user):
                return await interaction.response.send_message("No perm",ephemeral=True)

            async with aiosqlite.connect(DB_PATH) as db:
                team=(await (await db.execute(
                    "SELECT team_id FROM bingo_teams WHERE discord_id=?",
                    (self.user,)
                )).fetchone())[0]

                await db.execute("""
                    UPDATE bingo_boards
                    SET completed=1, completed_by=?
                    WHERE team_id=? AND tile=? AND completed=0
                """,(self.user,team,self.tile))
                await db.commit()

            self.disable_all()
            await interaction.message.edit(view=self)

            board_channel = self.cog.bot.get_channel(BOARD_CHANNEL_ID)
            await board_channel.send(f"✅ Tile {self.tile} approved for <@{self.user}>")

            await interaction.response.send_message("Approved",ephemeral=True)

            await self.cog.update_board(team)
            await self.cog.update_leaderboard()

        @discord.ui.button(label="Reject",style=discord.ButtonStyle.red,custom_id="reject")
        async def reject(self,interaction,button):
            if not is_staff(interaction.user):
                return await interaction.response.send_message("No perm",ephemeral=True)

            self.disable_all()
            await interaction.message.edit(view=self)

            board_channel = self.cog.bot.get_channel(BOARD_CHANNEL_ID)
            await board_channel.send(f"❌ Tile {self.tile} rejected for <@{self.user}>")

            await interaction.response.send_message("Rejected",ephemeral=True)

# ================= LOAD =================
async def setup(bot):
    await bot.add_cog(Bingo(bot))