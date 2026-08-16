import os
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from datetime import datetime, timedelta
from aiohttp import web

# إعداد قاعدة البيانات
DB_NAME = "attendance.db"

# دالة الاستجابة لطلبات UptimeRobot و Render
async def handle(request):
    return web.Response(text="Bot is running alive!")

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                user_id INTEGER,
                user_name TEXT,
                type TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                duration_minutes INTEGER DEFAULT 0
            )
        ''')
        await db.commit()

class AttendanceView(discord.ui.View):
    def __init__(self, role_type: str):
        super().__init__(timeout=None)
        self.role_type = role_type

    @discord.ui.button(label="بدء التحضير", style=discord.ButtonStyle.green, custom_id="start_attendance")
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        now = datetime.now()

        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT start_time FROM attendance WHERE user_id = ? AND end_time IS NULL", (user.id,)) as cursor:
                active_session = await cursor.fetchone()

            if active_session:
                await interaction.followup.send("❌ أنت مسجل دخول بالفعل!", ephemeral=True)
                return

            await db.execute("INSERT INTO attendance (user_id, user_name, type, start_time) VALUES (?, ?, ?, ?)",
                             (user.id, user.display_name, self.role_type, now.isoformat()))
            await db.commit()

        await interaction.followup.send(f"✅ تم تسجيل دخولك كـ ({self.role_type}) الساعة `{now.strftime('%I:%M %p')}`", ephemeral=True)

    @discord.ui.button(label="إنهاء التحضير", style=discord.ButtonStyle.red, custom_id="end_attendance")
    async def end_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        now = datetime.now()

        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT rowid, start_time FROM attendance WHERE user_id = ? AND end_time IS NULL", (user.id,)) as cursor:
                active_session = await cursor.fetchone()

            if not active_session:
                await interaction.followup.send("❌ أنت غير مسجل دخول حالياً!", ephemeral=True)
                return

            row_id, start_str = active_session
            start_time = datetime.fromisoformat(str(start_str))
            duration = int((now - start_time).total_seconds() // 60)

            await db.execute("UPDATE attendance SET end_time = ?, duration_minutes = ? WHERE rowid = ?", (now.isoformat(), duration, row_id))
            await db.commit()

        hours, mins = divmod(duration, 60)
        await interaction.followup.send(f"🔴 تم تسجيل خروجك. مدة تواجدك: `{hours} ساعة و {mins} دقيقة`", ephemeral=True)

    @discord.ui.button(label="حالة تحضيري ⏱️", style=discord.ButtonStyle.secondary, custom_id="status_attendance")
    async def status_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        user = interaction.user
        now = datetime.now()

        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT start_time FROM attendance WHERE user_id = ? AND end_time IS NULL", (user.id,)) as cursor:
                active_session = await cursor.fetchone()

            five_days_ago = (now - timedelta(days=5)).isoformat()
            async with db.execute("SELECT SUM(duration_minutes) FROM attendance WHERE user_id = ? AND start_time >= ?", (user.id, five_days_ago)) as cursor:
                weekly_minutes = (await cursor.fetchone())[0] or 0

        w_hours, w_mins = divmod(weekly_minutes, 60)

        if active_session:
            start_time = datetime.fromisoformat(str(active_session[0]))
            curr_duration = int((now - start_time).total_seconds() // 60)
            c_hours, c_mins = divmod(curr_duration, 60)
            
            msg = (f"🟢 **حالتك الحالية:** مسجل دخول\n"
                   f"⏱️ **مدة التواجد الحالية:** {c_hours} ساعة و {c_mins} دقيقة\n"
                   f"📊 **إجمالي ساعاتك لآخر 5 أيام:** {w_hours} ساعة و {w_mins} دقيقة")
        else:
            msg = (f"🔴 **حالتك الحالية:** غير مسجل دخول\n"
                   f"📊 **إجمالي ساعاتك لآخر 5 أيام:** {w_hours} ساعة و {w_mins} دقيقة")

        await interaction.followup.send(msg, ephemeral=True)


class AttendanceBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        self.add_view(AttendanceView("أفراد"))
        self.add_view(AttendanceView("ضباط"))
        await self.tree.sync()

        app = web.Application()
        app.router.add_get('/', handle)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 8080))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        print(f"Web server started on port {port}")

bot = AttendanceBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")

# أوامر تنزيل التحضير
@bot.tree.command(name="setup_individuals", description="تنزيل تحضير الأفراد")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ind(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title="📋 تحضير الأفراد", description="اضغط الأزرار بالأسفل لتسجيل الدخول أو الخروج", color=discord.Color.blue())
    await interaction.channel.send(embed=embed, view=AttendanceView("أفراد"))
    await interaction.followup.send("تم إرسال التحضير بنجاح!", ephemeral=True)

@bot.tree.command(name="setup_officers", description="تنزيل تحضير الضباط")
@app_commands.checks.has_permissions(administrator=True)
async def setup_off(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title="👮‍♂️ تحضير الضباط", description="اضغط الأزرار بالأسفل لتسجيل الدخول أو الخروج", color=discord.Color.gold())
    await interaction.channel.send(embed=embed, view=AttendanceView("ضباط"))
    await interaction.followup.send("تم إرسال التحضير بنجاح!", ephemeral=True)

# أمر عرض المتواجدين حالياً
@bot.tree.command(name="active_now", description="عرض المسجلين دخول حالياً ومدة تواجدهم")
@app_commands.checks.has_permissions(administrator=True)
async def active_now(interaction: discord.Interaction):
    await interaction.response.defer()
    now = datetime.now()
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_name, type, start_time FROM attendance WHERE end_time IS NULL") as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await interaction.followup.send("لا يوجد أي شخص مسجل دخول حالياً.", ephemeral=True)
        return

    embed = discord.Embed(title="🟢 قائمة المتواجدين حالياً", color=discord.Color.green())
    for name, r_type, start_str in rows:
        start_time = datetime.fromisoformat(str(start_str))
        duration = int((now - start_time).total_seconds() // 60)
        h, m = divmod(duration, 60)
        embed.add_field(name=f"{name} ({r_type})", value=f"⏱️ متواجد منذ: `{h} ساعة و {m} دقيقة`", inline=False)

    await interaction.followup.send(embed=embed)

# 🔨 أمر طرد أو إخراج عضو مسجل دخول حالياً (إداري)
@bot.tree.command(name="force_checkout", description="طرد أو إنهاء تحضير عضو مسجل دخول")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="العضو المراد إنهاء تحضيره", save_time="هل تريد احتساب الساعات أم إلغائها؟")
@app_commands.choices(save_time=[
    app_commands.Choice(name="حفظ الساعات التي قضاها", value="yes"),
    app_commands.Choice(name="إلغاء الجلسة بدون احتساب ساعات (طرد بسبب اللعب)", value="no")
])
async def force_checkout(interaction: discord.Interaction, user: discord.Member, save_time: str = "yes"):
    await interaction.response.defer()
    now = datetime.now()

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT rowid, start_time, type FROM attendance WHERE user_id = ? AND end_time IS NULL", (user.id,)) as cursor:
            active_session = await cursor.fetchone()

        if not active_session:
            await interaction.followup.send(f"❌ العضو {user.mention} غير مسجل دخول حالياً!", ephemeral=True)
            return

        row_id, start_str, r_type = active_session

        if save_time == "yes":
            start_time = datetime.fromisoformat(str(start_str))
            duration = int((now - start_time).total_seconds() // 60)
            await db.execute("UPDATE attendance SET end_time = ?, duration_minutes = ? WHERE rowid = ?", (now.isoformat(), duration, row_id))
            await db.commit()
            hours, mins = divmod(duration, 60)
            msg = f"🚨 **إنهاء تحضير:** تم إنهاء جلسة {user.mention} بواسطة الإدارة.\n⏱️ **مدة الجلسة المحسوبة:** `{hours} ساعة و {mins} دقيقة`"
        else:
            await db.execute("DELETE FROM attendance WHERE rowid = ?", (row_id,))
            await db.commit()
            msg = f"⛔ **طرد وإلغاء تحضير:** تم إخراج {user.mention} وإلغاء الجلسة الحالية بدون احتساب أي ساعات!"

    embed = discord.Embed(title="إجراء إداري", description=msg, color=discord.Color.red())
    await interaction.followup.send(embed=embed)

# أمر الجرد والتفاصيل لآخر 5 أيام
@bot.tree.command(name="stats_weekly", description="عرض تفاصيل الحضور اليومية لآخر 5 أيام")
@app_commands.checks.has_permissions(administrator=True)
async def stats_weekly(interaction: discord.Interaction):
    await interaction.response.defer()
    
    five_days_ago = (datetime.now() - timedelta(days=5)).isoformat()
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("""
            SELECT user_id, user_name, type, start_time, duration_minutes 
            FROM attendance 
            WHERE start_time >= ? AND duration_minutes > 0
            ORDER BY start_time DESC
        """, (five_days_ago,)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await interaction.followup.send("لا توجد سجلات حضور خلال الـ 5 أيام الأخيرة.", ephemeral=True)
        return

    user_data = {}
    for u_id, u_name, r_type, start_str, duration in rows:
        log_date = str(start_str).split("T")[0].split(" ")[0]
        if u_id not in user_data:
            user_data[u_id] = {
                'name': u_name,
                'type': r_type,
                'dates': {},
                'total_mins': 0
            }
        
        dur = duration or 0
        user_data[u_id]['dates'][log_date] = user_data[u_id]['dates'].get(log_date, 0) + dur
        user_data[u_id]['total_mins'] += dur

    embed = discord.Embed(title="📊 إحصائيات الحضور التفصيلية (آخر 5 أيام)", color=discord.Color.purple())

    for u_id, data in user_data.items():
        tot_hrs, tot_mins = divmod(data['total_mins'], 60)
        
        details = ""
        for date_str, mins in sorted(data['dates'].items(), reverse=True):
            d_hrs, d_mins = divmod(mins, 60)
            details += f"• `{date_str}`: **{d_hrs}** ساعة و **{d_mins}** دقيقة\n"

        field_value = f"**المجموع:** `{tot_hrs} ساعة و {tot_mins} دقيقة` (في {len(data['dates'])} أيام)\n{details}"
        embed.add_field(name=f"👤 {data['name']} [{data['type']}]", value=field_value, inline=False)

    await interaction.followup.send(embed=embed)

# 🧹 أمر التصفير اليدوي لجميع السجلات (إداري)
@bot.tree.command(name="reset_stats", description="تصفير ومسح جميع سجلات الحضور يدوياً")
@app_commands.checks.has_permissions(administrator=True)
async def reset_stats(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM attendance")
        await db.commit()
    await interaction.followup.send("🧹 تم مسح وتصفير جميع سجلات الحضور بنجاح!", ephemeral=True)

# تشغيل البوت
TOKEN = os.environ.get("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
