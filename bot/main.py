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

# ==================== إعدادات الحزم (العدد الإجمالي والنوع والألوان) ====================
PACKAGES_DATA = {
    # الحزم المحدودة
    "CLASSIC": {"type": "limited", "color_hex": 0x992d22, "color_str": "992d22", "total": 5},
    "FULMINE": {"type": "limited", "color_hex": 0x240b7a, "color_str": "240b7a", "total": 8},
    "RED FLAME": {"type": "limited", "color_hex": 0xff0000, "color_str": "ff0000", "total": 1},
    "CLAWS 🐯": {"type": "limited", "color_hex": 0xc27c0e, "color_str": "c27c0e", "total": 1},
    "PREMIUM": {"type": "limited", "color_hex": 0xcda609, "color_str": "cda609", "total": 8},
    "Elite": {"type": "limited", "color_hex": 0xa6834b, "color_str": "a6834b", "total": 1},
    
    # الحزم العادية
    "SKY": {"type": "normal", "color_hex": 0x64b0e3, "color_str": "64b0e3", "total": 1},
    "WOLF KING": {"type": "normal", "color_hex": 0x1100fe, "color_str": "1100fe", "total": 1},
    "PLUM": {"type": "normal", "color_hex": 0x71368a, "color_str": "71368a", "total": 2},
    "ROYAL PINK": {"type": "normal", "color_hex": 0xc852bc, "color_str": "c852bc", "total": 1},
    "ROYAL GRAY": {"type": "normal", "color_hex": 0xf7f5f5, "color_str": "f7f5f5", "total": 8},
    "BRIGHT ROSES": {"type": "normal", "color_hex": 0xad1457, "color_str": "ad1457", "total": 2},
    "Venom": {"type": "normal", "color_hex": 0x073403, "color_str": "073403", "total": 2},
    "GREEN FLAG": {"type": "normal", "color_hex": 0x1f8b4c, "color_str": "1f8b4c", "total": 6},
    "Viper": {"type": "normal", "color_hex": 0x3e4020, "color_str": "3e4020", "total": 2},
    "BlackBlood": {"type": "normal", "color_hex": 0x010101, "color_str": "010101", "total": 2},
    "BLUE FANG": {"type": "normal", "color_hex": 0x2b3eea, "color_str": "2b3eea", "total": 1}
}

# ==================== الثوابت والمعرفات المطلوبة ====================
BROADCAST_ROLE_ID = 1550542997010251927      
WELCOME_ROLE_ID = 1550543013317447680        
RULES_CHANNEL_ID = 1550543164723564636       
APPLY_CHANNEL_ID = 1550543173300781116       
WELCOME_CHANNEL_ID = 1550543159321427978     
ATTENDANCE_CHANNEL_ID = 1552244246764064818  

CHECK_INTERVAL = 3600         
CONFIRM_TIMEOUT = 600         

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
        await db.execute('''
            CREATE TABLE IF NOT EXISTS package_serials (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                package_name TEXT,
                package_type TEXT,
                version_number TEXT,
                serial_number TEXT,
                added_by TEXT,
                added_at TEXT
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

# ==================== نظام إضافة السيريال باختيار الحزمة ====================
class AddSerialModalDetails(discord.ui.Modal):
    def __init__(self, selected_package: str):
        self.selected_package = selected_package
        super().__init__(title=f"إضافة سيريال للحزمة: {selected_package}")

    version_number = discord.ui.TextInput(label="اسم / رقم النسخة", placeholder="مثال: النسخة الأولى أو V1...", required=True)
    serial_number = discord.ui.TextInput(label="السيريال نمبر (Serial Number)", placeholder="أدخل رقم السيريال هنا...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        now_str = get_makkah_now().isoformat()
        pkg_info = PACKAGES_DATA.get(self.selected_package, {"type": "normal"})
        pkg_type = pkg_info["type"]

        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT INTO package_serials (package_name, package_type, version_number, serial_number, added_by, added_at) VALUES (?, ?, ?, ?, ?, ?)",
                (self.selected_package, pkg_type, self.version_number.value.strip(), self.serial_number.value.strip(), str(interaction.user), now_str)
            )
            await db.commit()

        type_label = "🌟 محدودة" if pkg_type == "limited" else "🔹 عادية"

        embed = discord.Embed(
            title="✅ تم تسجيل سيريال الحزمة بنجاح",
            color=discord.Color.green(),
            timestamp=get_makkah_now()
        )
        embed.add_field(name="الحزمة", value=f"`{self.selected_package}` ({type_label})", inline=True)
        embed.add_field(name="النسخة", value=f"`{self.version_number.value}`", inline=True)
        embed.add_field(name="السيريال نمبر", value=f"`{self.serial_number.value}`", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

class AddSerialPackageSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(
        placeholder="اختر الحزمة لإضافة سيريال ونسخة لها...",
        options=[
            discord.SelectOption(
                label=pkg_name,
                description=f"النوع: {'محدودة' | 'عادية'} | الإجمالي: {info['total']} نسخ",
                emoji="🌟" if info['type'] == 'limited' else "🔹",
                value=pkg_name
            ) for pkg_name, info in PACKAGES_DATA.items()
        ]
    )
    async def select_package(self, interaction: discord.Interaction, select: discord.ui.Select):
        selected_pkg = select.values[0]
        await interaction.response.send_modal(AddSerialModalDetails(selected_pkg))

@bot.tree.command(name="add_serial", description="إضافة سيريال ونسخة لحزمة عن طريق اختيارها من القائمة")
async def add_serial_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("📦 **اختر الحزمة المراد إضافة السيريال والنسخة لها:**", view=AddSerialPackageSelectView(), ephemeral=True)

# ==================== نظام استعراض الحزم مع الألوان وإحصائيات المسجل وغير المسجل ====================
class PackagesSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="الحزم المحدودة (Limited Packages)", description="عرض الحزم المحدودة، ألوانها، وإحصائيات سيريالاتها", emoji="🌟", value="limited_packages"),
            discord.SelectOption(label="الحزم العادية (Normal Packages)", description="عرض الحزم العادية، ألوانها، وإحصائيات سيريالاتها", emoji="🔹", value="normal_packages")
        ]
        super().__init__(placeholder="اختر قسم الحزم للاستعراض...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        target_type = "limited" if self.values[0] == "limited_packages" else "normal"
        title_text = "🌟 قائمة الحزم المحدودة وإحصائيات السيريالات" if target_type == "limited" else "🔹 قائمة الحزم العادية وإحصائيات السيريالات"
        color_theme = discord.Color.gold() if target_type == "limited" else discord.Color.blue()

        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT rowid, package_name, version_number, serial_number FROM package_serials WHERE package_type = ?", (target_type,)) as cursor:
                serials_rows = await cursor.fetchall()

        # تجميع السيريالات وحساب المسجل لكل حزمة
        serials_by_pkg = {}
        registered_counts = {}
        for rowid, p_name, ver, serial in serials_rows:
            if p_name not in serials_by_pkg:
                serials_by_pkg[p_name] = []
                registered_counts[p_name] = 0
            serials_by_pkg[p_name].append(f"🆔 {rowid} | النسخة: `{ver}` ➔ السيريال: `{serial}`")
            registered_counts[p_name] += 1

        embed = discord.Embed(title=title_text, color=color_theme, timestamp=get_makkah_now())

        for pkg_name, info in PACKAGES_DATA.items():
            if info["type"] == target_type:
                total_copies = info["total"]
                registered_num = registered_counts.get(pkg_name, 0)
                unregistered_num = max(0, total_copies - registered_num)

                pkg_serials = serials_by_pkg.get(pkg_name, [])
                serials_text = "\n".join(pkg_serials) if pkg_serials else "لا توجد نسخ مسجلة حالياً."

                stats_line = f"📊 **الإحصائية:** مسجل: `{registered_num}` | غير مسجل: `{unregistered_num}` من إجمالي `{total_copies}`"
                color_line = f"🎨 **لون الحزمة:** `{info['color_str']}`"

                field_value = f"{color_line}\n{stats_line}\n\n**النسخ المسجلة:**\n{serials_text}"

                embed.add_field(
                    name=f"{'🌟' if target_type == 'limited' else '🔹'} {pkg_name}",
                    value=field_value,
                    inline=False
                )

        await interaction.edit_original_response(embed=embed, view=self.view)

class PackagesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(PackagesSelect())

@bot.tree.command(name="packages", description="عرض قوائم الحزم مع الألوان وإحصائيات السيريالات المسجلة وغير المسجلة")
async def packages_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📦 نظام إدارة واستعراض الحزم والنسخ",
        description="اختر القسم من القائمة المنسدلة بالأسفل لعرض الحزم، الألوان الملونة، وعدد النسخ المسجلة وغير المسجلة.",
        color=discord.Color.dark_theme(),
        timestamp=get_makkah_now()
    )
    await interaction.response.send_message(embed=embed, view=PackagesView(), ephemeral=True)

@bot.tree.command(name="remove_serial", description="حذف سيريال أو نسخة حزمة برقم الـ ID (للأدمن فقط)")
@app_commands.checks.has_permissions(administrator=True)
async def remove_serial_cmd(interaction: discord.Interaction, row_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("DELETE FROM package_serials WHERE rowid = ?", (row_id,))
        await db.commit()
        if cursor.rowcount == 0:
            await interaction.response.send_message(f"❌ لم يتم العثور على سيريال بهذا الـ ID ({row_id}).", ephemeral=True)
            return
    await interaction.response.send_message(f"🗑️ تم حذف السيريال (ID: {row_id}) بنجاح.", ephemeral=True)

# ==================== باقي الأوامر (الترحيب، البرودكاست، التحضير، الخيول) ====================
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
                        f"🤝 إذا كنت تبي تنضم لعائلتنا وتقدم طلبك، توجه إلى {apply_mention}.",
            color=discord.Color.gold(),
            timestamp=get_makkah_now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await channel.send(content=member.mention, embed=embed)

async def remove_recent(member_id):
    await asyncio.sleep(10)
    recent_joined.discard(member_id)

@bot.command(name="bc")
async def broadcast_cmd(ctx, *, message_content: str = None):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    if not message_content:
        await ctx.send("❌ يرجى كتابة الرسالة بعد الأمر!", delete_after=6)
        return

    target_role = ctx.guild.get_role(BROADCAST_ROLE_ID)
    if not target_role:
        await ctx.send("❌ رتبة البرودكاست غير موجودة!", delete_after=6)
        return

    status_msg = await ctx.send(f"⏳ جاري إرسال البرودكاست...")
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

    await status_msg.edit(content=f"✅ تم الانتهاء! تم الإرسال لـ {sent} عضو.")

class ConfirmRedMView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=CONFIRM_TIMEOUT)
        self.user_id = user_id
        self.confirmed = False

    @discord.ui.button(label="تأكيد التواجد 🟢", style=discord.ButtonStyle.green, custom_id="confirm_redm_presence")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ هذا التنبيه ليس لك!", ephemeral=True)
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
                await channel.send(f"⚠️ {member.mention} **تأكيد حضور دوري:** يرجى الضغط على الزر خلال 10 دقائق.", view=view)
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
                await interaction.response.send_message("❌ أنت مسجل دخول بالفعل!", ephemeral=True)
                return
            await db.execute("INSERT INTO redm_attendance (user_id, user_name, start_time) VALUES (?, ?, ?)",
                             (user.id, user.display_name, now.isoformat()))
            await db.commit()
        if user.id in periodic_check_tasks:
            periodic_check_tasks[user.id].cancel()
        periodic_check_tasks[user.id] = asyncio.create_task(start_redm_periodic_check(self.bot, user))
        await interaction.response.send_message(f"✅ تم تسجيل دخولك الساعة `{format_makkah_time(now)}`.", ephemeral=True)

    @discord.ui.button(label="خروج RedM", style=discord.ButtonStyle.red, custom_id="redm_end_btn")
    async def end_redm(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        now = get_makkah_now()
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT rowid, start_time FROM redm_attendance WHERE user_id = ? AND end_time IS NULL", (user.id,)) as cursor:
                active_session = await cursor.fetchone()
            if not active_session:
                await interaction.response.send_message("❌ أنت غير مسجل دخول حالياً!", ephemeral=True)
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
        await interaction.response.send_message(f"🔴 تم تسجيل خروجك. المدة: `{hours}س و {mins}د` | النقاط: `⭐ {earned_points}`", ephemeral=True)

@bot.tree.command(name="setup_redm_panel", description="إرسال لوحة تحضير RedM في الروم الحالي")
@app_commands.checks.has_permissions(administrator=True)
async def setup_redm_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="⚔️ تحضير RedM", description="استخدم الأزرار لتسجيل حضورك وخروجك.", color=discord.Color.red(), timestamp=get_makkah_now())
    await interaction.channel.send(embed=embed, view=RedMAttendanceView(bot))
    await interaction.response.send_message("✅ تم إرسال لوحة التحضير بنجاح.", ephemeral=True)

@bot.tree.command(name="points", description="عرض عدد النقاط الحالية")
async def points_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT total_points FROM member_points WHERE user_id = ?", (target.id,)) as cursor:
            row = await cursor.fetchone()
    points = row[0] if row else 0
    embed = discord.Embed(title="⭐ نقاط تحضير RedM", description=f"العضو: {target.mention}\nرصيد النقاط: **`{points:,} نقطة`**", color=discord.Color.gold(), timestamp=get_makkah_now())
    await interaction.response.send_message(embed=embed)

HORSE_TYPES = ["العربي الدتش", "العربي الابليسي", "العربي الاسود", "الشير الابيض", "الشير الاسود"]

class HorseBreedModalDetails(discord.ui.Modal, title="تفاصيل تزاوج الحصان 🐎"):
    def __init__(self, selected_breed: str):
        super().__init__(timeout=None)
        self.selected_breed = selected_breed

    horse_name = discord.ui.TextInput(label="اسم الحصان", placeholder="أدخل الاسم...", required=True)
    horse_age = discord.ui.TextInput(label="عمر الحصان", placeholder="أدخل العمر...", required=True)
    mating_date = discord.ui.TextInput(label="تاريخ ووقت التزاوج", placeholder="DD-MM-YYYY hh:mm AM/PM", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            mating_dt = datetime.strptime(self.mating_date.value.strip(), "%d-%m-%Y %I:%M %p").replace(tzinfo=MAKKAH_TZ)
        except ValueError:
            await interaction.followup.send("❌ صيغة التاريخ غير صحيحة!", ephemeral=True)
            return
        ready_dt = mating_dt + timedelta(hours=48)
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT INTO horse_breeding (user_id, horse_name, breed_type, horse_age, mating_time, ready_time) VALUES (?, ?, ?, ?, ?, ?)",
                (interaction.user.id, self.horse_name.value, self.selected_breed, self.horse_age.value, mating_dt.isoformat(), ready_dt.isoformat())
            )
            await db.commit()
        embed = discord.Embed(title="🐎 تم تسجيل تزاوج الحصان", color=discord.Color.gold(), timestamp=get_makkah_now())
        embed.add_field(name="اسم الحصان", value=f"`{self.horse_name.value}`", inline=True)
        embed.add_field(name="الفصيلة", value=f"`{self.selected_breed}`", inline=True)
        embed.add_field(name="وقت الإنتاج المتوقع", value=f"`{format_makkah_time(ready_dt)}`", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

class HorseBreedSelectView(discord.ui.View):
    def __init__(self, bot_instance=None):
        super().__init__(timeout=180)

    @discord.ui.select(placeholder="اختر نوع الحصان 🐎...", options=[discord.SelectOption(label=h, value=h) for h in HORSE_TYPES])
    async def select_horse_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.send_modal(HorseBreedModalDetails(select.values[0]))

@bot.tree.command(name="breed", description="حساب موعد إنتاج الحصان")
async def breed_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("🐎 **اختر نوع الحصان:**", view=HorseBreedSelectView(), ephemeral=True)

@bot.tree.command(name="breed_list", description="عرض قائمة تزاوج الخيول الحالية")
async def breed_list_cmd(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT rowid, horse_name, breed_type, horse_age, ready_time FROM horse_breeding") as cursor:
            rows = await cursor.fetchall()
    embed = discord.Embed(title="🐎 قائمة إنتاج الخيول الحالية", color=discord.Color.dark_red(), timestamp=get_makkah_now())
    if not rows:
        embed.description = "لا توجد عمليات مسجلة."
    else:
        now = get_makkah_now()
        for rowid, h_name, b_type, h_age, ready_str in rows:
            ready_dt = datetime.fromisoformat(ready_str)
            remaining = ready_dt - now
            status = f"⏳ باقي: {int(remaining.total_seconds()//3600)}س" if remaining.total_seconds() > 0 else "🟢 جاهز!"
            embed.add_field(name=f"ID: {rowid} | {h_name}", value=f"الفصيلة: `{b_type}`\nالحالة: **{status}**", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="remove_breed", description="حذف عملية إنتاج حصان")
@app_commands.checks.has_permissions(administrator=True)
async def remove_breed(interaction: discord.Interaction, row_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM horse_breeding WHERE rowid = ?", (row_id,))
        await db.commit()
    await interaction.response.send_message(f"🗑️ تم حذف عملية إنتاج الحصان (ID: {row_id}).")

if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if TOKEN:
        TOKEN = TOKEN.strip()
    if not TOKEN:
        raise ValueError("❌ لم يتم العثور على توكن البوت!")
    bot.run(TOKEN)
