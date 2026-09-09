# --- نظام الأغاني (Music Commands) ---
@bot.tree.command(name="play", description="تشغيل مقطع صوتي أو أغنية من يوتيوب")
async def play(interaction: discord.Interaction, search: str):
    if not interaction.user.voice:
        await interaction.response.send_message("❌ يجب أن تكون متصلاً بروم صوتي لتشغيل الأغاني!", ephemeral=True)
        return

    await interaction.response.defer()
    
    voice_channel = interaction.user.voice.channel
    if interaction.guild.voice_client is None:
        await voice_channel.connect()
    elif interaction.guild.voice_client.channel != voice_channel:
        await interaction.guild.voice_client.move_to(voice_channel)

    try:
        player = await YTDLSource.from_url(search, loop=bot.loop, stream=True)
        interaction.guild.voice_client.play(player, after=lambda e: print(f'Player error: {e}') if e else None)
        await interaction.followup.send(f"🎶 **جاري تشغيل الآن:** `{player.title}`")
    except Exception as e:
        await interaction.followup.send(f"❌ حدث خطأ أثناء تشغيل الأغنية: {e}")

@bot.tree.command(name="skip", description="تخطي الأغنية الحالية")
async def skip(interaction: discord.Interaction):
    await interaction.response.defer()
    if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
        interaction.guild.voice_client.stop()
        await interaction.followup.send("⏭️ **تم تخطي الأغنية!**")
    else:
        await interaction.followup.send("❌ لا توجد أغنية تعمل حالياً لتخطيها.")

@bot.tree.command(name="stop", description="إيقاف الأغنية وإخراج البوت من الروم الصوتي")
async def stop(interaction: discord.Interaction):
    await interaction.response.defer()
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.followup.send("🛑 **تم إيقاف الأغنية ومغادرة الروم الصوتي.**")
    else:
        await interaction.followup.send("❌ البوت ليس متصلاً بأي روم صوتي أصلاً.")
