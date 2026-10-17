import discord
from discord.ext import commands, tasks
import aiohttp
import aiosqlite
import db

class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_nitro.start()

    def cog_unload(self):
        self.check_nitro.cancel()

    @tasks.loop(minutes=1)
    async def check_nitro(self):
        """สแกน Token ทุกตัวใน DB เพื่อดูว่ามี Nitro และ Boost 2 หรือไม่"""
        async with aiosqlite.connect(db.DB_PATH) as db_conn:
            async with db_conn.execute("SELECT token, claimed FROM accounts") as cursor:
                rows = await cursor.fetchall()
                
                for token, claimed in rows:
                    if claimed: continue # ข้ามถ้าถูกใช้ไปแล้ว
                    
                    headers = {"Authorization": f"Bearer {token}"}
                    async with aiohttp.ClientSession() as session:
                        async with session.get("https://discord.com/api/v10/users/@me", headers=headers) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                nitro_type = data.get("premium_type", 0)
                                
                                # ถ้ามี Nitro (Type 2 = Nitro, 3 = Nitro Basic)
                                if nitro_type >= 2:
                                    await db_conn.execute("UPDATE accounts SET nitro_status = 1 WHERE token = ?", (token,))
                                else:
                                    await db_conn.execute("UPDATE accounts SET nitro_status = 0 WHERE token = ?", (token,))
                                await db_conn.commit()

    @check_nitro.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Tasks(bot))