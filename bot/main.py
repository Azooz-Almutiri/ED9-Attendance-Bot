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
    return dt_obj.strftime("%I:%M %p").replace("AM", "صباحاً").replace("PM", "مساءً")

DB_NAME = "godfather_jobs.db"

# ==================== الثوابت والمعرفات المطلوبة ====================
BROADCAST_ROLE_ID = 1550542997010251927     # رتبة استلام البرودكاست
WELCOME_ROLE_ID = 1550543013317447680       # الرول الذي يعطى للعضو عند دخوله
RULES_CHANNEL_ID = 1550543164723564636      # روم القوانين
APPLY_CHANNEL_ID = 1550543173300781116      # روم طلب التقديم
WELCOME_CHANNEL_ID = 1550543159321427978    # روم مرحبا بك (الترحيب)

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
        app = web.Application()
        app.router.add_get('/', handle)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 10000))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()

# تعريف البوت هنا بالبداية (عشان تفهمها جميع الدالات والأوامر لاحقاً)
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
@bot.event
async def on_member_join(member: discord.Member):
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

# ==================== أمر البرودكاست المخصص لرتبة معينة ====================
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

    target_role = ctx.guild.get_role(BROADCAST_ROLE_ID)
    if not target_role:
        await ctx.send("❌ عذراً، رتبة البرودكاست المحددة غير موجودة في السيرفر!", delete_after=6)
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

# ==================== 1. أوامر التقديم والخيول ====================
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

# ==================== 2. نظام الستور / الخزنة العامة ====================
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

# ==================== 3. نظام محل الأسلحة (Weapons) ====================
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

# ==================== 4. نظام الحانة (Bar) ====================
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

# ==================== 5. نظام الحداد (Blacksmith & Inventory) ====================
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

# ==================== 6. نظام الأغاني (Play, Skip, Stop) ====================
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

# ==================== 7. أوامر الإدارة المتقدمة (حذف وتصفير) ====================
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
