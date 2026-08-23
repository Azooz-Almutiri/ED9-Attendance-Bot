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
    return web.Response(text="GodFather Bot is running alive!")

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

# نظام تسجيل الدخول العام
class SimpleAttendanceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="بدء التحضير 🟢", style=discord.ButtonStyle.green, custom_id="start_simple_attendance")
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
                             (user.id, user.display_name, "عضو", now.isoformat()))
            await db.commit()

        await interaction.followup.send(f"✅ تم تسجيل دخولك الساعة `{now.strftime('%I:%M %p')}`", ephemeral=True)

    @discord.ui.button(label="إنهاء التحضير 🔴", style=discord.ButtonStyle.red, custom_id="end_simple_attendance")
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

    @discord.ui.button(label="حالة تحضيري ⏱️", style=discord.ButtonStyle.secondary, custom_id="status_simple_attendance")
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
        self.add_view(SimpleAttendanceView())

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
    try:
        synced = await bot.tree.sync()
        print(f"✅ Global sync: {len(synced)} commands registered.")
    except Exception as e:
        print(f"❌ Failed to global sync: {e}")

# أمر تزامن يدوي إجباري
@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def sync(ctx):
    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"✅ تم تزامن {len(synced)} أمر مباشرة مع هذا السيرفر!")

# ==================== أوامر الخزائن والجرد المباشر ====================

# 1️⃣ أمر جرد خزنة الحداد (كتابة يدوي)
@bot.tree.command(name="inventory", description="إرسال جرد لخزنة الحداد")
@app_commands.describe(
    item_1="اسم المورد الأول", amount_1="الكمية",
    item_2="اسم المورد الثاني (اختياري)", amount_2="الكمية",
    item_3="اسم المورد الثالث (اختياري)", amount_3="الكمية",
    item_4="اسم المورد الرابع (اختياري)", amount_4="الكمية",
    item_5="اسم المورد الخامس (اختياري)", amount_5="الكمية"
)
async def inventory(
    interaction: discord.Interaction,
    item_1: str, amount_1: int,
    item_2: str = None, amount_2: int = 0,
    item_3: str = None, amount_3: int = 0,
    item_4: str = None, amount_4: int = 0,
    item_5: str = None, amount_5: int = 0
):
    await interaction.response.defer()
    items_list = [(item_1, amount_1), (item_2, amount_2), (item_3, amount_3), (item_4, amount_4), (item_5, amount_5)]
    
    text = "📋 **خزنة الحداد**\n\n"
    for name, qty in items_list:
        if name:
            text += f"• **{name} :** {qty:,}\n\n"
            
    await interaction.followup.send(text)

# 2️⃣ أمر جرد خزنة الستور (كتابة يدوي)
@bot.tree.command(name="store_inv", description="إرسال جرد لخزنة الستور")
@app_commands.describe(
    item_1="اسم الغرض الأول", amount_1="الكمية",
    item_2="اسم الغرض الثاني (اختياري)", amount_2="الكمية",
    item_3="اسم الغرض الثالث (اختياري)", amount_3="الكمية",
    item_4="اسم الغرض الرابع (اختياري)", amount_4="الكمية",
    item_5="اسم الغرض الخامس (اختياري)", amount_5="الكمية"
)
async def store_inv(
    interaction: discord.Interaction,
    item_1: str, amount_1: int,
    item_2: str = None, amount_2: int = 0,
    item_3: str = None, amount_3: int = 0,
    item_4: str = None, amount_4: int = 0,
    item_5: str = None, amount_5: int = 0
):
    await interaction.response.defer()
    items_list = [(item_1, amount_1), (item_2, amount_2), (item_3, amount_3), (item_4, amount_4), (item_5, amount_5)]
    
    text = "📋 **خزنة الستور**\n\n"
    for name, qty in items_list:
        if name:
            text += f"• **{name} :** {qty:,}\n\n"
            
    await interaction.followup.send(text)

# 3️⃣ أمر جرد خزنة الأسلحة (كتابة يدوي)
@bot.tree.command(name="weapons_inv", description="إرسال جرد لخزنة محل الأسلحة")
@app_commands.describe(
    item_1="اسم السلاح/الذخيرة الأول", amount_1="الكمية",
    item_2="اسم السلاح/الذخيرة الثاني (اختياري)", amount_2="الكمية",
    item_3="اسم السلاح/الذخيرة الثالث (اختياري)", amount_3="الكمية",
    item_4="اسم السلاح/الذخيرة الرابع (اختياري)", amount_4="الكمية",
    item_5="اسم السلاح/الذخيرة الخامس (اختياري)", amount_5="الكمية"
)
async def weapons_inv(
    interaction: discord.Interaction,
    item_1: str, amount_1: int,
    item_2: str = None, amount_2: int = 0,
    item_3: str = None, amount_3: int = 0,
    item_4: str = None, amount_4: int = 0,
    item_5: str = None, amount_5: int = 0
):
    await interaction.response.defer()
    items_list = [(item_1, amount_1), (item_2, amount_2), (item_3, amount_3), (item_4, amount_4), (item_5, amount_5)]
    
    text = "📋 **خزنة محل الاسلحة**\n\n"
    for name, qty in items_list:
        if name:
            text += f"• **{name} :** {qty:,}\n\n"
            
    await interaction.followup.send(text)

# 4️⃣ أمر جرد خزنة الحانة (كتابة يدوي)
@bot.tree.command(name="bar_inv", description="إرسال جرد لخزنة الحانة")
@app_commands.describe(
    item_1="اسم المشروب/الغرض الأول", amount_1="الكمية",
    item_2="اسم المشروب/الغرض الثاني (اختياري)", amount_2="الكمية",
    item_3="اسم المشروب/الغرض الثالث (اختياري)", amount_3="الكمية",
    item_4="اسم المشروب/الغرض الرابع (اختياري)", amount_4="الكمية",
    item_5="اسم المشروب/الغرض الخامس (اختياري)", amount_5="الكمية"
)
async def bar_inv(
    interaction: discord.Interaction,
    item_1: str, amount_1: int,
    item_2: str = None, amount_2: int = 0,
    item_3: str = None, amount_3: int = 0,
    item_4: str = None, amount_4: int = 0,
    item_5: str = None, amount_5: int = 0
):
    await interaction.response.defer()
    items_list = [(item_1, amount_1), (item_2, amount_2), (item_3, amount_3), (item_4, amount_4), (item_5, amount_5)]
    
    text = "📋 **خزنة الحانة**\n\n"
    for name, qty in items_list:
        if name:
            text += f"• **{name} :** {qty:,}\n\n"
            
    await interaction.followup.send(text)

# ==================== الأوامر العامة والتعريفية ====================

# أمر الخيول المتوفرة
@bot.tree.command(name="horses", description="إرسال قائمة الخيول المتوفرة لدى عائلة القودفاذر")
async def horses(interaction: discord.Interaction):
    await interaction.response.defer()
    horses_text = (
        "📢 **الخيول المتوفرة لدى العائلة**\n\n"
        "يسرنا إبلاغكم بأن الخيول المتوفرة حالياً لدى العائلة هي:\n\n"
        "🐎 **شاير — الأبيض والأسود**\n"
        "🐎 **تركماني — الأبيض**\n"
        "🐎 **ميسوري فوكس تروتر — الأزرق (Blue)**\n"
        "🐎 **الخيل العربي — أصيل (مختلف الألوان)**\n\n"
        "📨 **لطلب الخيول، يرجى فتح تذكرة والتواصل مع المسؤولين، وسيتم متابعة طلبكم حسب التوفر.**\n\n"
        "@everyone"
    )
    await interaction.followup.send(horses_text)

# أمر إمبد خزنة الحداد
@bot.tree.command(name="blacksmith", description="عرض خزنة الحداد")
async def blacksmith(interaction: discord.Interaction):
    embed = discord.Embed(title="🔨 خزنة الحداد - GODFATHER FAMILY", color=discord.Color.dark_gray())
    embed.description = "قائمة الموارد والمعادن المخصصة للحدادة والتصنيع."
    await interaction.response.send_message(embed=embed)

# أمر إمبد خزنة محل الأسلحة
@bot.tree.command(name="weapons", description="عرض خزنة محل الأسلحة")
async def weapons(interaction: discord.Interaction):
    embed = discord.Embed(title="⚔️ خزنة محل الاسلحة - GODFATHER FAMILY", color=discord.Color.dark_red())
    embed.description = "قائمة الذخائر والأسلحة المتوفرة في الخزنة."
    await interaction.response.send_message(embed=embed)

# أمر إمبد خزنة الستور
@bot.tree.command(name="store", description="عرض خزنة الستور")
async def store(interaction: discord.Interaction):
    embed = discord.Embed(title="🛒 خزنة الستور - GODFATHER FAMILY", color=discord.Color.gold())
    embed.description = "قائمة الأغراض والمنتجات المتاحة للشراء أو التوزيع."
    await interaction.response.send_message(embed=embed)

# أمر إمبد خزنة الحانة
@bot.tree.command(name="bar", description="عرض خزنة الحانة")
async def bar(interaction: discord.Interaction):
    embed = discord.Embed(title="🍺 خزنة الحانة - GODFATHER FAMILY", color=discord.Color.dark_purple())
    embed.description = "قائمة المشروبات والمستلزمات الخاصة بالحانة."
    await interaction.response.send_message(embed=embed)

# أمر التقديم
@bot.tree.command(name="apply", description="عرض طريقة التقديم للانضمام لعائلة القودفاذر")
async def apply(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 التقديم على عائلة GODFATHER", color=discord.Color.red())
    embed.description = "مرحباً بك! للانضمام إلى العائلة، يرجى فتح تذكرة تقديم وتعبئة البيانات المطلوبة ليتم مراجعتها من قبل الإدارة."
    await interaction.response.send_message(embed=embed)

# أمر تنزيل لوحة التحضير
@bot.tree.command(name="setup_attendance", description="تنزيل لوحة التحضير الموقتة للعائلة")
@app_commands.checks.has_permissions(administrator=True)
async def setup_attendance(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    embed = discord.Embed(title="⏱️ تحضير عائلة GODFATHER", description="اضغط الأزرار بالأسفل لتسجيل الدخول أو الخروج", color=discord.Color.red())
    await interaction.channel.send(embed=embed, view=SimpleAttendanceView())
    await interaction.followup.send("تم إرسال لوحة التحضير بنجاح!", ephemeral=True)

# ==================== الأوامر الإدارية وسجلات الحضور ====================

@bot.tree.command(name="add_hours", description="إضافة ساعات تحضير يدوياً لعضو")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    user="العضو المراد إضافة الساعات له",
    hours="عدد الساعات المراد إضافتها",
    minutes="عدد الدقائق المراد إضافتها (اختياري)"
)
async def add_hours(interaction: discord.Interaction, user: discord.Member, hours: int = 0, minutes: int = 0):
    await interaction.response.defer()
    total_added_minutes = (hours * 60) + minutes

    if total_added_minutes <= 0:
        await interaction.followup.send("❌ يجب أن تدخل عدداً أكبر من صفر للساعات أو الدقائق!", ephemeral=True)
        return

    now = datetime.now()
    fake_start_time = now - timedelta(minutes=total_added_minutes)

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO attendance (user_id, user_name, type, start_time, end_time, duration_minutes) VALUES (?, ?, ?, ?, ?, ?)",
            (user.id, user.display_name, "عضو", fake_start_time.isoformat(), now.isoformat(), total_added_minutes)
        )
        await db.commit()

    embed = discord.Embed(
        title="➕ تم إضافة ساعات تحضير",
        description=f"تمت إضافة **{hours}** ساعة و **{minutes}** دقيقة إلى حساب {user.mention} بنجاح!",
        color=discord.Color.green()
    )
    embed.add_field(name="المشرف المسؤول", value=interaction.user.mention, inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="active_now", description="عرض المسجلين دخول حالياً")
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
        embed.add_field(name=f"{name}", value=f"⏱️ متواجد منذ: `{h} ساعة و {m} دقيقة`", inline=False)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="force_checkout", description="طرد أو إنهاء تحضير عضو مسجل دخول")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="العضو المراد إنهاء تحضيره", save_time="هل تريد احتساب الساعات أم إلغائها؟")
@app_commands.choices(save_time=[
    app_commands.Choice(name="حفظ الساعات التي قضاها", value="yes"),
    app_commands.Choice(name="إلغاء الجلسة بدون احتساب ساعات", value="no")
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
        embed.add_field(name=f"👤 {data['name']}", value=field_value, inline=False)

    await interaction.followup.send(embed=embed)

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
