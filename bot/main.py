import os
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from datetime import datetime, timezone, timedelta
from aiohttp import web
import asyncio

# ==================== إعدادات التوقيت (توقيت مكة المكرمة UTC+3) ====================
MAKKAH_TZ = timezone(timedelta(hours=3))

def get_makkah_now():
    return datetime.now(MAKKAH_TZ)

def format_makkah_time(dt_obj):
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc).astimezone(MAKKAH_TZ)
    else:
        dt_obj = dt_obj.astimezone(MAKKAH_TZ)
    return dt_obj.strftime("%d-%m-%Y %I:%M %p").replace("AM", "صباحاً").replace("PM", "مساءً")

DB_NAME = "godfather_jobs.db"

# ==================== الثوابت والمعرفات المطلوبة ====================
BROADCAST_ROLE_ID = 1550542997010251927      # رتبة استلام البرودكاست
WELCOME_ROLE_ID = 1550543013317447680        # الرول الذي يعطى للعضو عند دخوله
RULES_CHANNEL_ID = 1550543164723564636       # روم القوانين
APPLY_CHANNEL_ID = 1550543173300781116       # روم طلب التقديم
WELCOME_CHANNEL_ID = 1550543159321427978    # روم الترحيب
ATTENDANCE_CHANNEL_ID = 1552244246764064818  # روم تحضير RedM

CHECK_INTERVAL = 3600         # التحقق كل ساعة
CONFIRM_TIMEOUT = 600         # 10 دقائق مهلة للرد

periodic_check_tasks = {}

# ==================== تهيئة قاعدة البيانات ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS horses (
                horse_name TEXT PRIMARY KEY,
                added_by TEXT,
                added_at TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS horse_breeding (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                horse_name TEXT,
                breed_type TEXT,
                horse_age TEXT,
                mating_time TEXT,
                ready_time TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS redm_attendance (
                user_id INTEGER,
                user_name TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                duration_minutes INTEGER DEFAULT 0,
                points_earned INTEGER DEFAULT 0
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS member_points (
                user_id INTEGER PRIMARY KEY,
                user_name TEXT,
                total_points INTEGER DEFAULT 0
            )
        ''')
        await db.commit()

# ==================== سيرفر الويب للبوت ====================
async def handle(request):
    return web.Response(text="Godfather Bot is running alive!")

class GodfatherBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        self.add_view(RedMAttendanceView(self))
        app = web.Application()
        app.router.add_get('/', handle)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 10000))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()

bot = GodfatherBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"❌ Failed to sync: {e}")

# ==================== نظام الترحيب التلقائي بالأعضاء الجدد ====================
recent_joined = set()

@bot.event
async def on_member_join(member: discord.Member):
    if member.id in recent_joined:
        return
    recent_joined.add(member.id)
    asyncio.create_task(remove_recent(member.id))

    role = member.guild.get_role(WELCOME_ROLE_ID)
    if role:
        try:
            await member.add_roles(role)
        except Exception:
            pass

    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        apply_channel = member.guild.get_channel(APPLY_CHANNEL_ID)
        rules_channel = member.guild.get_channel(RULES_CHANNEL_ID)
        
        apply_mention = apply_channel.mention if apply_channel else "#طلب-التقديم"
        rules_mention = rules_channel.mention if rules_channel else "#القوانين"

        embed = discord.Embed(
            title="👋 حياك الله في عائلة القودفاذرز!",
            description=f"مرحباً بك {member.mention} نورت السيرفر.\n\n"
                        f"📜 نرجو منك قراءة قوانين السيرفر بتمعن في {rules_mention}.\n"
                        f"🤝 إذا كنت تبي تنضم لعائلتنا وتقدم طلبك، توجه وحط طلبك في {apply_mention}.",
            color=discord.Color.gold(),
            timestamp=get_makkah_now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(content=member.mention, embed=embed)

async def remove_recent(member_id):
    await asyncio.sleep(10)
    recent_joined.discard(member_id)

# ==================== أمر البرودكاست المخصص ====================
@bot.command(name="bc")
async def broadcast_cmd(ctx, *, message_content: str = None):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    if not message_content:
        await ctx.send("❌ يرجى كتابة الرسالة المراد إرسالها بعد الأمر!\nمثال: `!bc السلام عليكم حياكم الله`", delete_after=6)
        return

    target_role = ctx.guild.get_role(BROADCAST_ROLE_ID)
    if not target_role:
        await ctx.send("❌ عذراً، رتبة استقبال البرودكاست المحددة غير موجودة في السيرفر!", delete_after=6)
        return

    status_msg = await ctx.send(f"⏳ جاري إرسال البرودكاست لأصحاب رتبة ({target_role.name})...")
    sent, failed = 0, 0

    for member in target_role.members:
        if member.bot:
            continue
        try:
            await member.send(message_content)
            sent += 1
            await asyncio.sleep(0.1)
        except Exception:
            failed += 1

    await status_msg.edit(content=f"✅ تم الانتهاء من إرسال البرودكاست!\n📤 تم الإرسال لـ {sent} عضو\n❌ تعذر الإرسال لـ {failed} عضو (خاص مقفل)")

# ==================== نظام تحضير RedM التفاعلي والنقاط ====================
class ConfirmRedMView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=CONFIRM_TIMEOUT)
        self.user_id = user_id
        self.confirmed = False

    @discord.ui.button(label="تأكيد التواجد 🟢", style=discord.ButtonStyle.green, custom_id="confirm_redm_presence")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ هذا التنبيه ليس مخصصاً لك!", ephemeral=True)
            return

        self.confirmed = True
        button.disabled = True
        button.label = "تم التأكيد ✅"
        await interaction.response.defer()
        self.stop()
        try:
            await interaction.message.delete()
        except Exception:
            pass

async def start_redm_periodic_check(bot_client, member: discord.Member):
    try:
        while True:
            await asyncio.sleep(CHECK_INTERVAL)
            async with aiosqlite.connect(DB_NAME) as db:
                async with db.execute("SELECT rowid, start_time FROM redm_attendance WHERE user_id = ? AND end_time IS NULL", (member.id,)) as cursor:
                    active_session = await cursor.fetchone()

            if not active_session:
                break

            channel = bot_client.get_channel(ATTENDANCE_CHANNEL_ID)
            if not channel:
                break

            view = ConfirmRedMView(member.id)
            try:
                msg = await channel.send(
                    f"⚠️ {member.mention} **تأكيد حضور دوري:**\n"
                    "لقد مرت ساعة على تواجدك في التحضير. هل ما زلت متصلاً؟\n"
                    "يرجى الضغط على الزر أدناه خلال **10 دقائق** لتأكيد تواجدك، وإلا سيتم تسجيل خروجك تلقائياً.",
                    view=view
                )
            except Exception:
                pass

            await view.wait()

            if not view.confirmed:
                now = get_makkah_now()
                row_id, start_str = active_session
                duration = max(0, int((now - datetime.fromisoformat(str(start_str))).total_seconds() // 60))
                earned_points = duration // 60

                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE redm_attendance SET end_time = ?, duration_minutes = ?, points_earned = ? WHERE rowid = ?", 
                                     (now.isoformat(), duration, earned_points, row_id))
                    if earned_points > 0:
                        await db.execute('''
                            INSERT INTO member_points (user_id, user_name, total_points) VALUES (?, ?, ?)
                            ON CONFLICT(user_id) DO UPDATE SET total_points = total_points + ?, user_name = ?
                        ''', (member.id, member.display_name, earned_points, earned_points, member.display_name))
                    await db.commit()
                break
    except asyncio.CancelledError:
        pass
    finally:
        periodic_check_tasks.pop(member.id, None)

class RedMAttendanceView(discord.ui.View):
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot = bot_instance

    @discord.ui.button(label="دخول RedM", style=discord.ButtonStyle.green, custom_id="redm_start_btn")
    async def start_redm(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        now = get_makkah_now()

        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT start_time FROM redm_attendance WHERE user_id = ? AND end_time IS NULL", (user.id,)) as cursor:
                active_session = await cursor.fetchone()

            if active_session:
                await interaction.response.send_message("❌ أنت مسجل دخول في RedM بالفعل!", ephemeral=True)
                return

            await db.execute("INSERT INTO redm_attendance (user_id, user_name, start_time) VALUES (?, ?, ?)",
                             (user.id, user.display_name, now.isoformat()))
            await db.commit()

        if user.id in periodic_check_tasks:
            periodic_check_tasks[user.id].cancel()

        periodic_check_tasks[user.id] = asyncio.create_task(start_redm_periodic_check(self.bot, user))
        await interaction.response.send_message(f"✅ تم تسجيل دخولك في RedM بنجاح الساعة `{format_makkah_time(now)}`.", ephemeral=True)

    @discord.ui.button(label="خروج RedM", style=discord.ButtonStyle.red, custom_id="redm_end_btn")
    async def end_redm(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        now = get_makkah_now()

        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT rowid, start_time FROM redm_attendance WHERE user_id = ? AND end_time IS NULL", (user.id,)) as cursor:
                active_session = await cursor.fetchone()

            if not active_session:
                await interaction.response.send_message("❌ أنت غير مسجل دخول في RedM حالياً!", ephemeral=True)
                return

            row_id, start_str = active_session
            duration = max(0, int((now - datetime.fromisoformat(str(start_str))).total_seconds() // 60))
            earned_points = duration // 60

            await db.execute("UPDATE redm_attendance SET end_time = ?, duration_minutes = ?, points_earned = ? WHERE rowid = ?", 
                             (now.isoformat(), duration, earned_points, row_id))
            
            if earned_points > 0:
                await db.execute('''
                    INSERT INTO member_points (user_id, user_name, total_points) VALUES (?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET total_points = total_points + ?, user_name = ?
                ''', (user.id, user.display_name, earned_points, earned_points, user.display_name))
            
            await db.commit()

        if user.id in periodic_check_tasks:
            periodic_check_tasks[user.id].cancel()
        periodic_check_tasks.pop(user.id, None)

        hours, mins = divmod(duration, 60)
        await interaction.response.send_message(f"🔴 تم تسجيل خروجك من RedM. مدة تواجدك: `{hours} ساعة و {mins} دقيقة` | النقاط المكتسبة: `⭐ {earned_points} نقطة`", ephemeral=True)

@bot.tree.command(name="setup_redm_panel", description="إرسال لوحة تحضير RedM في الروم الحالي")
@app_commands.checks.has_permissions(administrator=True)
async def setup_redm_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚔️ تحضير RedM",
        description="استخدم الأزرار بالأسفل لتسجيل حضورك في RedM.\n\n"
                    "🟢 **دخول RedM**\nاضغط عند دخولك للسيرفر لبدء احتساب الوقت.\n\n"
                    "🔴 **خروج RedM**\nاضغط عند انتهائك لإيقاف احتساب الوقت.\n\n"
                    "⭐ **كل ساعة تواجد = 1 نقطة**",
        color=discord.Color.red(),
        timestamp=get_makkah_now()
    )
    await interaction.channel.send(embed=embed, view=RedMAttendanceView(bot))
    await interaction.response.send_message("✅ تم إرسال لوحة تحضير RedM بنجاح في هذا الروم.", ephemeral=True)

# ==================== أوامر النقاط والإحصائيات ====================
@bot.tree.command(name="points", description="عرض عدد النقاط الحالية لك أو لأي عضو آخر")
async def points_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT total_points FROM member_points WHERE user_id = ?", (target.id,)) as cursor:
            row = await cursor.fetchone()
    
    points = row[0] if row else 0
    embed = discord.Embed(
        title="⭐ نظام نقاط تحضير RedM",
        description=f"العضو: {target.mention}\nرصيد النقاط الحالي: **`{points:,} نقطة`**",
        color=discord.Color.gold(),
        timestamp=get_makkah_now()
    )
    await interaction.response.send_message(embed=embed)

# ==================== نظام تزاوج الخيول المطور (خيارات منسدلة سهلة) ====================
HORSE_TYPES = [
    "العربي الدتش",
    "العربي الابليسي",
    "العربي الاسود",
    "الشير الابيض",
    "الشير الاسود"
]

class HorseBreedModalDetails(discord.ui.Modal, title="تفاصيل تزاوج الحصان 🐎"):
    def __init__(self, selected_breed: str):
        super().__init__(timeout=None)
        self.selected_breed = selected_breed

    horse_name = discord.ui.TextInput(label="اسم الحصان", placeholder="أدخل اسم الحصان...", required=True)
    horse_age = discord.ui.TextInput(label="عمر الحصان", placeholder="أدخل عمر الحصان...", required=True)
    mating_date = discord.ui.TextInput(
        label="تاريخ ووقت التزاوج", 
        placeholder="DD-MM-YYYY hh:mm AM/PM (مثال: 24-10-2026 03:30 PM)", 
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            mating_dt = datetime.strptime(self.mating_date.value.strip(), "%d-%m-%Y %I:%M %p")
            mating_dt = mating_dt.replace(tzinfo=MAKKAH_TZ)
        except ValueError:
            await interaction.followup.send("❌ صيغة التاريخ غير صحيحة! يرجى الاستخدام مثال: `24-10-2026 03:30 PM`", ephemeral=True)
            return

        ready_dt = mating_dt + timedelta(hours=48)
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT INTO horse_breeding (user_id, horse_name, breed_type, horse_age, mating_time, ready_time) VALUES (?, ?, ?, ?, ?, ?)",
                (interaction.user.id, self.horse_name.value, self.selected_breed, self.horse_age.value, mating_dt.isoformat(), ready_dt.isoformat())
            )
            await db.commit()

        now = get_makkah_now()
        remaining = ready_dt - now

        if remaining.total_seconds() > 0:
            rem_days = int(remaining.total_seconds() // 86400)
            rem_hours = int((remaining.total_seconds() % 86400) // 3600)
            rem_mins = int((remaining.total_seconds() % 3600) // 60)
            time_text = f"باقي على الإنتاج: `{rem_days} يوم و {rem_hours} ساعة و {rem_mins} دقيقة`" if rem_days > 0 else f"باقي على الإنتاج: `{rem_hours} ساعة و {rem_mins} دقيقة`"
        else:
            time_text = "🟢 **انتهت مدة الإنتاج وجاهز للحصاد!**"

        embed = discord.Embed(
            title="🐎 تم تسجيل عملية تزاوج الحصان بنجاح",
            description="تم حفظ تفاصيل الإنتاج وحساب الموعد بدقة (مدة الإنتاج: **48 ساعة / يومان**).",
            color=discord.Color.gold(),
            timestamp=get_makkah_now()
        )
        embed.add_field(name="اسم الحصان", value=f"`{self.horse_name.value}`", inline=True)
        embed.add_field(name="الفصيلة المحددة", value=f"`{self.selected_breed}`", inline=True)
        embed.add_field(name="العمر", value=f"`{self.horse_age.value}`", inline=True)
        embed.add_field(name="وقت التزاوج", value=f"`{format_makkah_time(mating_dt)}`", inline=False)
        embed.add_field(name="وقت الإنتاج المتوقع", value=f"`{format_makkah_time(ready_dt)}`", inline=False)
        embed.add_field(name="الحالة", value=time_text, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

class HorseBreedSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(
        placeholder="اختر نوع الحصان للتزاوج 🐎...",
        options=[discord.SelectOption(label=h_type, value=h_type) for h_type in HORSE_TYPES]
    )
    async def select_horse_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        selected_type = select.values[0]
        await interaction.response.send_modal(HorseBreedModalDetails(selected_type))

@bot.tree.command(name="breed", description="حساب موعد إنتاج الحصان الجديد (قائمة خيارات منسدلة)")
async def breed_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("🐎 **يرجى اختيار نوع الحصان من القائمة التالية:**", view=HorseBreedSelectView(), ephemeral=True)

@bot.tree.command(name="breed_list", description="عرض قائمة جميع عمليات تزاوج وإنتاج الخيول الحالية")
async def breed_list_cmd(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT rowid, horse_name, breed_type, horse_age, ready_time FROM horse_breeding") as cursor:
            rows = await cursor.fetchall()

    embed = discord.Embed(title="🐎 قائمة إنتاج وتزاوج الخيول الحالية (48 ساعة)", color=discord.Color.dark_red(), timestamp=get_makkah_now())
    if not rows:
        embed.description = "لا توجد عمليات تزاوج أو إنتاج مسجلة حالياً."
    else:
        now = get_makkah_now()
        for rowid, h_name, b_type, h_age, ready_str in rows:
            try:
                ready_dt = datetime.fromisoformat(ready_str)
                remaining = ready_dt - now
                if remaining.total_seconds() > 0:
                    rd = int(remaining.total_seconds() // 86400)
                    rh = int((remaining.total_seconds() % 86400) // 3600)
                    rm = int((remaining.total_seconds() % 3600) // 60)
                    status = f"⏳ باقي: {rd}ي {rh}س {rm}د" if rd > 0 else f"⏳ باقي: {rh}س {rm}د"
                else:
                    status = "🟢 جاهز للإنتاج!"
            except Exception:
                status = "غير محدد"

            embed.add_field(
                name=f"ID: {rowid} | {h_name}",
                value=f"الفصيلة: `{b_type}` | العمر: `{h_age}`\nموعد الإنتاج: `{format_makkah_time(ready_dt)}`\nالحالة: **{status}**",
                inline=False
            )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="remove_breed", description="حذف عملية إنتاج حصان من القائمة (للأدمن فقط)")
@app_commands.checks.has_permissions(administrator=True)
async def remove_breed(interaction: discord.Interaction, row_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("DELETE FROM horse_breeding WHERE rowid = ?", (row_id,))
        await db.commit()
        if cursor.rowcount == 0:
            await interaction.response.send_message(f"❌ لم يتم العثور على عملية إنتاج بهذا الـ ID ({row_id}).", ephemeral=True)
            return
    await interaction.response.send_message(f"🗑️ تم حذف عملية إنتاج الحصان (ID: {row_id}) بنجاح.")

if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if TOKEN:
        TOKEN = TOKEN.strip()
    if not TOKEN:
        raise ValueError("❌ لم يتم العثور على توكن البوت!")
    bot.run(TOKEN)
