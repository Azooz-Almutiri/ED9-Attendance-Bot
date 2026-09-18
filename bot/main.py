import os
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from datetime import datetime, timedelta, timezone
from aiohttp import web
import asyncio
from collections import defaultdict, deque
import re

# ==================== إعدادات التوقيت (توقيت مكة المكرمة UTC+3) ====================
MAKKAH_TZ = timezone(timedelta(hours=3))

def get_makkah_now():
    return datetime.now(MAKKAH_TZ)

def format_makkah_time(dt_obj):
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc).astimezone(MAKKAH_TZ)
    else:
        dt_obj = dt_obj.astimezone(MAKKAH_TZ)
    return dt_obj.strftime("%I:%M %p").replace("AM", "صباحاً").replace("PM", "مساءً")

DB_NAME = "attendance.db"

# المعرفات الخاصة
APPLY_CHANNEL_ID = 1526075774216437971
RULES_CHANNEL_ID = 1526075771079102464
WAITING_CHANNEL_ID = 1526076563735445595
ACCEPTED_ROLE_NAME = "✔️〡مقبول مبدئياً بالادارة ◂"
COMPENSATION_MANAGER_ROLE_ID = 1526074882893418626
SECURITY_NOTIFY_ROLE_ID = 1526074792564756510 

# المعرفات الجديدة المطلوبة
BROADCAST_TARGET_ROLE_ID = 1550542997010251927  # رتبة البرودكاست المخصصة
WELCOME_ROLE_ID = 1550543013317447680         # رتبة العضو الجديد عند الدخول
WELCOME_CHANNEL_ID = 1550543152778137600      # روم مرحبا بك (يرجى تعديل الآيدي إذا اختلف، تم وضع قيمة افتراضية أو يمكنك تعديله)
FAMILY_APPLY_CHANNEL_ID = 1550543173300781116 # روم طلب تقديم العائلة
RULES_NEW_CHANNEL_ID = 1550543164723564636    # روم القوانين الجديد

CHECK_INTERVAL = 3600         
CONFIRM_TIMEOUT = 1800         

periodic_check_tasks = {}

spam_content_tracker = defaultdict(lambda: deque(maxlen=10))
channel_delete_tracker = defaultdict(lambda: deque(maxlen=10))
channel_update_tracker = defaultdict(lambda: deque(maxlen=10))

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
        await db.execute('''
            CREATE TABLE IF NOT EXISTS vrp_ids (
                id_number INTEGER PRIMARY KEY,
                holder TEXT,
                assigned_by TEXT,
                assigned_at TIMESTAMP
            )
        ''')

        for i in range(1, 501):
            await db.execute("INSERT OR IGNORE INTO vrp_ids (id_number, holder) VALUES (?, ?)", (i, "متاح 🟢"))
            await db.execute("INSERT OR IGNORE INTO vrp_ids (id_number, holder) VALUES (?, ?)", (-i, "متاح 🟢"))

        await db.commit()

def is_compensation_manager(member: discord.Member) -> bool:
    return any(role.id == COMPENSATION_MANAGER_ROLE_ID for role in getattr(member, "roles", []))

async def send_security_alert_to_role(guild: discord.Guild, embed: discord.Embed):
    for member in guild.members:
        if member.bot:
            continue
        if any(role.id == SECURITY_NOTIFY_ROLE_ID for role in member.roles):
            try:
                await member.send(embed=embed)
            except Exception:
                pass

class ConfirmPresenceView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=CONFIRM_TIMEOUT)
        self.user_id = user_id
        self.confirmed = False

    @discord.ui.button(label="تأكيد التواجد 🟢", style=discord.ButtonStyle.green, custom_id="confirm_presence_btn")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ هذا التنبيه ليس مخصصاً لك!", ephemeral=True)
            return

        self.confirmed = True
        button.disabled = True
        button.label = "تم التأكيد ✅"
        await interaction.response.edit_message(content="✅ تم تأكيد استمرار تحضيرك بنجاح!", view=self)
        self.stop()

async def start_periodic_check(member: discord.Member):
    try:
        while True:
            await asyncio.sleep(CHECK_INTERVAL)
            async with aiosqlite.connect(DB_NAME) as db:
                async with db.execute("SELECT rowid, start_time FROM attendance WHERE user_id = ? AND end_time IS NULL", (member.id,)) as cursor:
                    active_session = await cursor.fetchone()

            if not active_session:
                break

            view = ConfirmPresenceView(member.id)
            try:
                await member.send(
                    "⚠️ **تأكيد حضور دوري:**\n"
                    "لقد مرت ساعة على تواجدك في التحضير. هل ما زلت متصلاً؟\n"
                    "يرجى الضغط على الزر أدناه خلال **30 دقيقة** لتأكيد تواجدك، وإلا سيتم تسجيل خروجك تلقائياً.",
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

                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("UPDATE attendance SET end_time = ?, duration_minutes = ? WHERE rowid = ?", 
                                     (now.isoformat(), duration, row_id))
                    await db.commit()

                try:
                    h, m = divmod(duration, 60)
                    await member.send(f"❌ **تم تسجيل خروجك تلقائياً** لعدم إجابتك على تأكيد التواجد.\n⏱️ مدة التواجد: `{h} ساعة و {m} دقيقة`.")
                except Exception:
                    pass
                break
    except asyncio.CancelledError:
        pass
    finally:
        periodic_check_tasks.pop(member.id, None)

class AttendanceView(discord.ui.View):
    def __init__(self, role_type: str):
        super().__init__(timeout=None)
        self.role_type = role_type

    @discord.ui.button(label="بدء التحضير", style=discord.ButtonStyle.green, custom_id="start_attendance")
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        now = get_makkah_now()

        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT start_time FROM attendance WHERE user_id = ? AND end_time IS NULL", (user.id,)) as cursor:
                active_session = await cursor.fetchone()

            if active_session:
                await interaction.response.send_message("❌ أنت مسجل دخول بالفعل!", ephemeral=True)
                return

            await db.execute("INSERT INTO attendance (user_id, user_name, type, start_time) VALUES (?, ?, ?, ?)",
                             (user.id, user.display_name, self.role_type, now.isoformat()))
            await db.commit()

        if user.id in periodic_check_tasks:
            periodic_check_tasks[user.id].cancel()

        periodic_check_tasks[user.id] = asyncio.create_task(start_periodic_check(user))
        await interaction.response.send_message(f"✅ تم تسجيل دخولك كـ ({self.role_type}) الساعة `{format_makkah_time(now)}`.", ephemeral=True)

    @discord.ui.button(label="إنهاء التحضير", style=discord.ButtonStyle.red, custom_id="end_attendance")
    async def end_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        now = get_makkah_now()

        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT rowid, start_time FROM attendance WHERE user_id = ? AND end_time IS NULL", (user.id,)) as cursor:
                active_session = await cursor.fetchone()

            if not active_session:
                await interaction.response.send_message("❌ أنت غير مسجل دخول حالياً!", ephemeral=True)
                return

            row_id, start_str = active_session
            try:
                duration = max(0, int((now - datetime.fromisoformat(str(start_str))).total_seconds() // 60))
            except Exception:
                duration = 0

            await db.execute("UPDATE attendance SET end_time = ?, duration_minutes = ? WHERE rowid = ?", (now.isoformat(), duration, row_id))
            await db.commit()

        if user.id in periodic_check_tasks:
            periodic_check_tasks[user.id].cancel()
        periodic_check_tasks.pop(user.id, None)

        hours, mins = divmod(duration, 60)
        await interaction.response.send_message(f"🔴 تم تسجيل خروجك. مدة تواجدك: `{hours} ساعة و {mins} دقيقة`", ephemeral=True)

    @discord.ui.button(label="حالة تحضيري ⏱️", style=discord.ButtonStyle.secondary, custom_id="status_attendance")
    async def status_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        now = get_makkah_now()

        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT start_time FROM attendance WHERE user_id = ? AND end_time IS NULL", (user.id,)) as cursor:
                active_session = await cursor.fetchone()
            async with db.execute("SELECT SUM(duration_minutes) FROM attendance WHERE user_id = ? AND start_time >= ?", (user.id, (now - timedelta(days=7)).isoformat())) as cursor:
                weekly_minutes = (await cursor.fetchone())[0] or 0

        w_h, w_m = divmod(weekly_minutes, 60)
        if active_session:
            try:
                c_min = max(0, int((now - datetime.fromisoformat(str(active_session[0]))).total_seconds() // 60))
            except Exception:
                c_min = 0
            c_h, c_m = divmod(c_min, 60)
            msg = f"🟢 مسجل دخول منذ {c_h}س و {c_m}د.\n📊 ساعات آخر 7 أيام: {w_h}س و {w_m}د."
        else:
            msg = f"🔴 غير مسجل دخول.\n📊 ساعات آخر 7 أيام: {w_h}س و {w_m}د."
        await interaction.response.send_message(msg, ephemeral=True)

class IDManagementModal(discord.ui.Modal, title="إدارة الآيديات"):
    id_input = discord.ui.TextInput(
        label="رقم الآيدي (من 1 إلى 500 أو بالسالب)",
        placeholder="مثال: 55",
        required=True,
        max_length=5
    )
    holder_input = discord.ui.TextInput(
        label="اسم صاحب الآيدي أو (متاح 🟢)",
        placeholder="اكتب اسم العضو أو 'متاح 🟢'",
        required=True,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            id_val = int(self.id_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ رقم الآيدي يجب أن يكون رقماً صحيحاً!", ephemeral=True)
            return

        new_holder = self.holder_input.value.strip()
        assigned_by = str(interaction.user)
        assigned_now = get_makkah_now().isoformat()

        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT id_number FROM vrp_ids WHERE id_number = ?", (id_val,)) as cursor:
                exists = await cursor.fetchone()

            if not exists:
                await interaction.response.send_message(f"❌ رقم الآيدي `{id_val}` غير موجود في قاعدة البيانات.", ephemeral=True)
                return

            await db.execute(
                "UPDATE vrp_ids SET holder = ?, assigned_by = ?, assigned_at = ? WHERE id_number = ?",
                (new_holder, assigned_by, assigned_now, id_val)
            )
            await db.commit()

        await interaction.response.send_message(f"✅ تم تحديث بيانات الآيدي `{id_val}` بنجاح ليكون بواسطة: `{new_holder}`", ephemeral=True)

class IDManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تحديث / تعيين آيدي 🆔", style=discord.ButtonStyle.blurple, custom_id="manage_vrp_id_btn")
    async def manage_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_compensation_manager(interaction.user):
            await interaction.response.send_message("❌ هذا الزر مخصص لمسؤولي التعويض فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(IDManagementModal())

class AttendanceBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        self.add_view(AttendanceView("إدارة"))
        self.add_view(AttendanceView("داخلية"))
        self.add_view(AttendanceView("أمن الدولة"))
        self.add_view(AttendanceView("عصابات"))
        self.add_view(AttendanceView("بنات"))

        self.add_view(IDManagementView())

        app = web.Application()
        app.router.add_get('/', handle)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 10000))  
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()

bot = AttendanceBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Global sync: {len(synced)} commands registered.")
    except Exception as e:
        print(f"❌ Failed to sync: {e}")

# ==================== نظام الترحيب بالأعضاء الجدد ====================
@bot.event
async def on_member_join(member: discord.Member):
    # 1. إعطاء الرتبة المحددة تلقائياً
    role = member.guild.get_role(WELCOME_ROLE_ID)
    if role:
        try:
            await member.add_roles(role, reason="ترحيب السيرفر التلقائي")
        except Exception:
            pass

    # 2. إرسال رسالة الترحيب في روم مرحبا بك
    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if channel:
        welcome_text = (
            f"مرحباً بك {member.mention} في السيرفر! 🎉\n"
            f"إذا كنت ترغب بالانخراط أو دخول العائلة، يرجى التوجه وتقديم الطلب في روم: <#{FAMILY_APPLY_CHANNEL_ID}>\n"
            f"ولا تنسَ قراءة القوانين والتعليمات في روم: <#{RULES_NEW_CHANNEL_ID}> لضمان عدم مخالفتك."
        )
        try:
            await channel.send(welcome_text)
        except Exception:
            pass

# ==================== أنظمة الحماية الأمنية المحدثة ====================

@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    now = datetime.now()
    guild = channel.guild
    
    handler_member = None
    try:
        async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.channel_delete):
            if entry.target.id == channel.id:
                handler_member = entry.user
                break
    except Exception:
        pass

    alert_embed = discord.Embed(
        title="🚨 تنبيه أمني: حذف روم بدون صلاحية!",
        color=discord.Color.red(),
        timestamp=get_makkah_now()
    )
    alert_embed.add_field(name="👤 العضو الحذف", value=f"{handler_member.mention} (`{handler_member.id}`)" if handler_member else "غير معروف", inline=False)
    alert_embed.add_field(name="📂 الروم المحذوف", value=f"#{channel.name} (`{channel.id}`)", inline=True)
    alert_embed.add_field(name="📌 نوع الروم", value=str(channel.type), inline=True)
    
    await send_security_alert_to_role(guild, alert_embed)

    if handler_member and not handler_member.bot:
        channel_delete_tracker[handler_member.id].append(now)
        recent_deletes = [t for t in channel_delete_tracker[handler_member.id] if now - t < timedelta(minutes=3)]
        
        if len(recent_deletes) >= 3:
            try:
                await handler_member.timeout(timedelta(days=7), reason="حماية السيرفر: حذف 3 رومات أو أكثر في أقل من 3 دقائق.")
            except Exception:
                pass

@bot.event
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
    if before.name != after.name:
        now = datetime.now()
        guild = after.guild
        
        handler_member = None
        try:
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.channel_update):
                if entry.target.id == after.id:
                    handler_member = entry.user
                    break
        except Exception:
            pass

        if handler_member and not handler_member.bot:
            channel_update_tracker[handler_member.id].append(now)
            recent_updates = [t for t in channel_update_tracker[handler_member.id] if now - t < timedelta(minutes=3)]
            
            if len(recent_updates) >= 3:
                try:
                    await handler_member.timeout(timedelta(days=7), reason="حماية السيرفر: تغيير أسماء 3 شاتات في أقل من 3 دقائق.")
                except Exception:
                    pass

                alert_embed = discord.Embed(
                    title="🚨 تنبيه أمني تلقائي: تغيير متكرر لأسماء الشاتات",
                    color=discord.Color.red(),
                    timestamp=get_makkah_now()
                )
                alert_embed.add_field(name="👤 العضو المخالف", value=f"{handler_member.mention} (`{handler_member.id}`)", inline=False)
                alert_embed.add_field(name="📌 التفاصيل", value=f"قام بتغيير أسماء الشاتات (مثل: {after.name}) 3 مرات أو أكثر.", inline=False)
                alert_embed.add_field(name="🛡️ الإجراء التلقائي", value="تم إعطاء العضو تايم أوت (7 أيام).", inline=False)
                
                await send_security_alert_to_role(guild, alert_embed)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    user_id = message.author.id
    now = datetime.now()
    content = message.content.strip()

    link_pattern = re.compile(
        r'(https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9-]+\.(com|gg|net|org|me|xyz|info|co|ru|tk|ml|ga|cf|gq|US|TO|CC)/[^\s]*|discord\.gg/[^\s]+)',
        re.IGNORECASE
    )
    has_link = link_pattern.search(content)

    if has_link:
        try:
            await message.delete()
            await message.author.timeout(timedelta(days=7), reason="حماية السيرفر: إرسال رابط ممنوع.")
        except Exception:
            pass

        alert_embed = discord.Embed(
            title="🚨 تنبيه أمني: حظر رابط وإعطاء تايم أوت أسبوع",
            color=discord.Color.red(),
            timestamp=get_makkah_now()
        )
        alert_embed.add_field(name="👤 العضو المخالف", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
        alert_embed.add_field(name="📍 الروم", value=message.channel.mention, inline=True)
        alert_embed.add_field(name="💬 الرابط المرسل", value=f"`{content[:150]}`", inline=False)
        alert_embed.add_field(name="🛡️ الإجراء التلقائي", value="حذف الرسالة + تايم أوت لمدة 7 أيام + إرسال تنبيه بالخاص.", inline=False)

        await send_security_alert_to_role(message.guild, alert_embed)
        return

    if content:
        spam_content_tracker[user_id].append((now, content))
        recent_same_msgs = [t for t, c in spam_content_tracker[user_id] if (now - t < timedelta(seconds=30)) and (c == content)]
        
        if len(recent_same_msgs) > 3:
            try:
                await message.delete()
                await message.author.timeout(timedelta(days=7), reason="حماية السيرفر: سبام تكرار رسائل متطابقة.")
            except Exception:
                pass

            alert_embed = discord.Embed(
                title="🚨 تحذير أمني تلقائي: اكتشاف سبام / تكرار سريع",
                color=discord.Color.red(),
                timestamp=get_makkah_now()
            )
            alert_embed.add_field(name="👤 العضو المخالف", value=f"{message.author.mention} (`{message.author.id}`)", inline=False)
            alert_embed.add_field(name="📍 الروم", value=message.channel.mention, inline=True)
            alert_embed.add_field(name="💬 النص المكرر", value=f"`{content[:100]}`", inline=False)
            alert_embed.add_field(name="🛡️ الإجراء التلقائي", value="تم حذف الرسالة المكررة + تايم أوت (7 أيام).", inline=False)
            
            await send_security_alert_to_role(message.guild, alert_embed)
            return

    if message.channel.id == APPLY_CHANNEL_ID:
        content_txt = message.content.strip()
        required_keywords = ["الأسم", "العمر", "رقم الهوية", "ساعات التواجد", "هل كنت إداري", "الخبرات"]
        if all(kw in content_txt for kw in required_keywords):
            role = discord.utils.get(message.guild.roles, name=ACCEPTED_ROLE_NAME)
            if role and role not in message.author.roles:
                try:
                    await message.author.add_roles(role)
                except Exception:
                    pass

            text_response = (
                f"✨ **أهلاً وحياك الله في تقديم الإدارة**\n\n"
                f"أهلاً بك {message.author.mention}, تم استقبال تقديمك وتزويدك برتبة مقبول مبدئياً بنجاح!\n\n"
                f"📌 **التعليمات والإرشادات:**\n"
                f"• يرجى مراجعة وقراءة قوانين الإدارة في روم: <#{RULES_CHANNEL_ID}>\n"
                f"• ⚠️ **علماً بأنه يوجد اختبار خاص بالإدارة** عند تقديم المقابلة.\n"
                f"• بعد الانتهاء والمراجعة, يرجى التوجه في روم: <#{WAITING_CHANNEL_ID}>\n\n"
                f"نتمنى لك كامل التوفيق!"
            )
            try:
                await message.reply(content=text_response)
            except Exception:
                pass
            return

    await bot.process_commands(message)

# ==================== الأوامر الإدارية وأوامر التحضير ====================

@bot.command(name="مسح")
@commands.has_permissions(manage_messages=True)
async def clear_messages(ctx, amount: int):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    
    if amount <= 0:
        await ctx.send("❌ يرجى تحديد عدد أكبر من الصفر!", delete_after=5)
        return

    try:
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: not m.pinned)
        await ctx.send(f"✅ تم حذف `{len(deleted)}` رسالة بنجاح.", delete_after=4)
    except discord.HTTPException:
        await ctx.send("❌ تعذر حذف بعض الرسائل لأنها قد تكون أقدم من 14 يوماً (قيود ديسكورد).", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ حدث خطأ أثناء مسح الرسائل: {e}", delete_after=5)

@clear_messages.error
async def clear_messages_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ ليس لديك صلاحية `Manage Messages` لاستخدام هذا الأمر!", delete_after=5)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ الاستخدام الصحيح: `#مسح [العدد]` (مثال: `#مسح 10`)", delete_after=5)
    else:
        await ctx.send(f"❌ حدث خطأ: {error}", delete_after=5)

@bot.command(name="bc")
@commands.has_permissions(administrator=True)
async def broadcast_cmd(ctx, *, message_content: str = None):
    try:
        await ctx.message.delete()
    except Exception:
        pass

    if not message_content:
        await ctx.send("❌ يرجى كتابة الرسالة المراد إرسالها بعد الأمر!\nمثال: `!bc السلام عليكم حياكم الله`", delete_after=6)
        return

    # التحقق من وجود الرتبة المستهدفة في السيرفر
    target_role = ctx.guild.get_role(BROADCAST_TARGET_ROLE_ID)
    if not target_role:
        await ctx.send("❌ لم يتم العثور على رتبة البرودكاست المحددة في هذا السيرفر!", delete_after=6)
        return

    status_msg = await ctx.send("⏳ جاري إرسال البرودكاست لأصحاب الرتبة المحددة...")
    sent, failed = 0, 0

    try:
        # إرسال الرسالة فقط لمن يحمل الرتبة المحددة
        for member in target_role.members:
            if member.bot:
                continue
            try:
                await member.send(message_content)
                sent += 1
                await asyncio.sleep(0.1)
            except Exception:
                failed += 1
    except Exception as e:
        await status_msg.edit(content=f"❌ حدث خطأ أثناء إرسال البرودكاست: {e}")
        return

    await status_msg.edit(content=f"✅ تم الانتهاء من إرسال البرودكاست للرتبة المستهدفة!\n📤 تم الإرسال لـ {sent} عضو\n❌ تعذر الإرسال لـ {failed} عضو (خاص مقفل)")

@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def manual_sync(ctx):
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ تم مزامنة {len(synced)} من أوامر السلاش بنجاح!", delete_after=5)
    except Exception as e:
        await ctx.send(f"❌ فشلت المزامنة: {e}", delete_after=5)

@bot.tree.command(name="setup_attendance", description="تنزيل لوحة التحضير لأي قطاع وفي أي روم تحدده")
@app_commands.choices(section=[
    app_commands.Choice(name="إدارة", value="إدارة"),
    app_commands.Choice(name="داخلية", value="داخلية"),
    app_commands.Choice(name="أمن الدولة", value="أمن الدولة"),
    app_commands.Choice(name="عصابات", value="عصابات"),
    app_commands.Choice(name="بنات", value="بنات"),
])
@app_commands.describe(
    section="اختر القطاع",
    channel="اختر الروم الذي تريد إرسال اللوحة إليه"
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_attendance(interaction: discord.Interaction, section: str, channel: discord.TextChannel):
    embed = discord.Embed(
        title=f"🛡️ تحضير قطاع {section}", 
        description="اضغط الأزرار بالأسفل للتسجيل.", 
        color=discord.Color.red(), 
        timestamp=get_makkah_now()
    )
    try:
        await channel.send(embed=embed, view=AttendanceView(section))
        await interaction.response.send_message(f"✅ تم تنزيل لوحة تحضير قطاع ({section}) بنجاح في الروم {channel.mention}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ حدث خطأ أثناء إرسال اللوحة للروم المحدد: {e}", ephemeral=True)

@bot.command(name="setup_ids")
@commands.has_permissions(administrator=True)
async def setup_ids_panel(ctx):
    try:
        await ctx.message.delete()
    except Exception:
        pass
    embed = discord.Embed(title="🆔 إدارة آيديات VRP", description="مخصصة لمسؤولي التعويض لإدارة الآيديات.", color=discord.Color.gold(), timestamp=get_makkah_now())
    await ctx.send(embed=embed, view=IDManagementView())

@bot.tree.command(name="id_search", description="الاستعلام عن حالة آيدي معين")
async def id_search(interaction: discord.Interaction, id_number: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT holder, assigned_by, assigned_at FROM vrp_ids WHERE id_number = ?", (id_number,)) as cursor:
            row = await cursor.fetchone()

    if not row:
        await interaction.response.send_message(f"❌ الآيدي `{id_number}` غير موجود.", ephemeral=True)
        return

    holder, assigned_by, assigned_at = row
    embed = discord.Embed(title=f"🔍 استعلام عن الآيدي [{id_number}]", color=discord.Color.green() if "متاح" in holder else discord.Color.red(), timestamp=get_makkah_now())
    embed.add_field(name="👤 صاحب الآيدي", value=holder, inline=False)
    if "متاح" not in holder:
        embed.add_field(name="🛠️ بواسطة", value=assigned_by or "غير معروف", inline=True)
        embed.add_field(name="⏱️ الوقت", value=assigned_at or "غير معروف", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if TOKEN:
        TOKEN = TOKEN.strip()
    if not TOKEN:
        raise ValueError("❌ لم يتم العثور على توكن البوت!")
    bot.run(TOKEN)
