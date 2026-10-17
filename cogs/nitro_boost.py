import discord
from discord.ext import commands, tasks
import sqlite3
import random
import string
from database import DB_NAME, get_user_balance, update_user_balance

OWNER_ID = 1488103702488154173

class NitroBoost(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_nitro_tokens.start()

    def cog_unload(self):
        self.check_nitro_tokens.cancel()

    @commands.slash_command(name="nitro", description="เปิดแผงควบคุมระบบ Nitro & Boost")
    async def nitro_panel(self, inter: discord.Interaction):
        if inter.user.id != OWNER_ID:
            await inter.response.send_message("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่วว", ephemeral=True)
            return
        
        view = MainPanelView()
        embed = discord.Embed(
            title="<:1000039353:1560870698485022821> auto sell Boost server <:1000039353:1560870698485022821>",
            description=(
                "กดเติมตังที่ https://discord.com/channels/1489537948746645645/1560871774961401856 ก่อน แล้วรอเงินเข้า รับเเค่ <a:1000030144:1559280351254151199>\n\n"
                "บัญชีละ 5 บ. ไม่ว่าจะ1เดือนหรือ3เดือน 5บ. เหมือนกันสุ่มๆเอา\n\n"
                "<:1000039353:1560870698485022821> เหลือ 10 บัญชีที่มีบูส <a:1000039264:1560448511588302928> ขายเเล้ว 2 บัญชี\n\n"
                "หลังจากเงินเข้า กดปุ่มด้านล่าง ซื้อบูสดิส ใส่จำนวนที่จะซื้อ บัญชีละ5บาท ก็คือ5บาทจะได้2บูส หลังจากกดซื้อ บอทจะส่งรหัสเข้าไปในDm นะครับโปรดเปิดDmด้วย ส่งไปพร้อมกับลิ้งเชิญบอท ให้เชิญบอทไปที่เซิฟที่จะบูส เเล้วกลับมาที่เเผงหลัก ใส่ID เซิฟเวอร์ที่จะบูสไป เเละรอไปประมาณ2นาทีจะเริ่มบูส\n\n"
                "<:1000035866:1559279147648290947> โปรดปิดanti botก่อนนะครับ บัญชีจะได้ไม่โดนเตะหรือเเบน จะไม่รับผิดชอบ"
            ),
            color=discord.Color.dark_embed()
        )
        embed.set_image(url="https://cdn.discordapp.com/attachments/1555167748865392701/1560874474478374943/7a7f7c254b3951e2d6aa379d5abbee53.jpg")
        await inter.response.send_message(embed=embed, view=view, ephemeral=False)

    # Background Task ตรวจสอบ Nitro ทุกๆ 1 นาที
    @tasks.loop(minutes=1.0)
    async def check_nitro_tokens(velf=None):
        # โค้ดสำหรับเช็คโทเค็น OAuth2 ใน Data ว่ามี Nitro หรือไม่ อัปเดตสถานะอัตโนมัติ
        pass

class MainPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="แผงระบบ", style=discord.ButtonStyle.primary, custom_id="btn_main_panel")
    async def main_panel_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_message("นี่คือแผงระบบหลักของคุณ", ephemeral=True)

    @discord.ui.button(label="รับลิ้ง", style=discord.ButtonStyle.success, custom_id="btn_get_link")
    async def get_link_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        # ลิงก์ OAuth2 ของ Discord (แทนที่ CLIENT_ID และ REDIRECT_URI ของคุณ)
        oauth_url = "https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=YOUR_REDIRECT_URI&response_type=code&scope=identify+guilds.join+applications.store.update"
        await inter.response.send_message(f"คลิกเพื่อยืนยันสิทธิ์ OAuth2:\n{oauth_url}", ephemeral=True)

    @discord.ui.button(label="เช็คบัญชี", style=discord.ButtonStyle.secondary, custom_id="btn_check_account")
    async def check_account_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        # จำลองการแสดงผลเช็คบัญชีตามที่ขอ
        text = "(account_example@gmail.com) | มีไนโตร: ยังไม่ได้รับ | สถานะ: ยังไม่ได้รับ | บูส: ยังไม่ได้บูส"
        await inter.response.send_message(text, ephemeral=True)

    @discord.ui.button(label="ซื้อรหัสบูส", style=discord.ButtonStyle.danger, custom_id="btn_buy_boost")
    async def buy_boost_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(BuyBoostModal())

    @discord.ui.button(label="บูสดิส", style=discord.ButtonStyle.success, custom_id="btn_do_boost")
    async def do_boost_btn(self, inter: discord.Interaction, button: discord.ui.Button):
        await inter.response.send_modal(DoBoostModal())

class BuyBoostModal(discord.ui.Modal, title="ซื้อรหัสบูสเซิร์ฟเวอร์"):
    amount = discord.ui.inputText(label="ใส่จำนวนบัญชีที่ต้องการซื้อ (ตัวเลขเท่านั้น)", placeholder="เช่น 1, 2, 3")

    async def on_submit(self, inter: discord.Interaction):
        raw_val = self.amount.value
        if not raw_val.isdigit():
            await inter.response.send_message("กรุณาใส่เฉพาะตัวเลขเท่านั้น ห้ามมีสิ่งแปลกปลอม!", ephemeral=True)
            return
        
        qty = int(raw_val)
        cost = qty * 5
        user_bal = get_user_balance(str(inter.user.id))

        if user_bal < cost:
            await inter.response.send_message("เงินไม่พอ", ephemeral=True)
            return
        
        # ตัดเงินและสร้างรหัส 222.xxxx
        update_user_balance(str(inter.user.id), -cost)
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        generated_code = f"222.{random_str}"

        # บันทึกลง DB
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO boost_codes (code, account_ids, used) VALUES (?, ?, 0)", (generated_code, "acc1,acc2"))
        conn.commit()
        conn.close()

        await inter.response.send_message("สำเร็จ รหัสส่งไปที่ Dm แล้ว", ephemeral=True)
        try:
            dm_channel = await inter.user.create_dm()
            await dm_channel.send(f"นี่คือรหัสผ่านของคุณ: ||{generated_code}||")
        except:
            pass

class DoBoostModal(discord.ui.Modal, title="ระบบบูสดิสคอร์ด"):
    server_id = discord.ui.inputText(label="ID เซิร์ฟเวอร์ดิสคอร์ด")
    boost_code = discord.ui.inputText(label="รหัสผ่าน (ขึ้นต้นด้วย 222.)", placeholder="เช่น 222.zs82msa82a")

    async def on_submit(self, inter: discord.Interaction):
        code = self.boost_code.value
        if not code.startswith("222."):
            await inter.response.send_message("รหัสผ่านต้องขึ้นต้นด้วย 222. เท่านั้น", ephemeral=True)
            return
        
        # ตรวจสอบรหัสใน DB
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT used FROM boost_codes WHERE code = ?", (code,))
        row = cursor.fetchone()
        conn.close()

        if not row or row[0] == 1:
            await inter.response.send_message("รหัสไม่ถูกต้องหรือถูกใช้งานไปแล้ว", ephemeral=True)
            return

        await inter.response.send_message("กำลังเริ่มจอย...", ephemeral=True)

async def setup(bot):
    await bot.add_cog(NitroBoost(bot))
