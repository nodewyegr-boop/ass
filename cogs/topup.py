import discord
from discord.ext import commands
import sqlite3
from database import DB_NAME, get_user_balance, update_user_balance

OWNER_ID = 1488103702488154173

class TopUp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="true")
    async def true_command(self, ctx):
        if ctx.author.id != OWNER_ID:
            await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่วว")
            return
        
        embed = discord.Embed(
            title="<:1000035915:1559174417097953340> เติมเงินซื้อของ",
            description="กดเติมเงินด้านล่าง รับเเค่ <:1000035915:1559174417097953340> เเล้วรอระบบตรวจสอบลิ้ง ถ้าตรวจสอบเสร็จเดียวบอทจะเเจ้งไปในDm",
            color=discord.Color.green()
        )
        view = TopUpView()
        await ctx.send(embed=embed, view=view)

class TopUpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="เติมตัง", style=discord.ButtonStyle.success, custom_id="btn_topup_link")
    async def topup_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(TopUpModal())

    @discord.ui.button(label="เช็คยอด", style=discord.ButtonStyle.secondary, custom_id="btn_check_balance")
    async def check_bal_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        bal = get_user_balance(str(inter.user.id))
        await inter.response.send_message(f"ยอดเงินคงเหลือของคุณ: {bal} บาท", ephemeral=True)

class TopUpModal(discord.ui.Modal, title="เติมเงินผ่านซองของขวัญ TrueMoney"):
    link = discord.ui.inputText(label="ลิ้งซองของขวัญ TrueMoney", placeholder="https://gift.truemoney.com/campaign/?v=...")

    async def on_submit(self, inter: discord.Interaction):
        await inter.response.send_message("รอแอดมินตรวจสอบ", ephemeral=True)
        
        # ส่งข้อมูลเข้า DM ของ Owner (1488103702488154173)
        owner = inter.client.get_user(OWNER_ID)
        if owner:
            try:
                dm = await owner.create_dm()
                embed = discord.Embed(
                    title="มีคนเติมตังมา",
                    description=f"คนที่เติม: {inter.user.mention} ({inter.user.name})\nID: {inter.user.id}\nลิ้งซอง: {self.link.value}",
                    color=discord.Color.gold()
                )
                view = AdminApproveView(user_id=inter.user.id, voucher_link=self.link.value)
                await dm.send(embed=embed, view=view)
            except Exception as e:
                print(f"Error sending DM to owner: {e}")

class AdminApproveView(discord.ui.View):
    def __init__(self, user_id, voucher_link):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.voucher_link = voucher_link

    @discord.ui.button(label="ให้ตังคนที่เติมมา", style=discord.ButtonStyle.primary, custom_id="btn_admin_give_money")
    async def give_money_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        if inter.user.id != OWNER_ID:
            return
        await inter.response.send_modal(AdminAmountModal(target_user_id=self.user_id))

class AdminAmountModal(discord.ui.Modal, title="กำหนดจำนวนเงินที่จะเติมให้ผู้ใช้"):
    amount_input = discord.ui.inputText(label="จำนวนเงิน (1-9999 บาท)", placeholder="เช่น 50")

    def __init__(self, target_user_id):
        super().__init__()
        self.target_user_id = target_user_id

    async def on_submit(self, inter: discord.Interaction):
        if not self.amount_input.value.isdigit():
            await inter.response.send_message("กรุณาใส่ตัวเลขเท่านั้น", ephemeral=True)
            return
        
        amt = int(self.amount_input.value)
        update_user_balance(str(self.target_user_id), amt)
        new_bal = get_user_balance(str(self.target_user_id))

        await inter.response.send_message(f"สำเร็จ เเจ้งไปที่ Dm คนนั้นเเล้ว (ยอด {amt} บาท)", ephemeral=True)

        # แจ้งเตือนไปหา User ที่เติมเงิน
        target_user = inter.client.get_user(int(self.target_user_id))
        if target_user:
            try:
                dm = await target_user.create_dm()
                await dm.send(f"สำเร็จ คุณได้ตังมา {amt} บาท ยอดคงเหลือ: {new_bal} บาท")
            except:
                pass

async def setup(bot):
    await bot.add_cog(TopUp(bot))
