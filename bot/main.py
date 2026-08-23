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

# نظام تسجيل الدخول العام (مؤقتاً بدون أفراد وضباط)
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

# أمر تزامن يدوي إجباري لربط جميع السلاش كمند بالسيرفر فوراً
@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def sync(ctx):
    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"✅ تم تزامن {len(synced)} أمر مباشرة مع هذا السيرفر!")

# ==================== الأوامر الجديدة الخاصة بعائلة GODFATHER ====================

# 1️⃣ أمر جرد الموارد المباشر
@bot.tree.command(name="inventory", description="إرسال جرد كامل للموارد بقيم محددة")
@app_commands.describe(
    fibers="ألياف نباتية",
    oil_barrels="برميل نفت",
    sandstone="حجر رملي",
    gold_shoes="حذوات ذهبيه",
    iron_ore="خام الحديد",
    quartz_ore="خام الكوارتز",
    copper_ore="خام النحاس",
    ruby_ore="خام الياقوت",
    steel_ore="خام فولاذ",
    wood="خشب"
)
async def inventory(
    interaction: discord.Interaction,
    fibers: int = 0,
    oil_barrels: int = 0,
    sandstone: int = 0,
    gold_shoes: int = 0,
    iron_ore: int = 0,
    quartz_ore: int = 0,
    copper_ore: int = 0,
    ruby_ore: int = 0,
    steel_ore: int = 0,
    wood: int = 0
):
    await interaction.response.defer()
    inventory_text = (
        f"📋 **خزنة الحداد**\n\n"
        f"• **ألياف نباتية :** {fibers:,}\n\n"
        f"• **برميل نفت :** {oil_barrels:,}\n\n"
        f"• **حجر رملي :** {sandstone:,}\n\n"
        f"• **حذوات ذهبيه :** {gold_shoes:,}\n\n"
        f"• **خام الحديد :** {iron_ore:,}\n\n"
        f"• **خام الكوارتز :** {quartz_ore:,}\n\n"
        f"• **خام النحاس :** {copper_ore:,}\n\n"
        f"• **خام الياقوت :** {ruby_ore:,}\n\n"
        f"• **خام فولاذ :** {steel_ore:,}\n\n"
        f"• **خشب :** {wood:,}"
    )
    await interaction.followup.send(inventory_text)

# 2️⃣ أمر الخيول المتوفرة
@bot.tree.command(name="horses", description="إرسال قائمة الخيول المتوفرة لدى عائلة القودفاذر")
async def horses(interaction: discord.Interaction):
    await interaction.response.defer()
    horses_text = (
        "📢 **الخيول المتوفرة لدى العائلة**\n\n"
        ":يسرنا إبلاغكم بأن الخيول المتوفرة حالياً لدى العائلة هي\n\n"
        "🐎 **شاير — الأبيض والأسود**\n"
        "🐎 **تركماني — الأبيض**\n"
        "🐎 **ميسوري فوكس تروتر — الأزرق (Blue)**\n\n"
        "📨 **لطلب الخيول، يرجى فتح تذكرة والتواصل مع المسؤولين، وسيتم متابعة طلبكم حسب التوفر.**\n\n"
        "@everyone"
    )
    await interaction.followup.send(horses_text)

# 3️⃣ أمر مخزن الحداد
@bot.tree.command(name="blacksmith", description="عرض مخزن الحداد")
async def blacksmith(interaction: discord.Interaction):
    embed = discord.Embed(title="🔨 مخزن الحداد - GODFATHER FAMILY", color=discord.Color.dark_gray())
    embed.description = "قائمة الموارد والمعادن المخصصة للحدادة والتصنيع."
    await interaction.response.send_message(embed=embed)

# 4️⃣ أمر مخزن الأسلحة
@bot.tree.command(name="weapons", description="عرض مخزن الأسلحة")
async def weapons(interaction: discord.Interaction):
    embed = discord.Embed(title="⚔️ مخزن الأسلحة - GODFATHER FAMILY", color=discord.Color.dark_red())
    embed.description = "قائمة الذخائر والأسلحة المتوفرة في المخزن."
    await interaction.response.send_message(embed=embed)

# 5️⃣ أمر متجر العائلة
@bot.tree.command(name="store", description="عرض متجر العائلة")
async def store(interaction: discord.Interaction):
    embed = discord.Embed(title="🛒 متجر العائلة - GODFATHER FAMILY", color=discord.Color.gold())
    embed.description = "قائمة الأغراض والمنتجات المتاحة للشراء أو التوزيع."
    await interaction.response.send_message(embed=embed)

# 6️⃣ أمر مخزن الحانة
@bot.tree.command(name="bar", description="عرض مخزن الحانة")
async def bar(interaction: discord.Interaction):
    embed = discord.Embed(title="🍺 مخزن الحانة - GODFATHER FAMILY", color=discord.Color.dark_purple())
    embed.description = "قائمة المشروبات والمستلزمات الخاصة بالحانة."
    await interaction.response.send_message(embed=embed)

# 7️⃣ أمر التقديم على العائلة
@bot.tree.command(name="apply", description="عرض طريقة التقديم للانضمام لعائلة القودفاذر")
async def apply(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 التقديم على عائلة GODFATHER", color=discord.Color.red())
    embed.description = "مرحباً بك! للانضمام إلى العائلة، يرجى فتح تذكرة تقديم وتعبئة البيانات المطلوبة ليتم مراجعتها من قبل الإدارة."
    await interaction.response.send_message(embed=embed)

# 8️⃣ أمر تنزيل لوحة التحضير الموقتة العامة
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
