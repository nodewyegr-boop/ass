import discord
from discord.ext import commands
import db, os
from dotenv import load_dotenv
load_dotenv()
OWNER_ID = int(os.getenv("OWNER_ID"))

class GiveMoneyModal(discord.ui.Modal, title="ให้ตังคนที่เติมมา"):
    amount = discord.ui.TextInput(label="จำนวนเงิน (1-9999)", required=True)
    def __init__(self, target): super().__init__(); self.target = target
    async def on_submit(self, i: discord.Interaction):
        try: amt = int(self.amount.value)
        except: return await i.response.send_message("ใส่ตัวเลข", ephemeral=True)
        await db.update_balance(self.target.id, amt)
        new = await db.get_balance(self.target.id)
        await i.response.send_message("สำเร็จ แจ้งไปที่Dmคนนั้นเเล้ว", ephemeral=True)
        try: await self.target.send(f"สำเร็จ คุณได้ตังมา {amt} ยอดคงเหลือ {new}")
        except: pass

class AdminDepositView(discord.ui.View):
    def __init__(self, target): super().__init__(timeout=None); self.target = target
    @discord.ui.button(label="ให้ตังคนที่เติมมา", style=discord.ButtonStyle.success)
    async def give(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_modal(GiveMoneyModal(self.target))

class TopUpModal(discord.ui.Modal, title="เติมเงิน"):
    link = discord.ui.TextInput(label="ลิ้งซอง TrueMoney", required=True)
    async def on_submit(self, i: discord.Interaction):
        await i.response.send_message("รอแอดมินตรวจสอบ", ephemeral=True)
        owner = i.client.get_user(OWNER_ID)
        if owner: 
            embed = discord.Embed(title="มีคนเติมตังมา", color=0x2b2d31)
            embed.description = f"คนที่เติม {i.user.mention} ID({i.user.id})\n{self.link.value}"
            await owner.send(embed=embed, view=AdminDepositView(i.user))

class TopUpMainView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="เติมตัง", style=discord.ButtonStyle.success, custom_id="t1")
    async def t1(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_modal(TopUpModal())
    @discord.ui.button(label="เช็คยอด", style=discord.ButtonStyle.secondary, custom_id="t2")
    async def t2(self, i: discord.Interaction, b: discord.ui.Button): await i.response.send_message(f"ยอดเงินของคุณ: {await db.get_balance(i.user.id)} บาท", ephemeral=True)

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TopUpMainView())
        
    @commands.hybrid_command(name="true")
    async def true(self, ctx):
        if ctx.author.id != OWNER_ID: return await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่วว", ephemeral=True)
        embed = discord.Embed(color=0x2b2d31)
        embed.description = (
            f"# <:1000035915:1559174417097953340> เติมเงินซื้อของ\n"
            f"กดเติมเงินด้านล่าง รับเเค่ <:1000035915:1559174417097953340> เเล้วรอระบบตรวจสอบลิ้ง ถ้าตรวจสอบเสร็จเดียวบอทจะเเจ้งไปในDm"
        )
        await ctx.send(embed=embed, view=TopUpMainView())

    # บังคับใช้ ! นำหน้าเท่านั้น ห้ามใช้ /
    @commands.command(name="m")
    async def m(self, ctx, member: discord.Member, amount: int):
        if ctx.author.id != OWNER_ID: return
        await db.update_balance(member.id, amount)
        await ctx.send(f"ให้เงิน {member.mention} จำนวน {amount} บาทแล้ว")

    @commands.command(name="um")
    async def um(self, ctx, member: discord.Member, amount: int):
        if ctx.author.id != OWNER_ID: return
        await db.update_balance(member.id, -amount)
        await ctx.send(f"ลดเงิน {member.mention} จำนวน {amount} บาทแล้ว")

async def setup(bot): await bot.add_cog(Economy(bot))