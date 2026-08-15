import os
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DB_NAME = 'attendance.db'

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS active_sessions (
                user_id INTEGER PRIMARY KEY,
                role_type TEXT,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.commit()

class IndividualsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="بدء تحضير أفراد", style=discord.ButtonStyle.green, custom_id="ind_start")
    async def start_ind(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT role_type FROM active_sessions WHERE user_id = ?", (interaction.user.id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await interaction.response.send_message(f"❌ أنت مسجل بالفعل في نظام ({row[0]})!", ephemeral=True)
                    return
            await db.execute("INSERT INTO active_sessions (user_id, role_type) VALUES (?, ?)", (interaction.user.id, "أفراد"))
            await db.commit()
        await interaction.response.send_message("✅ تم تسجيل دخولك بنجاح في كرت **الأفراد**!", ephemeral=True)

    @discord.ui.button(label="إنهاء تحضير أفراد", style=discord.ButtonStyle.red, custom_id="ind_end")
    async def end_ind(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT role_type FROM active_sessions WHERE user_id = ?", (interaction.user.id,)) as cursor:
                row = await cursor.fetchone()
                if not row or row[0] != "أفراد":
                    await interaction.response.send_message("❌ أنت غير مسجل في تحضير الأفراد!", ephemeral=True)
                    return
            await db.execute("DELETE FROM active_sessions WHERE user_id = ?", (interaction.user.id,))
            await db.commit()
        await interaction.response.send_message("🛑 تم تسجيل خروجك بنجاح من كرت **الأفراد**!", ephemeral=True)

class OfficersView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="بدء تحضير ضباط", style=discord.ButtonStyle.primary, custom_id="off_start")
    async def start_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT role_type FROM active_sessions WHERE user_id = ?", (interaction.user.id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    await interaction.response.send_message(f"❌ أنت مسجل بالفعل في نظام ({row[0]})!", ephemeral=True)
                    return
            await db.execute("INSERT INTO active_sessions (user_id, role_type) VALUES (?, ?)", (interaction.user.id, "ضباط"))
            await db.commit()
        await interaction.response.send_message("✅ تم تسجيل دخولك بنجاح في كرت **الضباط**!", ephemeral=True)

    @discord.ui.button(label="إنهاء تحضير ضباط", style=discord.ButtonStyle.danger, custom_id="off_end")
    async def end_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT role_type FROM active_sessions WHERE user_id = ?", (interaction.user.id,)) as cursor:
                row = await cursor.fetchone()
                if not row or row[0] != "ضباط":
                    await interaction.response.send_message("❌ أنت غير مسجل في تحضير الضباط!", ephemeral=True)
                    return
            await db.execute("DELETE FROM active_sessions WHERE user_id = ?", (interaction.user.id,))
            await db.commit()
        await interaction.response.send_message("🛑 تم تسجيل خروجك بنجاح من كرت **الضباط**!", ephemeral=True)

@bot.event
async def on_ready():
    await init_db()
    bot.add_view(IndividualsView())
    bot.add_view(OfficersView())
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)
    print(f"Logged in as {bot.user}")

@bot.tree.command(name="setup_individuals", description="تنزيل كرت تحضير الأفراد")
@app_commands.checks.has_permissions(administrator=True)
async def setup_ind(interaction: discord.Interaction):
    embed = discord.Embed(title="📋 تحضير الأفراد", description="استخدم الأزرار أدناه للتحضير أو الخروج.", color=discord.Color.green())
    await interaction.channel.send(embed=embed, view=IndividualsView())
    await interaction.response.send_message("تم تنزيل كرت الأفراد.", ephemeral=True)

@bot.tree.command(name="setup_officers", description="تنزيل كرت تحضير الضباط")
@app_commands.checks.has_permissions(administrator=True)
async def setup_off(interaction: discord.Interaction):
    embed = discord.Embed(title="⚔️ تحضير الضباط", description="استخدم الأزرار أدناه للتحضير أو الخروج.", color=discord.Color.blue())
    await interaction.channel.send(embed=embed, view=OfficersView())
    await interaction.response.send_message("تم تنزيل كرت الضباط.", ephemeral=True)

TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
