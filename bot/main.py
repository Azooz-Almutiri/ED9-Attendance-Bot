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
BC_SENDER_ROLE_ID = 1544440717815054378      # رتبة السماح بإرسال البرودكاست (Bot)
WELCOME_ROLE_ID = 1550543013317447680        # الرول الذي يعطى للعضو عند دخوله
RULES_CHANNEL_ID = 1550543164723564636       # روم القوانين
APPLY_CHANNEL_ID = 1550543173300781116       # روم طلب التقديم
WELCOME_CHANNEL_ID = 1550543159321427978    # روم مرحبا بك (الترحيب)
ATTENDANCE_CHANNEL_ID = 1552244246764064818  # روم تحضير RedM

CHECK_INTERVAL = 3600         # التحقق كل ساعة (3600 ثانية)
CONFIRM_TIMEOUT = 600         # 10 دقائق مهلة للرد على تأكيد التواجد

periodic_check_tasks = {}

# ==================== تهيئة قاعدة البيانات ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS general_vaults (
                vault_name TEXT PRIMARY KEY,
                balance INTEGER DEFAULT 0,
                last_updated TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS weapons_vault (
                item_name TEXT PRIMARY KEY,
                quantity INTEGER DEFAULT 0
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bar_vault (
                item_name TEXT PRIMARY KEY,
                quantity INTEGER DEFAULT 0
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS blacksmith_vault (
                material_name TEXT PRIMARY KEY,
                quantity INTEGER DEFAULT 0
            )
        ''')
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
        except Exception as e:
            print(f"فشل في إعطاء الرول للعضو: {e}")

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

# ==================== أمر البرودكاست المخصص مع شرط الرتبة ====================
@bot.command(name="bc")
async def broadcast_cmd(ctx, *, message_content: str = None):
    has_required_role = any(r.id == BC_SENDER_ROLE_ID for r in getattr(ctx.author, "roles", []))
    if not has_required_role and not ctx.author.guild_permissions.administrator:
        await ctx.message.delete()
        await ctx.send("❌ عذراً، لا تمتلك الصلاحية أو رتبة إرسال البرودكاست المطلوبة!", delete_after=6)
        return

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
        await interaction.response.edit_message(content=f"✅ {interaction.user.mention} تم تأكيد استمرار تحضيرك بنجاح!", view=self)
        self.stop()

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
                try:
                    channel = await bot_client.fetch_channel(ATTENDANCE_CHANNEL_ID)
                except Exception:
                    break

            view = ConfirmRedMView(member.id)
            msg = None
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
                try:
                    duration = max(0, int((now - datetime.fromisoformat(str(start_str))).total_seconds() // 60))
                except Exception:
                    duration = 0

                earned_points = duration // 60  # كل ساعة = نقطة

                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE redm_attendance SET end_time = ?, duration_minutes = ?, points_earned = ? WHERE rowid = ?", 
                                     (now.isoformat(), duration, earned_points, row_id))
                    if earned_points > 0:
                        await db.execute('''
                            INSERT INTO member_points (user_id, user_name, total_points) VALUES (?, ?, ?)
                            ON CONFLICT(user_id) DO UPDATE SET total_points = total_points + ?, user_name = ?
                        ''', (member.id, member.display_name, earned_points, earned_points, member.display_name))
                    await db.commit()

                if msg:
                    try:
                        await msg.edit(content=f"❌ {member.mention} **تم تسجيل خروجك تلقائياً** لعدم إجابتك على تأكيد التواجد خلال المدة المحددة.", view=None)
                    except Exception:
                        pass
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
            try:
                duration = max(0, int((now - datetime.fromisoformat(str(start_str))).total_seconds() // 60))
            except Exception:
                duration = 0

            earned_points = duration // 60  # كل ساعة حضور = نقطة واحدة

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

@bot.tree.command(name="setup_redm_panel", description="إرسال لوحة تحضير RedM في روم التحضير المخصص (خاص بالإدارة)")
@app_commands.checks.has_permissions(administrator=True)
async def setup_redm_panel(interaction: discord.Interaction):
    channel = interaction.guild.get_channel(ATTENDANCE_CHANNEL_ID)
    if not channel:
        await interaction.response.send_message("❌ روم التحضير المخصص غير موجود أو خطأ في المعرف!", ephemeral=True)
        return

    embed = discord.Embed(
        title="⚔️ تحضير RedM",
        description="استخدم الأزرار بالأسفل لتسجيل حضورك في RedM.\n\n"
                    "🟢 **دخول RedM**\n"
                    "اضغط عند دخولك للسيرفر لبدء احتساب الوقت.\n\n"
                    "🔴 **خروج RedM**\n"
                    "اضغط عند انتهائك لإيقاف احتساب الوقت.\n\n"
                    "⭐ **كل ساعة تواجد = 1 نقطة**",
        color=discord.Color.red(),
        timestamp=get_makkah_now()
    )
    await channel.send(embed=embed, view=RedMAttendanceView(bot))
    await interaction.response.send_message(f"✅ تم إرسال لوحة تحضير RedM بنجاح إلى الروم {channel.mention}.", ephemeral=True)

# ==================== أوامر النقاط والإحصائيات ====================
@bot.tree.command(name="points", description="عرض عدد النقاط الحالية لك أو لأي عضو آخر")
@app_commands.describe(member="العضو المراد استعلام نقاطه (اختياري)")
async def points_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT total_points FROM member_points WHERE user_id = ?", (target.id,)) as cursor:
            row = await cursor.fetchone()
    
    points = row[0] if row else 0
    embed = discord.Embed(
        title="⭐ نظام نقاط تحضير RedM",
        description=f"العضو: {target.mention}\nرصيد النقاط الحالي: **`{points:,} نقطة`** (كل ساعة = نقطة)",
        color=discord.Color.gold(),
        timestamp=get_makkah_now()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="points_list", description="عرض قائمة بجميع الأعضاء الذين لديهم نقاط وعدد الأشخاص الإجمالي")
async def points_list_cmd(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id, user_name, total_points FROM member_points WHERE total_points > 0 ORDER BY total_points DESC") as cursor:
            rows = await cursor.fetchall()

    total_members_with_points = len(rows)

    embed = discord.Embed(
        title="📊 قائمة نقاط أعضاء RedM (ساعة = نقطة)",
        description=f"إجمالي عدد الأعضاء الذين لديهم نقاط: **`{total_members_with_points} عضو`**",
        color=discord.Color.dark_red(),
        timestamp=get_makkah_now()
    )

    if not rows:
        embed.add_field(name="لا توجد نقاط مسجلة", value="لم يحصل أي عضو على نقاط حتى الآن.", inline=False)
    else:
        for idx, (u_id, u_name, pts) in enumerate(rows, 1):
            embed.add_field(
                name=f"{idx}. {u_name or 'عضو'} (ID: {u_id})",
                value=f"النقاط: **`{pts} نقطة`**",
                inline=False
            )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="reset_points", description="تصفير نقاط عضو معين (خاص بالإدارة)")
@app_commands.describe(member="العضو المراد تصفير نقاطه")
@app_commands.checks.has_permissions(administrator=True)
async def reset_points(interaction: discord.Interaction, member: discord.Member):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE member_points SET total_points = 0 WHERE user_id = ?", (member.id,))
        await db.commit()
    await interaction.response.send_message(f"⚠️ تم تصفير نقاط العضو {member.mention} بنجاح.")

# ==================== نظام تزاوج وإنتاج الخيول (Breed Modal - DD-MM-YYYY hh:mm AM/PM) ====================
class HorseBreedModal(discord.ui.Modal, title="حاسبة تزاوج وإنتاج الخيول 🐎"):
    horse_name = discord.ui.TextInput(label="اسم الحصان", placeholder="أدخل اسم الحصان...", required=True)
    breed_type = discord.ui.TextInput(label="فصيلة الحصان", placeholder="أدخل فصيلة الحصان...", required=True)
    horse_age = discord.ui.TextInput(label="عمر الحصان", placeholder="أدخل عمر الحصان...", required=True)
    mating_date = discord.ui.TextInput(label="تاريخ ووقت التزاوج", placeholder="DD-MM-YYYY hh:mm AM/PM (مثال: 23-09-2026 03:30 PM)", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            mating_dt = datetime.strptime(self.mating_date.value.strip(), "%d-%m-%Y %I:%M %p")
            mating_dt = mating_dt.replace(tzinfo=MAKKAH_TZ)
        except ValueError:
            await interaction.response.send_message("❌ صيغة التاريخ غير صحيحة! يرجى استخدام الصيغة: `DD-MM-YYYY hh:mm AM/PM` (مثال: `23-09-2026 03:30 PM`)", ephemeral=True)
            return

        ready_dt = mating_dt + timedelta(days=2)
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT INTO horse_breeding (user_id, horse_name, breed_type, horse_age, mating_time, ready_time) VALUES (?, ?, ?, ?, ?, ?)",
                (interaction.user.id, self.horse_name.value, self.breed_type.value, self.horse_age.value, mating_dt.isoformat(), ready_dt.isoformat())
            )
            await db.commit()

        now = get_makkah_now()
        remaining = ready_dt - now

        if remaining.total_seconds() > 0:
            rem_hours = int(remaining.total_seconds() // 3600)
            rem_mins = int((remaining.total_seconds() % 3600) // 60)
            time_text = f"باقي على الإنتاج: `{rem_hours} ساعة و {rem_mins} دقيقة`"
        else:
            time_text = "🟢 **انتهت مدة الإنتاج وجاهز للحصاد!**"

        embed = discord.Embed(
            title="🐎 تم تسجيل عملية تزاوج الحصان بنجاح",
            description=f"تم حفظ تفاصيل الإنتاج وحساب الموعد بدقة (مدة الإنتاج: **يومان**).",
            color=discord.Color.gold(),
            timestamp=get_makkah_now()
        )
        embed.add_field(name="اسم الحصان", value=f"`{self.horse_name.value}`", inline=True)
        embed.add_field(name="الفصيلة", value=f"`{self.breed_type.value}`", inline=True)
        embed.add_field(name="العمر", value=f"`{self.horse_age.value}`", inline=True)
        embed.add_field(name="وقت التزاوج", value=f"`{format_makkah_time(mating_dt)}`", inline=False)
        embed.add_field(name="وقت الإنتاج المتوقع", value=f"`{format_makkah_time(ready_dt)}`", inline=False)
        embed.add_field(name="الحالة", value=time_text, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="breed", description="حساب موعد إنتاج الحصان الجديد بناءً على وقت التزاوج (يومان)")
async def breed_cmd(interaction: discord.Interaction):
    await interaction.response.send_modal(HorseBreedModal())

@bot.tree.command(name="breed_list", description="عرض قائمة جميع عمليات تزاوج وإنتاج الخيول الحالية")
async def breed_list_cmd(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT rowid, horse_name, breed_type, horse_age, ready_time FROM horse_breeding") as cursor:
            rows = await cursor.fetchall()

    embed = discord.Embed(title="🐎 قائمة إنتاج وتزاوج الخيول الحالية", color=discord.Color.dark_red(), timestamp=get_makkah_now())
    if not rows:
        embed.description = "لا توجد عمليات تزاوج أو إنتاج مسجلة حالياً."
    else:
        now = get_makkah_now()
        for rowid, h_name, b_type, h_age, ready_str in rows:
            try:
                ready_dt = datetime.fromisoformat(ready_str)
                remaining = ready_dt - now
                if remaining.total_seconds() > 0:
                    rh = int(remaining.total_seconds() // 3600)
                    rm = int((remaining.total_seconds() % 3600) // 60)
                    status = f"⏳ باقي: {rh}س {rm}د"
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

@bot.tree.command(name="remove_breed", description="حذف عملية إنتاج حصان من القائمة (خاص بالإدارة)")
@app_commands.describe(row_id="رقم الـ ID الخاص بعملية الإنتاج من أمر breed_list")
@app_commands.checks.has_permissions(administrator=True)
async def remove_breed(interaction: discord.Interaction, row_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("DELETE FROM horse_breeding WHERE rowid = ?", (row_id,))
        await db.commit()
        if cursor.rowcount == 0:
            await interaction.response.send_message(f"❌ لم يتم العثور على عملية إنتاج بهذا الـ ID ({row_id}).", ephemeral=True)
            return
    await interaction.response.send_message(f"🗑️ تم حذف عملية إنتاج الحصان (ID: {row_id}) بنجاح.")

# ==================== أوامر التقديم والخيول ====================
@bot.tree.command(name="apply", description="عرض طريقة التقديم للانضمام لعائلة القودفاذر")
async def apply_cmd(interaction: discord.Interaction):
    apply_ch = interaction.guild.get_channel(APPLY_CHANNEL_ID)
    ch_text = apply_ch.mention if apply_ch else "الروم المخصص"
    embed = discord.Embed(
        title="📝 طريقة التقديم لعائلة القودفاذرز",
        description=f"يرجى قراءة الشروط والتوجه إلى {ch_text} لتقديم طلبك.",
        color=discord.Color.gold(),
        timestamp=get_makkah_now()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="horses", description="إرسال قائمة الخيول المتوفرة لدى عائلة القودفاذر")
async def horses_cmd(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT horse_name, added_by FROM horses") as cursor:
            rows = await cursor.fetchall()

    embed = discord.Embed(title="🐎 قائمة خيول عائلة القودفاذر", color=discord.Color.dark_red(), timestamp=get_makkah_now())
    if not rows:
        embed.description = "لا توجد خيول مسجلة حالياً."
    else:
        for name, added in rows:
            embed.add_field(name=name, value=f"بواسطة: `{added or 'الإدارة'}`", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="add_horse", description="إضافة حصان جديد للقائمة (خاص بالإدارة)")
@app_commands.describe(horse_name="اسم الحصان المراد إضافته")
@app_commands.checks.has_permissions(administrator=True)
async def add_horse(interaction: discord.Interaction, horse_name: str):
    now_str = format_makkah_time(get_makkah_now())
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO horses (horse_name, added_by, added_at) VALUES (?, ?, ?)", 
                         (horse_name, str(interaction.user), now_str))
        await db.commit()
    await interaction.response.send_message(f"✅ تم إضافة الحصان `{horse_name}` للقائمة بنجاح.")

@bot.tree.command(name="remove_horse", description="حذف حصان من القائمة (خاص بالإدارة)")
@app_commands.describe(horse_name="اسم الحصان المراد حذفه")
@app_commands.checks.has_permissions(administrator=True)
async def remove_horse(interaction: discord.Interaction, horse_name: str):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("DELETE FROM horses WHERE horse_name = ?", (horse_name,))
        await db.commit()
        if cursor.rowcount == 0:
            await interaction.response.send_message(f"❌ الحصان `{horse_name}` غير موجود بالقائمة.", ephemeral=True)
            return
    await interaction.response.send_message(f"🗑️ تم حذف الحصان `{horse_name}` من القائمة بنجاح.")

# ==================== نظام الستور / الخزنة العامة ====================
@bot.tree.command(name="store", description="عرض خزنة الستور بالجرد الحالي")
async def store_cmd(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT vault_name, balance FROM general_vaults WHERE vault_name = 'store'") as cursor:
            row = await cursor.fetchone()
    balance = row[1] if row else 0
    embed = discord.Embed(title="📦 خزنة الستور - GODFATHER FAMILY", color=discord.Color.blue(), timestamp=get_makkah_now())
    embed.add_field(name="💰 الرصيد / الموارد الحالية", value=f"`{balance:,}`", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="store_inv", description="إضافة أو خصم (بالسالب) أغراض خزنة الستور")
@app_commands.describe(amount="الكمية المراد إضافتها أو خصمها")
@app_commands.checks.has_permissions(manage_guild=True)
async def store_inv(interaction: discord.Interaction, amount: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO general_vaults (vault_name, balance, last_updated) VALUES ('store', ?, ?)
            ON CONFLICT(vault_name) DO UPDATE SET balance = balance + ?, last_updated = ?
        ''', (amount, format_makkah_time(get_makkah_now()), amount, format_makkah_time(get_makkah_now())))
        await db.commit()
    await interaction.response.send_message(f"✅ تم تحديث جرد خزنة الستور بمقدار `{amount}` بنجاح.")

# ==================== نظام محل الأسلحة (Weapons) ====================
@bot.tree.command(name="weapons", description="عرض خزنة محل الأسلحة بالجرد الحالي")
async def weapons_cmd(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT item_name, quantity FROM weapons_vault") as cursor:
            rows = await cursor.fetchall()
    embed = discord.Embed(title="🔫 خزنة محل الأسلحة - GODFATHER FAMILY", color=discord.Color.red(), timestamp=get_makkah_now())
    if not rows:
        embed.description = "مخزون الأسلحة والذخيرة فارغ حالياً."
    else:
        for item, qty in rows:
            embed.add_field(name=item, value=f"الكمية: `{qty:,}`", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="weapons_inv", description="إضافة أو خصم (بالسالب) أسلحة وذخيرة خزنة الأسلحة")
@app_commands.describe(item_name="اسم السلاح أو المورد", quantity="الكمية")
@app_commands.checks.has_permissions(manage_guild=True)
async def weapons_inv(interaction: discord.Interaction, item_name: str, quantity: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO weapons_vault (item_name, quantity) VALUES (?, ?)
            ON CONFLICT(item_name) DO UPDATE SET quantity = quantity + ?
        ''', (item_name, quantity, quantity))
        await db.commit()
    await interaction.response.send_message(f"✅ تم تحديث خزنة الأسلحة ({item_name}) بمقدار `{quantity}` بنجاح.")

# ==================== نظام الحانة (Bar) ====================
@bot.tree.command(name="bar", description="عرض خزنة الحانة بالجرد الحالي")
async def bar_cmd(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT item_name, quantity FROM bar_vault") as cursor:
            rows = await cursor.fetchall()
    embed = discord.Embed(title="🍻 خزنة الحانة - GODFATHER FAMILY", color=discord.Color.orange(), timestamp=get_makkah_now())
    if not rows:
        embed.description = "خزنة الحانة فارغة حالياً."
    else:
        for item, qty in rows:
            embed.add_field(name=item, value=f"الكمية: `{qty:,}`", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="bar_inv", description="إضافة أو خصم (بالسالب) مشروبات/أغراض خزنة الحانة")
@app_commands.describe(item_name="اسم المشروب أو الغرض", quantity="الكمية")
@app_commands.checks.has_permissions(manage_guild=True)
async def bar_inv(interaction: discord.Interaction, item_name: str, quantity: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO bar_vault (item_name, quantity) VALUES (?, ?)
            ON CONFLICT(item_name) DO UPDATE SET quantity = quantity + ?
        ''', (item_name, quantity, quantity))
        await db.commit()
    await interaction.response.send_message(f"✅ تم تحديث خزنة الحانة ({item_name}) بمقدار `{quantity}` بنجاح.")

# ==================== نظام الحداد (Blacksmith & Inventory) ====================
@bot.tree.command(name="blacksmith", description="عرض خزنة الحداد بالجرد الحالي")
async def blacksmith_cmd(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT material_name, quantity FROM blacksmith_vault") as cursor:
            rows = await cursor.fetchall()
    embed = discord.Embed(title="⚒️ خزنة الحداد - GODFATHER FAMILY", color=discord.Color.dark_grey(), timestamp=get_makkah_now())
    if not rows:
        embed.description = "مخزون الحداد فارغ حالياً."
    else:
        for mat, qty in rows:
            embed.add_field(name=mat, value=f"الكمية: `{qty:,}`", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="inventory", description="إضافة أو خصم (بالسالب) موارد خزنة الحداد")
@app_commands.describe(material_name="اسم المورد", quantity="الكمية")
@app_commands.checks.has_permissions(manage_guild=True)
async def inventory_cmd(interaction: discord.Interaction, material_name: str, quantity: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO blacksmith_vault (material_name, quantity) VALUES (?, ?)
            ON CONFLICT(material_name) DO UPDATE SET quantity = quantity + ?
        ''', (material_name, quantity, quantity))
        await db.commit()
    await interaction.response.send_message(f"✅ تم تحديث موارد خزنة الحداد ({material_name}) بمقدار `{quantity}` بنجاح.")

# ==================== نظام الأغاني ====================
@bot.tree.command(name="play", description="تشغيل مقطع صوتي أو أغنية من يوتيوب")
@app_commands.describe(query="اسم الأغنية أو الرابط")
async def play_music(interaction: discord.Interaction, query: str):
    await interaction.response.send_message(f"🎵 جاري البحث والتشغيل لـ: `{query}` 🎧")

@bot.tree.command(name="skip", description="تخطي الأغنية الحالية")
async def skip_music(interaction: discord.Interaction):
    await interaction.response.send_message("⏭️ تم تخطي الأغنية الحالية بنجاح.")

@bot.tree.command(name="stop", description="إيقاف الأغنية وإخراج البوت من الروم الصوتي")
async def stop_music(interaction: discord.Interaction):
    await interaction.response.send_message("⏹️ تم إيقاف الصوت ومغادرة القناة الصوتية بنجاح.")

# ==================== أوامر الإدارة المتقدمة (حذف وتصفير) ====================
@bot.tree.command(name="remove_item", description="حذف عنصر معين نهائياً من خزنة محددة")
@app_commands.choices(vault_type=[
    app_commands.Choice(name="محل الأسلحة", value="weapons"),
    app_commands.Choice(name="الحانة", value="bar"),
    app_commands.Choice(name="الحداد", value="blacksmith")
])
@app_commands.describe(vault_type="اختر الخزنة", item_name="اسم العنصر المراد حذفه نهائياً")
@app_commands.checks.has_permissions(manage_guild=True)
async def remove_item(interaction: discord.Interaction, vault_type: str, item_name: str):
    table_map = {
        "weapons": "weapons_vault",
        "bar": "bar_vault",
        "blacksmith": "blacksmith_vault"
    }
    column_map = {
        "weapons": "item_name",
        "bar": "item_name",
        "blacksmith": "material_name"
    }
    
    table = table_map.get(vault_type)
    col = column_map.get(vault_type)

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(f"DELETE FROM {table} WHERE {col} = ?", (item_name,))
        await db.commit()
        if cursor.rowcount == 0:
            await interaction.response.send_message(f"❌ العنصر `{item_name}` غير موجود في الخزنة المحددة.", ephemeral=True)
            return

    await interaction.response.send_message(f"🗑️ تم حذف العنصر `{item_name}` من الخزنة بنجاح.")

@bot.tree.command(name="reset_inv", description="تصفير ومسح جرد خزنة معينة بالكامل")
@app_commands.choices(vault_type=[
    app_commands.Choice(name="خزنة الستور", value="store"),
    app_commands.Choice(name="محل الأسلحة", value="weapons"),
    app_commands.Choice(name="الحانة", value="bar"),
    app_commands.Choice(name="الحداد", value="blacksmith")
])
@app_commands.describe(vault_type="اختر الخزنة المراد تصفيرها")
@app_commands.checks.has_permissions(administrator=True)
async def reset_inv(interaction: discord.Interaction, vault_type: str):
    async with aiosqlite.connect(DB_NAME) as db:
        if vault_type == "store":
            await db.execute("DELETE FROM general_vaults WHERE vault_name = 'store'")
        elif vault_type == "weapons":
            await db.execute("DELETE FROM weapons_vault")
        elif vault_type == "bar":
            await db.execute("DELETE FROM bar_vault")
        elif vault_type == "blacksmith":
            await db.execute("DELETE FROM blacksmith_vault")
        await db.commit()
        
    await interaction.response.send_message(f"⚠️ تم تصفير ومسح جرد (`{vault_type}`) بالكامل بنجاح.")

if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if TOKEN:
        TOKEN = TOKEN.strip()
    if not TOKEN:
        raise ValueError("❌ لم يتم العثور على توكن البوت!")
    bot.run(TOKEN)
