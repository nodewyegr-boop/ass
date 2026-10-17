import discord
from discord.ext import commands
import os, random, string, aiohttp, db, aiosqlite, time
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()
OWNER_ID = int(os.getenv("OWNER_ID"))

class OAuth2Server:
    def __init__(self, bot): 
        self.bot = bot
        
    async def start(self):
        from aiohttp import web
        app = web.Application()
        app.router.add_get('/callback', self.handle_callback)
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, '0.0.0.0', 8080).start()
        print("[+] OAuth2 Server started on port 8080")

    async def handle_callback(self, request):
        from aiohttp import web
        
        # ดักจับกรณี Discord ส่ง Error กลับมา
        error = request.query.get('error')
        if error:
            return web.Response(text=f"<h1>Discord Error</h1><p>สิทธิ์ถูกปฏิเสธ: {error}</p>", content_type='text/html')

        code = request.query.get('code')
        if not code: 
            return web.Response(text="<h1>Error: No code provided</h1><p>กรุณากดลิงก์จากใน Discord และกดปุ่ม 'อนุญาต' ครับ</p>", content_type='text/html')
        
        data = {
            'client_id': os.getenv('CLIENT_ID'), 
            'client_secret': os.getenv('CLIENT_SECRET'), 
            'grant_type': 'authorization_code', 
            'code': code, 
            'redirect_uri': os.getenv('REDIRECT_URI')
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post("https://discord.com/api/v10/oauth2/token", data=data) as resp:
                    resp_data = await resp.json()
                    if resp.status != 200: 
                        return web.Response(text=f"<h1>Discord API Error</h1><p>{resp_data}</p>", content_type='text/html')
                    
                    async with session.get("https://discord.com/api/v10/users/@me", headers={'Authorization': f"Bearer {resp_data['access_token']}"}) as u:
                        if u.status == 200:
                            ud = await u.json()
                            async with aiosqlite.connect(db.DB_PATH) as db_conn:
                                await db_conn.execute(
                                    "INSERT OR REPLACE INTO accounts (user_id, token, refresh_token, expires_at) VALUES (?, ?, ?, ?)", 
                                    (int(ud['id']), resp_data['access_token'], resp_data['refresh_token'], int(time.time()) + resp_data['expires_in'])
                                )
                                await db_conn.commit()
                            return web.Response(text=f"<h1>Authentication successful</h1><p>เพิ่มบัญชี {ud['username']} สำเร็จ! ปิดหน้านี้ได้เลย</p>", content_type='text/html')
        except Exception as e:
            return web.Response(text=f"<h1>System Error</h1><p>{e}</p>", content_type='text/html')
            
        return web.Response(text="<h1>Unknown Error</h1>", content_type='text/html')

class BuyBoostModal(discord.ui.Modal, title="ซื้อรหัสบูส"):
    amount = discord.ui.TextInput(label="จำนวนบัญชี (1 บัญชี = 5 บาท)", required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        try: amt = int(self.amount.value)
        except: return await interaction.response.send_message("ใส่ตัวเลข", ephemeral=True)
        
        cost = amt * 5
        if await db.get_balance(interaction.user.id) < cost: 
            return await interaction.response.send_message("เงินไม่พอ", ephemeral=True)
            
        await db.update_balance(interaction.user.id, -cost)
        code = f"222.{''.join(random.choices(string.ascii_lowercase + string.digits, k=10))}"
        
        async with aiosqlite.connect(db.DB_PATH) as db_conn:
            await db_conn.execute("INSERT INTO boost_codes (code, user_id, amount) VALUES (?, ?, ?)", (code, interaction.user.id, amt))
            await db_conn.commit()
            
        try:
            await interaction.user.send(f"นี่คือรหัสผ่าน ||`{code}`|| {code}\n\nลิ้งเชิญบอท: https://discord.com/oauth2/authorize?client_id={os.getenv('CLIENT_ID')}&permissions=8&scope=bot")
            await interaction.response.send_message("สำเร็จ รหัสส่งไปที่Dmแล้ว", ephemeral=True)
        except: 
            await interaction.response.send_message("Dm ปิดอยู่", ephemeral=True)

class BoostServerModal(discord.ui.Modal, title="บูสเซิร์ฟเวอร์"):
    guild_id = discord.ui.TextInput(label="ID เซิร์ฟเวอร์", required=True)
    code = discord.ui.TextInput(label="รหัสบูส", required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        try: gid = int(self.guild_id.value)
        except: return await interaction.response.send_message("ID ไม่ถูกต้อง", ephemeral=True)
        
        # แก้บั๊ก ID ผิด: ใช้ fetch_guild ยิงตรงไปที่ API
        try: 
            await interaction.client.fetch_guild(gid)
        except Exception: 
            return await interaction.response.send_message("ไม่สำเร็จบอทไม่อยู่ในดิสนั้นเชิญบอทก่อนน", ephemeral=True)
            
        async with aiosqlite.connect(db.DB_PATH) as db_conn:
            async with db_conn.execute("SELECT amount, used FROM boost_codes WHERE code = ? AND user_id = ?", (self.code.value, interaction.user.id)) as cursor:
                row = await cursor.fetchone()
                if not row or row[1]: 
                    return await interaction.response.send_message("รหัสผิดหรือใช้แล้ว", ephemeral=True)
                await db_conn.execute("UPDATE boost_codes SET used = 1 WHERE code = ?", (self.code.value,))
                await db_conn.commit()
                
        await interaction.response.send_message("กำลังเริ่มจอย", ephemeral=True)
        interaction.client.loop.create_task(self.process_boost(interaction.user, gid, row[0]))
        
    async def process_boost(self, user, guild_id, amount):
        joined = 0
        async with aiosqlite.connect(db.DB_PATH) as db_conn:
            async with db_conn.execute("SELECT user_id, token FROM accounts WHERE claimed = 0 AND nitro_status = 1 LIMIT ?", (amount,)) as cursor:
                for (uid, token) in await cursor.fetchall():
                    async with aiohttp.ClientSession() as session:
                        await session.put(f"https://discord.com/api/v10/guilds/{guild_id}/members/{uid}", headers={"Authorization": f"Bot {os.getenv('BOT_TOKEN')}"}, json={"access_token": token})
                        joined += 1
                    await db_conn.execute("UPDATE accounts SET claimed = 1 WHERE user_id = ?", (uid,))
                    await db_conn.commit()
        
        boosts = joined * 2
        async with aiosqlite.connect(db.DB_PATH) as db_conn:
            await db_conn.execute("UPDATE stats SET sold_boosts = sold_boosts + ? WHERE id = 1", (boosts,))
            await db_conn.commit()

        await user.send(f"สำเร็จ บัญชีทั้งหมด {joined} บูสที่บูสได้ {boosts}")

class SystemPanelView(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
        
    @discord.ui.button(label="ซื้อรหัสบูส", style=discord.ButtonStyle.success, custom_id="buy_b")
    async def buy(self, i: discord.Interaction, b: discord.ui.Button): 
        await i.response.send_modal(BuyBoostModal())
        
    @discord.ui.button(label="บูสดิส", style=discord.ButtonStyle.primary, custom_id="go_b")
    async def go(self, i: discord.Interaction, b: discord.ui.Button): 
        await i.response.send_modal(BoostServerModal())

class NitroMainView(discord.ui.View):
    def __init__(self): 
        super().__init__(timeout=None)
    
    @discord.ui.button(label="แผงระบบ", style=discord.ButtonStyle.secondary, custom_id="p1")
    async def p1(self, i: discord.Interaction, b: discord.ui.Button):
        stats = await db.get_stats()
        embed = discord.Embed(color=0x2b2d31)
        embed.description = (
            f"# <:1000039353:1560870698485022821> auto sell Boost server <:1000039353:1560870698485022821>\n"
            f"กดเติมตังที่ <#1560871774961401856> ก่อน แล้วรอเงินเข้า รับเเค่ <a:1000030144:1559280351254151199>\n\n"
            f"บัญชีละ 5 บ. ไม่ว่าจะ1เดือนหรือ3เดือน 5บ. เหมือนกันสุ่มๆเอา\n\n"
            f"<:1000039353:1560870698485022821> เหลือ {stats[0]} บัญชี <a:1000039264:1560448511588302928> ขายเเล้ว {stats[1]} บูส\n\n"
            f"หลังจากเงินเข้า กดปุ่มด้านล่าง ซื้อบูสดิส ใส่จำนวนที่จะซื้อ บัญชีละ5บาท ก็คือ5บาทจะได้2บูส หลังจากกดซื้อ บอทจะส่งรหัสเข้าไปในDm นะครับโปรดเปิดDmด้วย ส่งไปพร้อมกับลิ้งเชิญบอท ให้เชิญบอทไปที่เซิฟที่จะบูส เเล้วกลับมาที่เเผงหลัก ใส่ID เซิฟเวอร์ที่จะบูสไป เเละรอไปประมาณ2นาทีจะเริ่มบูส\n\n"
            f"<:1000035866:1559279147648290947> โปรดปิดanti botก่อนนะครับ บัญชีจะได้ไม่โดนเตะหรือเเบน จะไม่รับผิดชอบ"
        )
        embed.set_image(url="https://cdn.discordapp.com/attachments/1555167748865392701/1560874474478374943/7a7f7c254b3951e2d6aa379d5abbee53.jpg")
        # ตั้งค่าให้เห็นทุกคน (ephemeral=False)
        await i.response.send_message(embed=embed, view=SystemPanelView(), ephemeral=False)
        
    @discord.ui.button(label="รับลิ้ง", style=discord.ButtonStyle.primary, custom_id="p2")
    async def p2(self, i: discord.Interaction, b: discord.ui.Button):
        redirect = quote(os.getenv('REDIRECT_URI'))
        url = f"https://discord.com/oauth2/authorize?client_id={os.getenv('CLIENT_ID')}&response_type=code&redirect_uri={redirect}&scope=identify%20identify.premium%20guilds.join"
        embed = discord.Embed(title="เพิ่มบัญชี Nitro", description=f"[คลิกที่นี่เพื่อเข้าสู่ระบบและให้สิทธิ์บอท]({url})\n\nระบบจะรักษาสิทธิ์และต่ออายุ Token ให้ตลอด", color=0x2b2d31)
        # ตั้งค่าให้เห็นทุกคน (ephemeral=False)
        await i.response.send_message(embed=embed, ephemeral=False)
        
    @discord.ui.button(label="เช็คบัญชี", style=discord.ButtonStyle.secondary, custom_id="p3")
    async def p3(self, i: discord.Interaction, b: discord.ui.Button):
        async with aiosqlite.connect(db.DB_PATH) as c:
            async with c.execute("SELECT user_id, nitro_status, claimed FROM accounts") as cur:
                rows = await cur.fetchall()
                if not rows: 
                    return await i.response.send_message("ไม่มีบัญชีที่ให้สิทธิ์", ephemeral=True)
                embed = discord.Embed(title="รายชื่อบัญชีที่ให้สิทธิ์", color=0x2b2d31)
                for uid, n, cl in rows: 
                    embed.add_field(
                        name=f"<@{uid}>", 
                        value=f"ไนโตร: {'มี' if n else 'ไม่มี'}\nบูส: {'บูสแล้ว' if cl else 'ยังไม่ได้บูส'}", 
                        inline=False
                    )
                await i.response.send_message(embed=embed, ephemeral=True)

class Nitro(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(OAuth2Server(bot).start())
        self.bot.add_view(NitroMainView())
        self.bot.add_view(SystemPanelView())
        
    @commands.hybrid_command(name="nitro")
    async def nitro(self, ctx):
        if ctx.author.id != OWNER_ID: 
            return await ctx.send("ชั้นต่ำอยากจะใช้คำสั่งชั้นสูงรั่วว", ephemeral=True)
        await ctx.send(embed=discord.Embed(title="Nitro System", color=0x2b2d31), view=NitroMainView(), ephemeral=True)

async def setup(bot): 
    await bot.add_cog(Nitro(bot))