import discord
from discord.ext import commands
from discord import app_commands
import db
import os
from dotenv import load_dotenv

load_dotenv()
OWNER_ID = int(os.getenv("OWNER_ID"))

class GiveMoneyModal(discord.ui.Modal, title="ให้ตังคนที่เติมมา"):
    amount = discord.ui.TextInput(label="จำนวนเงิน (1-9999)", placeholder="เช่น 50", required=True)

    def __init__(self, target_user: discord.User):
        super().__init__()
        self.target_user = target_user

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            if amt < 1 or amt > 9999: raise ValueError
        except ValueError:
            return await interaction.response.send_message("กรุณาใส่ตัวเลข 1-9999", ephemeral=True)

        await db.update_balance(self.target_user.id, amt)
        new_bal = await db.get_balance(self.target_user.id)
        
        await interaction.response.send_message(f"✅ สำเร็จ แจ้งไปที่ DM คนนั้นแล้ว", ephemeral=True)
        
        try:
            await self.target_user.send(f"✅ สำเร็จ คุณได้ตังมา **{amt}** บาท\nยอดคงเหลือ **{new_bal}** บาท")
        except:
            pass

class AdminDepositView(discord.ui.View):
    def __init__(self, target_user: discord.User):
        super().__init__(timeout=None)
        self.target_user = target_user

    @discord.ui.button(label="ให้ตังคนที่เติมมา", style=discord.ButtonStyle.success)
    async def give_money(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GiveMoneyModal(self.target_user))

class TopUpModal(discord.ui.Modal, title="เติมเงิน"):
    link = discord.ui.TextInput(label="ลิ้งซอง TrueMoney", placeholder="https://gift.truemoney.com/campaign/?v=...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("รอแอดมินตรวจสอบ...", ephemeral=True)
        
        owner = interaction.client.get_user(OWNER_ID)
        if owner:
            embed = discord.Embed(title="💰 มีคนเติมตังมา", color=0x2b2d31)
            embed.description = f"คนที่เติม: {interaction.user.mention} (ID: {interaction.user.id})\n\nลิ้งซอง:\n{self.link.value}"
            await owner.send(embed=embed, view=AdminDepositView(interaction.user))

class TopUpMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="เติมตัง", style=discord.ButtonStyle.success, custom_id="topup_btn")
    async def topup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TopUpModal())

    @discord.ui.button(label="เช็คยอด", style=discord.ButtonStyle.secondary, custom_id="check_bal_btn")
    async def check_bal(self, interaction: discord.Interaction, button: discord.ui.Button):
        bal = await db.get_balance(interaction.user.id)
        await interaction.response.send_message(f"✅ ยอดเงินของคุณ: **{bal}** บาท", ephemeral=True)

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.add_view(TopUpMainView())

    @commands.hybrid_command(name="true", description="ระบบเติมเงิน")
    async def true(self, ctx: commands.Context):
        if ctx.author.id != OWNER_ID:
            return await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่วว", ephemeral=True)
            
        embed = discord.Embed(color=0x2b2d31)
        embed.description = (
            f"# <:1000035915:1559174417097953340> เติมเงินซื้อของ\n"
            f"กดเติมเงินด้านล่าง รับเเค่ <:1000035915:1559174417097953340> เเล้วรอระบบตรวจสอบลิ้ง ถ้าตรวจสอบเสร็จเดียวบอทจะเเจ้งไปในDm"
        )
        await ctx.send(embed=embed, view=TopUpMainView())

    @commands.hybrid_command(name="m", description="ให้เงินผู้ใช้")
    async def m(self, ctx: commands.Context, member: discord.Member, amount: int):
        if ctx.author.id != OWNER_ID: return
        await db.update_balance(member.id, amount)
        await ctx.send(f"✅ให้เงิน {member.mention} จำนวน {amount} บาทแล้ว", ephemeral=True)

    @commands.hybrid_command(name="um", description="ลดเงินผู้ใช้")
    async def um(self, ctx: commands.Context, member: discord.Member, amount: int):
        if ctx.author.id != OWNER_ID: return
        await db.update_balance(member.id, -amount)
        await ctx.send(f"✅ ลดเงิน {member.mention} จำนวน {amount} บาทแล้ว", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Economy(bot))