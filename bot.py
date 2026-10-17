import os
import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
import db

load_dotenv()

class ValanBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await db.init_db()
        # โหลด Cogs
        await self.load_extension("cogs.nitro")
        await self.load_extension("cogs.economy")
        await self.load_extension("cogs.tasks")
        
        # ซิงค์ Slash Commands
        await self.tree.sync()
        print("[+] Cogs loaded and commands synced.")

bot = ValanBot()

@bot.event
async def on_ready():
    print(f"[+] {bot.user} online")
    # บอทออนไลน์แล้วใช้งานได้เลย ไม่ต้องรันคำสั่งใหม่ (Persistent views ถูกโหลดใน Cog)

if __name__ == "__main__":
    bot.run(os.getenv("BOT_TOKEN"))