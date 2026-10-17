import discord
from discord.ext import commands
import os
from database import init_db

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
OWNER_ID = 1488103702488154173

@bot.event
async def on_ready():
    init_db()
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    print("Loading cogs...")
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            print(f"Loaded cog: {filename[:-3]}")
    print("Bot is ready!")

# คำสั่งจัดการเงินเฉพาะ Owner (!m และ !um)
@bot.command(name="m")
async def add_money(ctx, member: discord.Member, amount: int):
    if ctx.author.id != OWNER_ID:
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่วว", ephemeral=True)
        return
    from database import update_user_balance
    update_user_balance(str(member.id), amount)
    await ctx.send(f"เพิ่มเงินให้ {member.mention} จำนวน {amount} บาท สำเร็จ!")

@bot.command(name="um")
async def deduct_money(ctx, member: discord.Member, amount: int):
    if ctx.author.id != OWNER_ID:
        await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่วว", ephemeral=True)
        return
    from database import update_user_balance
    update_user_balance(str(member.id), -amount)
    await ctx.send(f"ลดเงินจาก {member.mention} จำนวน {amount} บาท สำเร็จ!")

# รันบอท (ใส่ Token ของคุณที่นี่)
bot.run("YOUR_DISCORD_BOT_TOKEN")
