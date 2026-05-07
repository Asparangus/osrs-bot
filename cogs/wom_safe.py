import asyncio
import time
import aiohttp
from database import get_last_wom_call, update_wom_call

WOM_DELAY = 3

async def fetch_wom_player_safe(username: str):
    last = await get_last_wom_call()
    now = int(time.time())

    wait = WOM_DELAY - (now - last)
    if wait > 0:
        await asyncio.sleep(wait)

    await update_wom_call(int(time.time()))

    url = f"https://api.wiseoldman.net/v2/players/{username.replace(' ', '%20')}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=20) as r:
            if r.status != 200:
                return None
            return await r.json()
