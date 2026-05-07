import aiosqlite
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path("data.db")

# ==========================================================
# INIT
# ==========================================================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:

        await db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;

        -- =====================
        -- CORE MEMBERS
        -- =====================
        CREATE TABLE IF NOT EXISTS members (
            discord_id INTEGER PRIMARY KEY,
            discord_name TEXT NOT NULL,
            osrs_name TEXT,
            points INTEGER DEFAULT 0,
            last_xp INTEGER DEFAULT 0,
            last_seen TEXT
        );

        -- =====================
        -- WEEKLY XP TRACKING
        -- =====================
        CREATE TABLE IF NOT EXISTS weekly_tracking (
            discord_id INTEGER,
            week_start TEXT,
            xp_gained INTEGER DEFAULT 0,
            PRIMARY KEY (discord_id, week_start)
        );

        CREATE TABLE IF NOT EXISTS weekly_role_state (
            week_start TEXT PRIMARY KEY,
            discord_id INTEGER,
            role_id INTEGER,
            assigned_at TEXT
        );

        -- =====================
        -- WOM RATE LIMIT
        -- =====================
        CREATE TABLE IF NOT EXISTS wom_rate_limit (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_call_ts INTEGER
        );

        INSERT OR IGNORE INTO wom_rate_limit (id, last_call_ts)
        VALUES (1, 0);

        -- =====================
        -- AUDIT LOG
        -- =====================
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            action TEXT,
            value INTEGER,
            created_at TEXT
        );

        -- =====================
        -- SUBMISSIONS
        -- =====================
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            value INTEGER,
            description TEXT,
            screenshot TEXT,
            is_xp INTEGER,
            is_boss INTEGER,
            boss_name TEXT,
            participants TEXT,
            created_at TEXT
        );

        -- =====================
        -- PET HUNT
        -- =====================
        CREATE TABLE IF NOT EXISTS pet_hunts (
            week_start TEXT PRIMARY KEY,
            pet_name TEXT,
            active INTEGER DEFAULT 1,
            winner_id INTEGER,
            prize_pool INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS pet_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            week_start TEXT,
            approved INTEGER DEFAULT 0,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS pet_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            week_start TEXT,
            pet_name TEXT,
            screenshot TEXT,
            approved INTEGER DEFAULT 0,
            created_at TEXT
        );

        -- =====================
        -- 🎮 BINGO SYSTEM
        -- =====================
        CREATE TABLE IF NOT EXISTS bingo_teams (
            team_id INTEGER,
            discord_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS bingo_boards (
            team_id INTEGER,
            tile INTEGER,
            task TEXT,
            completed INTEGER DEFAULT 0,
            board_id INTEGER DEFAULT 0,
            completed_by INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS bingo_messages (
            team_id INTEGER PRIMARY KEY,
            message_id INTEGER,
            channel_id INTEGER,
            board_id INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS image_hashes (
            hash TEXT PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS bingo_leaderboard (
            message_id INTEGER,
            channel_id INTEGER
        );

        -- =====================
        -- 🏆 BINGO SEASONS
        -- =====================
        CREATE TABLE IF NOT EXISTS bingo_seasons (
            season_id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            ended_at TEXT,
            winner_team INTEGER
        );

        -- =====================
        -- 🎥 BINGO REPLAYS
        -- =====================
        CREATE TABLE IF NOT EXISTS bingo_replays (
            team_id INTEGER,
            board_id INTEGER DEFAULT 0,
            tile INTEGER,
            user_id INTEGER,
            image TEXT,
            timestamp TEXT
        );

        -- =====================
        -- 💰 ECONOMY
        -- =====================
        CREATE TABLE IF NOT EXISTS bingo_wallets (
            user_id INTEGER PRIMARY KEY,
            coins INTEGER DEFAULT 0
        );

        -- =====================
        -- 🎯 ACHIEVEMENTS
        -- =====================
        CREATE TABLE IF NOT EXISTS bingo_achievements (
            user_id INTEGER,
            name TEXT,
            progress INTEGER DEFAULT 0,
            completed INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, name)
        );

        -- =====================
        -- 🏪 SHOP
        -- =====================
        CREATE TABLE IF NOT EXISTS bingo_shop (
            item TEXT PRIMARY KEY,
            price INTEGER
        );
        """)

        # =====================
        # SAFE MIGRATIONS (CRITICAL)
        # =====================

        # --- Add completed_by column ---
        try:
            await db.execute("""
                ALTER TABLE bingo_boards
                ADD COLUMN completed_by INTEGER DEFAULT 0
            """)
            print("[DB] Added completed_by column")
        except:
            pass

        # --- Ensure NO NULL values ---
        await db.execute("""
            UPDATE bingo_boards
            SET completed_by = 0
            WHERE completed_by IS NULL
        """)

        # --- Unique player constraint (VERY IMPORTANT) ---
        try:
            await db.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_player
                ON bingo_teams(discord_id)
            """)
            print("[DB] Added unique player index")
        except:
            pass

        # ==================================================
        # PERFORMANCE INDEXES
        # ==================================================

        await db.execute("CREATE INDEX IF NOT EXISTS idx_bingo_team ON bingo_boards(team_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bingo_tile ON bingo_boards(tile)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bingo_completed ON bingo_boards(completed)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bingo_team_tile ON bingo_boards(team_id, tile)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bingo_completed_by ON bingo_boards(completed_by)")

        await db.execute("CREATE INDEX IF NOT EXISTS idx_replays_team ON bingo_replays(team_id)")

        await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_image_hash_unique
        ON image_hashes(hash)
        """)

        await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_bingo_completed_by
        ON bingo_boards(completed_by)
        """)

        # ==================================================
        # DEFAULT SHOP
        # ==================================================

        await db.executemany("""
        INSERT OR IGNORE INTO bingo_shop (item, price) VALUES (?,?)
        """, [
            ("Skip Tile", 100),
            ("Double Reward", 200),
            ("Reveal Tile", 150)
        ])

        await db.commit()

# ==========================================================
# TIME HELPERS
# ==========================================================

def utc_now():
    return datetime.now(timezone.utc)

def current_week_start_utc():
    now = utc_now()
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


# ==========================================================
# MEMBER OPS
# ==========================================================

async def upsert_member(discord_id, discord_name, osrs_name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO members (discord_id, discord_name, osrs_name, last_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(discord_id) DO UPDATE SET
                discord_name = excluded.discord_name,
                osrs_name = excluded.osrs_name,
                last_seen = excluded.last_seen
        """, (discord_id, discord_name, osrs_name, utc_now().isoformat()))
        await db.commit()

async def get_all_members():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT discord_id, discord_name, osrs_name, points
            FROM members
            WHERE osrs_name IS NOT NULL
        """)
        return await cur.fetchall()

async def get_member(discord_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT discord_id, discord_name, osrs_name, points
            FROM members
            WHERE discord_id = ?
        """, (discord_id,))
        return await cur.fetchone()

# ==========================================================
# POINTS
# ==========================================================

async def get_points(discord_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT points FROM members WHERE discord_id = ?",
            (discord_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0

async def add_points(discord_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE members SET points = points + ? WHERE discord_id = ?",
            (amount, discord_id)
        )
        await db.execute("""
            INSERT INTO audit_log (discord_id, action, value, created_at)
            VALUES (?, 'points_added', ?, ?)
        """, (discord_id, amount, utc_now().isoformat()))
        await db.commit()

async def remove_points(discord_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE members
            SET points = MAX(points - ?, 0)
            WHERE discord_id = ?
        """, (amount, discord_id))
        await db.execute("""
            INSERT INTO audit_log (discord_id, action, value, created_at)
            VALUES (?, 'points_removed', ?, ?)
        """, (discord_id, amount, utc_now().isoformat()))
        await db.commit()

async def get_member_points(discord_id: int) -> int:
    return await get_points(discord_id)

# ==========================================================
# XP / WEEKLY
# ==========================================================

async def get_last_xp(discord_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT last_xp FROM members WHERE discord_id = ?",
            (discord_id,)
        )
        row = await cur.fetchone()
        return row[0] if row else 0

async def update_last_xp(discord_id, xp):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE members SET last_xp = ? WHERE discord_id = ?",
            (xp, discord_id)
        )
        await db.commit()

async def add_weekly_xp(discord_id, xp):
    week = current_week_start_utc()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO weekly_tracking (discord_id, week_start, xp_gained)
            VALUES (?, ?, ?)
            ON CONFLICT(discord_id, week_start)
            DO UPDATE SET xp_gained = xp_gained + excluded.xp_gained
        """, (discord_id, week, xp))
        await db.commit()

# ==========================================================
# SUBMISSIONS
# ==========================================================

async def create_submission(
    discord_id: int,
    value: int,
    description: str,
    screenshot: str,
    is_xp: bool,
    is_boss: bool,
    boss_name: str,
    participants: str,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO submissions (
                discord_id, value, description, screenshot,
                is_xp, is_boss, boss_name, participants, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            discord_id,
            value,
            description,
            screenshot,
            int(is_xp),
            int(is_boss),
            boss_name,
            participants,
            utc_now().isoformat()
        ))
        await db.commit()
        cur = await db.execute("SELECT last_insert_rowid()")
        row = await cur.fetchone()
        return row[0]

# ==========================================================
# USERNAME CHANGE
# ==========================================================

async def update_member_username(discord_id: int, new_osrs_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE members
            SET osrs_name = ?, last_seen = ?
            WHERE discord_id = ?
        """, (new_osrs_name, utc_now().isoformat(), discord_id))
        await db.commit()
        return True

# ==========================================================
# WOM RATE LIMIT
# ==========================================================

async def get_last_wom_call():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT last_call_ts FROM wom_rate_limit WHERE id = 1"
        )
        row = await cur.fetchone()
        return row[0]

async def update_wom_call(ts: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE wom_rate_limit SET last_call_ts = ? WHERE id = 1",
            (ts,)
        )
        await db.commit()

# ==========================================================
# REMOVE MEMBER
# ==========================================================

async def remove_member(discord_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM members WHERE discord_id = ?", (discord_id,))
        await db.execute("DELETE FROM weekly_tracking WHERE discord_id = ?", (discord_id,))
        await db.execute("DELETE FROM audit_log WHERE discord_id = ?", (discord_id,))
        await db.commit()

# ==========================================================
# LEGACY ALIASES
# ==========================================================

async def register_member(discord_id: int, discord_name: str, osrs_name: str):
    await upsert_member(discord_id, discord_name, osrs_name)
