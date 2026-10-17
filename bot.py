import os
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
        await self.load_extension("cogs.nitro")
        await self.load_extension("cogs.economy")
        await self.load_extension("cogs.tasks")
        await self.tree.sync()

bot = ValanBot()

@bot.event
async def on_ready():
    print(f"[+] {bot.user} online")

if __name__ == "__main__":
    bot.run(os.getenv("BOT_TOKEN"))