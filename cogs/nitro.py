import discord
from discord.ext import commands
from discord import app_commands
import os
import random
import string
import aiohttp
import db
from dotenv import load_dotenv

load_dotenv()
OWNER_ID = int(os.getenv("OWNER_ID"))

# คลาสสำหรับรับ OAuth2 (Web Server)
class OAuth2Server:
    def __init__(self, bot):
        self.bot = bot
        self.app = None

    async def start(self):
        from aiohttp import web
        self.app = web.Application()
        self.app.router.add_get('/callback', self.handle_callback)
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        print("[+] OAuth2 Server started on port 8080")

    async def handle_callback(self, request):
        from aiohttp import web
        code = request.query.get('code')
        if not code:
            return web.Response(text="No code provided", status=400)

        # แลก Code เป็น Token
        data = {
            'client_id': os.getenv('CLIENT_ID'),
            'client_secret': os.getenv('CLIENT_SECRET'),
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': os.getenv('REDIRECT_URI')
        }
        async with aiohttp.ClientSession() as session:
            async with session.post("https://discord.com/api/v10/oauth2/token", data=data) as resp:
                if resp.status != 200:
                    return web.Response(text="Failed to get token", status=400)
                token_data = await resp.json()
                access_token = token_data['access_token']
                refresh_token = token_data['refresh_token']

                # ดึงข้อมูล User
                headers = {'Authorization': f'Bearer {access_token}'}
                async with session.get("https://discord.com/api/v10/users/@me", headers=headers) as user_resp:
                    if user_resp.status == 200:
                        user_data = await user_resp.json()
                        user_id = int(user_data['id'])

                        # บันทึกลง DB
                        async with aiosqlite.connect(db.DB_PATH) as db_conn:
                            await db_conn.execute("INSERT OR REPLACE INTO accounts (user_id, token, refresh_token) VALUES (?, ?, ?)", (user_id, access_token, refresh_token))
                            await db_conn.commit()

                        return web.Response(text="Authorization successful! You can close this window.", content_type='text/html')
        return web.Response(text="Error", status=500)

# ----- Views -----

class BuyBoostModal(discord.ui.Modal, title="ซื้อรหัสบูส"):
    amount = discord.ui.TextInput(label="จำนวนบัญชี (1 บัญชี = 5 บาท = 2 บูส)", placeholder="เช่น 1, 2, 5", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            if amt < 1: raise ValueError
        except ValueError:
            return await interaction.response.send_message("กรุณาใส่ตัวเลขจำนวนเต็ม 1 ขึ้นไป", ephemeral=True)

        cost = amt * 5
        balance = await db.get_balance(interaction.user.id)

        if balance < cost:
            return await interaction.response.send_message(f"เงินไม่พอ (ต้องการ {cost} บาท, คุณมี {balance} บาท)", ephemeral=True)

        # หักเงิน
        await db.update_balance(interaction.user.id, -cost)

        # สร้างรหัส
        rand_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        code = f"222.{rand_str}"

        # บันทึก DB
        import aiosqlite
        async with aiosqlite.connect(db.DB_PATH) as db_conn:
            await db_conn.execute("INSERT INTO boost_codes (code, user_id, amount) VALUES (?, ?, ?)", (code, interaction.user.id, amt))
            await db_conn.commit()

        # ส่ง DM
        try:
            embed = discord.Embed(title="ซื้อรหัสบูสสำเร็จ", color=0x2b2d31)
            embed.description = f"นี่คือรหัสบูสของคุณ:\n||`{code}`||\n\n**นำรหัสนี้ไปกรอกในเมนู 'บูสดิส'**\n\nลิ้งเชิญบอทไปเซิฟที่ต้องการบูส:\n[คลิกเพื่อเชิญบอท](https://discord.com/oauth2/authorize?client_id={os.getenv('CLIENT_ID')}&permissions=8&scope=bot%20applications.commands)"
            await interaction.user.send(embed=embed)
            await interaction.response.send_message("สำเร็จรหัสถูกส่งไปที่ DM ของคุณแล้ว", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("ไม่สามารถส่ง DM ได้ เปิดdmก่อน", ephemeral=True)

class BoostServerModal(discord.ui.Modal, title="บูสเซิร์ฟเวอร์"):
    guild_id = discord.ui.TextInput(label="ID เซิร์ฟเวอร์ที่ต้องการบูส", placeholder="เช่น 123456789012345678", required=True)
    code = discord.ui.TextInput(label="รหัสบูส (จาก DM)", placeholder="222.xxxxxxxxx", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        # เช็คบอทอยู่ในเซิฟไหม
        try:
            target_guild = self.bot.get_guild(int(self.guild_id.value))
            if not target_guild:
                return await interaction.response.send_message("ไม่สำเร็จบอทไม่อยู่ในดิสนั้น เชิญบอทก่อนนะ", ephemeral=True)
        except:
            return await interaction.response.send_message("ID เซิร์ฟเวอร์ไม่ถูกต้อง", ephemeral=True)

        # เช็ครหัส
        import aiosqlite
        async with aiosqlite.connect(db.DB_PATH) as db_conn:
            async with db_conn.execute("SELECT amount, used FROM boost_codes WHERE code = ? AND user_id = ?", (self.code.value, interaction.user.id)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return await interaction.response.send_message("รหัสไม่ถูกต้องหรือไม่ใช่ของคุณ", ephemeral=True)
                amount, used = row
                if used:
                    return await interaction.response.send_message("รหัสนี้ถูกใช้งานไปแล้ว", ephemeral=True)

                # มาร์คว่าใช้แล้ว
                await db_conn.execute("UPDATE boost_codes SET used = 1 WHERE code = ?", (self.code.value,))
                await db_conn.commit()

        await interaction.response.send_message("กำลังเริ่มจอย...", ephemeral=True)

        # ส่งไปทำระบบบูส (Background Task)
        self.bot.loop.create_task(self.process_boost(interaction.user, int(self.guild_id.value), amount))

    async def process_boost(self, user, guild_id, amount):
        import aiohttp
        joined = 0
        boosted = 0

        async with aiosqlite.connect(db.DB_PATH) as db_conn:
            # ดึง Token ที่ว่าง
            async with db_conn.execute("SELECT token FROM accounts WHERE claimed = 0 LIMIT ?", (amount,)) as cursor:
                accounts = await cursor.fetchall()

                for (token,) in accounts:
                    # ให้ User เข้าเซิฟ (guilds.join scope)
                    headers = {"Authorization": f"Bot {os.getenv('BOT_TOKEN')}", "Content-Type": "application/json"}
                    data = {"access_token": token}
                    async with aiohttp.ClientSession() as session:
                        async with session.put(f"https://discord.com/api/v10/guilds/{guild_id}/members/{user.id}", headers=headers, json=data) as resp:
                            if resp.status in (201, 204):
                                joined += 1

                        # สั่งบูส (ใช้ User Token)
                        user_headers = {"Authorization": token}
                        async with session.put(f"https://discord.com/api/v10/guilds/{guild_id}/members/@me", headers=user_headers) as boost_resp:
                            if boost_resp.status == 200:
                                boosted += 1

                    # มาร์คว่าบัญชีนี้ถูกใช้แล้ว
                    await db_conn.execute("UPDATE accounts SET claimed = 1 WHERE token = ?", (token,))
                    await db_conn.commit()

        # แจ้งผล
        embed = discord.Embed(title="บูสสำเร็จ", color=0x00ff00)
        embed.description = f"บัญชีทั้งหมด: {joined}\nบูสที่บูสได้: {boosted * 2} (บัญชีละ 2 บูส)"
        await user.send(embed=embed)


class SystemPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="ซื้อรหัสบูส", style=discord.ButtonStyle.success, custom_id="buy_boost_btn")
    async def buy_boost(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BuyBoostModal())

    @discord.ui.button(label="บูสดิส", style=discord.ButtonStyle.primary, custom_id="boost_guild_btn")
    async def boost_guild(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BoostServerModal())


class NitroMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="แผงระบบ", style=discord.ButtonStyle.secondary, custom_id="sys_panel_btn")
    async def sys_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        stats = await db.get_stats()
        available = stats[0] if stats else 0
        sold = stats[1] if stats else 0

        embed = discord.Embed(color=0x2b2d31)
        embed.description = (
            f"# <:1000039353:1560870698485022821> auto sell Boost server <:1000039353:1560870698485022821>\n"
            f"กดเติมตังที่ <#1560871774961401856> ก่อน แล้วรอเงินเข้า รับเเค่ <a:1000030144:1559280351254151199>\n\n"
            f"บัญชีละ 5 บ. ไม่ว่าจะ1เดือนหรือ3เดือน 5บ. เหมือนกันสุ่มๆเอา\n\n"
            f"<:1000039353:1560870698485022821> เหลือ **{available}** บัญชี\n"
            f"<a:1000039264:1560448511588302928> ขายเเล้ว **{sold}** บูส\n\n"
            f"หลังจากเงินเข้า กดปุ่มด้านล่าง ซื้อบูสดิส ใส่จำนวนที่จะซื้อ บัญชีละ5บาท ก็คือ5บาทจะได้2บูส หลังจากกดซื้อ บอทจะส่งรหัสเข้าไปในDm นะครับโปรดเปิดDmด้วย ส่งไปพร้อมกับลิ้งเชิญบอท ให้เชิญบอทไปที่เซิฟที่จะบูส เเล้วกลับมาที่เเผงหลัก ใส่ID เซิฟเวอร์ที่จะบูสไป เเละรอไปประมาณ2นาทีจะเริ่มบูส\n\n"
            f"<:1000035866:1559279147648290947> โปรดปิดanti botก่อนนะครับ บัญชีจะได้ไม่โดนเตะหรือเเบน จะไม่รับผิดชอบ"
        )
        embed.set_image(url="https://cdn.discordapp.com/attachments/1555167748865392701/1560874474478374943/7a7f7c254b3951e2d6aa379d5abbee53.jpg")
        await interaction.response.send_message(embed=embed, view=SystemPanelView(), ephemeral=True)

    @discord.ui.button(label="รับลิ้ง", style=discord.ButtonStyle.primary, custom_id="oauth_link_btn")
    async def oauth_link(self, interaction: discord.Interaction, button: discord.ui.Button):
        url = f"https://discord.com/oauth2/authorize?client_id={os.getenv('CLIENT_ID')}&response_type=code&redirect_uri={os.getenv('REDIRECT_URI')}&scope=identify%20guilds.join"
        embed = discord.Embed(title="🔗 เพิ่มบัญชี Nitro", description="[คลิกที่นี่เพื่อเข้าสู่ระบบและให้สิทธิ์บอท](%s)\n\n*ระบบจะรักษาสิทธิ์และต่ออายุ Token ให้ตลอด*" % url, color=0x2b2d31)
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="เช็คบัญชี", style=discord.ButtonStyle.secondary, custom_id="check_acc_btn")
    async def check_acc(self, interaction: discord.Interaction, button: discord.ui.Button):
        import aiosqlite
        async with aiosqlite.connect(db.DB_PATH) as db_conn:
            async with db_conn.execute("SELECT user_id, nitro_status, claimed FROM accounts") as cursor:
                rows = await cursor.fetchall()

                if not rows:
                    return await interaction.response.send_message("ยังไม่มีบัญชีที่ให้สิทธิ์", ephemeral=True)

                embed = discord.Embed(title="รายชื่อบัญชีที่ให้สิทธิ์", color=0x2b2d31)
                for uid, nitro, claimed in rows:
                    boost_status = "บูสแล้ว" if claimed else "ยังไม่ได้บูส"
                    embed.add_field(
                        name=f"User: <@{uid}>",
                        value=f"Nitro: {'✅มี' if nitro else '❌ ไม่มี'}\nBoost: {boost_status}",
                        inline=False
                    )
                await interaction.response.send_message(embed=embed, ephemeral=True)

# ----- Commands -----

class Nitro(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.oauth_server = OAuth2Server(bot)
        self.bot.loop.create_task(self.oauth_server.start())

        # โหลด Persistent Views
        self.bot.add_view(NitroMainView())
        self.bot.add_view(SystemPanelView())

    @commands.hybrid_command(name="nitro", description="ระบบ Nitro และ Boost")
    async def nitro(self, ctx: commands.Context):
        if ctx.author.id != OWNER_ID:
            return await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่วว", ephemeral=True)

        embed = discord.Embed(title="Nitro System", description="เลือกเมนูด้านล่างเพื่อดำเนินการ", color=0x2b2d31)
        await ctx.send(embed=embed, view=NitroMainView(), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Nitro(bot))