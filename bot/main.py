import os
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
from aiohttp import web

DB_NAME = "godfather_inventory.db"

async def handle(request):
    return web.Response(text="GodFather Main Bot is running alive!")

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                vault_name TEXT,
                item_name TEXT,
                amount INTEGER,
                PRIMARY KEY (vault_name, item_name)
            )
        ''')
        await db.commit()

class GodfatherBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        app = web.Application()
        app.router.add_get('/', handle)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 8080))
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()

bot = GodfatherBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (Godfather Main Bot)")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Global sync: {len(synced)} commands registered.")
    except Exception as e:
        print(f"❌ Failed to global sync: {e}")

@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def sync(ctx):
    bot.tree.copy_global_to(guild=ctx.guild)
    synced = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(f"✅ تم تزامن {len(synced)} أمر مباشرة مع هذا السيرفر!")

async def update_inventory_data(vault_name: str, items_list: list):
    async with aiosqlite.connect(DB_NAME) as db:
        for name, qty in items_list:
            if name and qty != 0:
                clean_name = name.strip()
                await db.execute('''
                    INSERT INTO inventory (vault_name, item_name, amount) 
                    VALUES (?, ?, ?)
                    ON CONFLICT(vault_name, item_name) 
                    DO UPDATE SET amount = amount + excluded.amount
                ''', (vault_name, clean_name, qty))
        
        await db.execute("DELETE FROM inventory WHERE vault_name = ? AND amount <= 0", (vault_name,))
        await db.commit()

async def build_vault_embed(vault_name: str, title: str, description: str, color: discord.Color):
    embed = discord.Embed(title=title, description=description, color=color)
    
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT item_name, amount FROM inventory WHERE vault_name = ? AND amount > 0 ORDER BY item_name ASC", (vault_name,)) as cursor:
            items = await cursor.fetchall()
            
    if items:
        inv_text = ""
        for item_name, amount in items:
            inv_text += f"• **{item_name} :** {amount:,}\n"
        embed.add_field(name="📦 الموارد المتاحة حالياً:", value=inv_text, inline=False)
    else:
        embed.add_field(name="📦 الموارد المتاحة حالياً:", value="*لا توجد أغراض أو موارد مسجلة حالياً.*", inline=False)
        
    return embed

@bot.tree.command(name="inventory", description="إضافة أو خصم (بالسالب) موارد خزنة الحداد")
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
    await update_inventory_data("blacksmith", items_list)
    embed = await build_vault_embed("blacksmith", "🔨 خزنة الحداد - GODFATHER FAMILY", "تم تحديث جرد الموارد بنجاح.", discord.Color.dark_gray())
    await interaction.followup.send(content="✅ **تم تحديث خزنة الحداد!**", embed=embed)

@bot.tree.command(name="store_inv", description="إضافة أو خصم (بالسالب) أغراض خزنة الستور")
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
    await update_inventory_data("store", items_list)
    embed = await build_vault_embed("store", "🛒 خزنة الستور - GODFATHER FAMILY", "تم تحديث جرد الأغراض بنجاح.", discord.Color.gold())
    await interaction.followup.send(content="✅ **تم تحديث خزنة الستور!**", embed=embed)

@bot.tree.command(name="weapons_inv", description="إضافة أو خصم (بالسالب) أسلحة وذخيرة خزنة الأسلحة")
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
    await update_inventory_data("weapons", items_list)
    embed = await build_vault_embed("weapons", "⚔️ خزنة محل الاسلحة - GODFATHER FAMILY", "تم تحديث جرد الأسلحة والذخيرة بنجاح.", discord.Color.dark_red())
    await interaction.followup.send(content="✅ **تم تحديث خزنة الأسلحة!**", embed=embed)

@bot.tree.command(name="bar_inv", description="إضافة أو خصم (بالسالب) مشروبات/أغراض خزنة الحانة")
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
    await update_inventory_data("bar", items_list)
    embed = await build_vault_embed("bar", "🍺 خزنة الحانة - GODFATHER FAMILY", "تم تحديث جرد الحانة بنجاح.", discord.Color.dark_purple())
    await interaction.followup.send(content="✅ **تم تحديث خزنة الحانة!**", embed=embed)

@bot.tree.command(name="remove_item", description="حذف عنصر معين نهائياً من خزنة محددة")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.choices(vault=[
    app_commands.Choice(name="خزنة الحداد (blacksmith)", value="blacksmith"),
    app_commands.Choice(name="خزنة الستور (store)", value="store"),
    app_commands.Choice(name="خزنة الأسلحة (weapons)", value="weapons"),
    app_commands.Choice(name="خزنة الحانة (bar)", value="bar")
])
async def remove_item(interaction: discord.Interaction, vault: str, item_name: str):
    await interaction.response.defer(ephemeral=True)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM inventory WHERE vault_name = ? AND LOWER(item_name) = LOWER(?)", (vault, item_name.strip()))
        await db.commit()
    await interaction.followup.send(f"🗑️ تم حذف العنصر `{item_name}` من خزنة `{vault}` بنجاح!", ephemeral=True)

@bot.tree.command(name="reset_inv", description="تصفير ومسح جرد خزنة معينة بالكامل")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.choices(vault=[
    app_commands.Choice(name="خزنة الحداد (blacksmith)", value="blacksmith"),
    app_commands.Choice(name="خزنة الستور (store)", value="store"),
    app_commands.Choice(name="خزنة الأسلحة (weapons)", value="weapons"),
    app_commands.Choice(name="خزنة الحانة (bar)", value="bar")
])
async def reset_inv(interaction: discord.Interaction, vault: str):
    await interaction.response.defer(ephemeral=True)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM inventory WHERE vault_name = ?", (vault,))
        await db.commit()
    await interaction.followup.send(f"🧹 تم تصفير جرد الخزنة `{vault}` بنجاح!", ephemeral=True)

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

@bot.tree.command(name="blacksmith", description="عرض خزنة الحداد بالجرد الحالي")
async def blacksmith(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = await build_vault_embed("blacksmith", "🔨 خزنة الحداد - GODFATHER FAMILY", "قائمة الموارد والمعادن المخصصة للحدادة والتصنيع.", discord.Color.dark_gray())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="weapons", description="عرض خزنة محل الأسلحة بالجرد الحالي")
async def weapons(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = await build_vault_embed("weapons", "⚔️ خزنة محل الاسلحة - GODFATHER FAMILY", "قائمة الذخائر والأسلحة المتوفرة في الخزنة.", discord.Color.dark_red())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="store", description="عرض خزنة الستور بالجرد الحالي")
async def store(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = await build_vault_embed("store", "🛒 خزنة الستور - GODFATHER FAMILY", "قائمة الأغراض والمنتجات المتاحة للشراء أو التوزيع.", discord.Color.gold())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="bar", description="عرض خزنة الحانة بالجرد الحالي")
async def bar(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = await build_vault_embed("bar", "🍺 خزنة الحانة - GODFATHER FAMILY", "قائمة المشروبات والمستلزمات الخاصة بالحانة.", discord.Color.dark_purple())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="apply", description="عرض طريقة التقديم للانضمام لعائلة القودفاذر")
async def apply(interaction: discord.Interaction):
    embed = discord.Embed(title="📜 التقديم على عائلة GODFATHER", color=discord.Color.red())
    embed.description = "مرحباً بك! للانضمام إلى العائلة، يرجى فتح تذكرة تقديم وتعبئة البيانات المطلوبة ليتم مراجعتها من قبل الإدارة."
    await interaction.response.send_message(embed=embed)

TOKEN = os.environ.get("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
