import discord
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput
import subprocess
import os
import re
import requests
import asyncio

# إعداد البوت بـ Intents.all()
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="~#%c", intents=intents)

# ملفات البوتات المرتبطة بالأسماء
BOT_FILES = {
    "Sattaros": "sattaros.py",
    "Night": "night2.py",
    "Marr1ed": "mar1d.py",
    "Mofaj": "mofa.py"
}

# عمليات التشغيل الجارية لكل ملف
running_processes = {}

async def check_token_validity(token):
    """تحقق من صلاحية التوكن"""
    headers = {
        "Authorization": token,
        "User-Agent": "Mozilla/5.0"
    }
    try:
        response = requests.get("https://discord.com/api/v9/users/@me", headers=headers)
        return response.status_code == 200
    except:
        return False

async def start_bot(bot_name):
    """تشغيل بوت معين"""
    file_path = BOT_FILES[bot_name]
    if os.path.exists(file_path):
        if bot_name in running_processes:
            try:
                running_processes[bot_name].kill()
            except:
                pass
        
        try:
            proc = subprocess.Popen(["python3", file_path])
            running_processes[bot_name] = proc
            return True
        except Exception as e:
            print(f"Error starting {bot_name}: {e}")
            return False
    return False

async def start_all_bots():
    """تشغيل جميع البوتات عند بدء التشغيل"""
    for bot_name in BOT_FILES.keys():
        await start_bot(bot_name)
        await asyncio.sleep(1)  # تأخير بسيط بين تشغيل كل بوت

# Modal لإدخال التوكن
class TokenModal(Modal):
    def __init__(self, bot_name):
        super().__init__(title=f"Token for {bot_name}")
        self.bot_name = bot_name
        self.token = TextInput(
            label="التوكن",
            placeholder="أدخل التوكن هنا:",
            style=discord.TextStyle.short
        )
        self.add_item(self.token)

    async def on_submit(self, interaction: discord.Interaction):
        file_path = BOT_FILES[self.bot_name]
        new_token = self.token.value.strip()

        if not os.path.exists(file_path):
            await interaction.response.send_message("❌ خطأ 5524", ephemeral=True)
            return

        # التحقق من صلاحية التوكن
        if not await check_token_validity(new_token):
            await interaction.response.send_message("❌ التوكن غير صالح", ephemeral=True)
            return

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # استبدال التوكن بغض النظر عما إذا كان نفس التوكن الحالي
        updated = re.sub(r'USER_TOKEN\s*=\s*"([^"]+)"', f'USER_TOKEN = "{new_token}"', content)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(updated)

        # إعادة تشغيل الملف
        success = await start_bot(self.bot_name)
        
        if success:
            await interaction.response.send_message(f"✅ تم تحديث وتفعيل **{self.bot_name}** بنجاح", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ تم تحديث التوكن ولكن حدث خطأ في التشغيل", ephemeral=True)

# القائمة المنسدلة
class SelectBot(View):
    def __init__(self):
        super().__init__(timeout=None)
        select = Select(
            placeholder="اختر الحساب لتحديث التوكن",
            options=[discord.SelectOption(label=name, value=name) for name in BOT_FILES.keys()],
            custom_id="select_bot"
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        bot_name = interaction.data['values'][0]
        await interaction.response.send_modal(TokenModal(bot_name))

# الزر الرئيسي
class TokenButton(View):
    def __init__(self):
        super().__init__(timeout=None)
        button = Button(
            label="تفعيل",
            style=discord.ButtonStyle.primary,
            custom_id="send_button"
        )
        button.callback = self.button_callback
        self.add_item(button)

    async def button_callback(self, interaction: discord.Interaction):
        await interaction.response.send_message("اختر الحساب:", view=SelectBot(), ephemeral=True)

# الاستماع لأمر +send
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.content.lower().startswith("+send"):
        view = TokenButton()
        embed = discord.Embed(
            title="⚙️ إدارة التوكنات",
            description="اضغط على الزر لاختيار الحساب وتفعيلة.",
            color=discord.Color.green()
        )
        await message.channel.send(embed=embed, view=view)

# عند تشغيل البوت
@bot.event
async def on_ready():
    print(f'Working Bot {bot.user}')
    await start_all_bots()  # تشغيل جميع البوتات عند بدء التشغيل

# تشغيل البوت
bot.run("MTQwMDc0NTE3NjIyOTc0MDU5NA.G4U_Kl.D1v5sxFFk581B340GT0769AVv5c0GreozrRAuQ")