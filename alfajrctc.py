import discord
from discord.ext import commands
import json
import os
import asyncio
from typing import Dict, Optional
import datetime

# ------------------- الإعدادات الرئيسية ------------------- #
MAIN_BOT_TOKEN = "MTQwNjk0NTM2NTgzMTQ1NDc2MQ.GwSH4M.qyMRLPDWuys4Av5lzuf8Fw4Se2OEyZj5qpd-w4"
ADMIN_ROLE_ID = 1406948753830580305
BOT_DATA_FILE = "bots_data.json"
# ----------------------------------------------------------- #

# --- دوال التعامل مع البيانات ---
def load_bots_data() -> Dict:
    if not os.path.exists(BOT_DATA_FILE):
        return {}
    try:
        with open(BOT_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_bots_data(data: Dict):
    with open(BOT_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- متغيرات عامة ---
running_bots: Dict[str, Dict] = {}
bots_data = load_bots_data()

# --- إعداد البوت الرئيسي ---
intents = discord.Intents.all()

bot = commands.Bot(command_prefix="/<", intents=intents, help_command=None)

@bot.event
async def on_ready():
    print(f'Main Bot Logged in as {bot.user}')
    print(f'Prefix is: /<')
    bot.add_view(PanelView())
    await restart_all_bots()

# --- نافذة تفعيل البوت (Modal) ---
class ActivationModal(discord.ui.Modal, title="تفعيل خدمة بوت"):
    token = discord.ui.TextInput(label="أدخل توكن البوت هنا", style=discord.TextStyle.paragraph, required=True)
    prefix = discord.ui.TextInput(label="أدخل برفكس البوت", placeholder="مثال: !", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        token_value, prefix_value = self.token.value, self.prefix.value
        user_id = str(interaction.user.id)

        # التحقق من أن التوكن غير مستخدم من قبل بوت آخر
        for bot_info in bots_data.values():
            if bot_info.get('token') == token_value and str(bot_info.get('owner_id')) != user_id:
                await interaction.response.send_message("❌ هذا التوكن مستخدم بالفعل من قبل بوت آخر. يرجى استخدام توكن جديد أو حذف البوت القديم أولاً.", ephemeral=True)
                return

        async def is_token_valid(token):
            test_client = discord.Client(intents=discord.Intents.default())
            try:
                await test_client.login(token)
                await test_client.close()
                return True
            except discord.LoginFailure:
                return False

        if not await is_token_valid(token_value):
            await interaction.response.send_message("❌ التوكن الذي أدخلته غير صالح أو منتهي.", ephemeral=True)
            return
        
        if user_id in bots_data:
            await stop_bot_instance_by_owner(user_id)
            bots_data[user_id]['token'] = token_value
            bots_data[user_id]['prefix'] = prefix_value
            bots_data[user_id]['status'] = 'pending_service'
            save_bots_data(bots_data)
            view = ServiceSelectionView()
            await interaction.response.send_message("✅ تم تحديث التوكن! الآن اختر الخدمة التي تريد تفعيلها لبوتك.", view=view, ephemeral=True)
        else:
            bots_data[user_id] = {
                'token': token_value,
                'prefix': prefix_value,
                'owner_id': interaction.user.id,
                'owner_name': interaction.user.name,
                'status': 'pending_service'
            }
            save_bots_data(bots_data)
            view = ServiceSelectionView()
            await interaction.response.send_message("✅ تم الحفظ! الآن اختر الخدمة التي تريد تفعيلها لبوتك.", view=view, ephemeral=True)

# --- نوافذ إعدادات الخدمات (تم تحديث SystemBotModal) ---
class SystemBotModal(discord.ui.Modal, title="إعداد بوت سيستم"):
    ban_role = discord.ui.TextInput(label="ID رتبة صلاحية أمر ban/unban")
    kick_role = discord.ui.TextInput(label="ID رتبة صلاحية أمر kick")
    timeout_role = discord.ui.TextInput(label="ID رتبة صلاحية أمر timeout/untimeout")
    nick_role = discord.ui.TextInput(label="ID رتبة صلاحية أمر nick")
    lock_role = discord.ui.TextInput(label="ID رتبة صلاحية أمر lock/unlock")

    async def on_submit(self, interaction: discord.Interaction):
        roles = [self.ban_role.value, self.kick_role.value, self.timeout_role.value, self.nick_role.value, self.lock_role.value]
        if not all(role.isdigit() for role in roles):
            await interaction.response.send_message("❌ يجب ملء جميع الحقول بأرقام ID الرتب الصحيحة.", ephemeral=True)
            return

        bot_info = bots_data.get(str(interaction.user.id))
        bot_info['service_config'] = {
            'ban': int(self.ban_role.value), 'unban': int(self.ban_role.value),
            'kick': int(self.kick_role.value),
            'timeout': int(self.timeout_role.value), 'untimeout': int(self.timeout_role.value),
            'nick': int(self.nick_role.value),
            'lock': int(self.lock_role.value), 'unlock': int(self.lock_role.value)
        }
        save_bots_data(bots_data)
        await interaction.response.send_message("⚙️ جاري إعداد وتفعيل بوت السيستم...", ephemeral=True)
        await start_bot_instance(interaction.user.id, bot_info)

class BroadcastModal(discord.ui.Modal, title="إعداد بوت برودكاست"):
    target_status = discord.ui.TextInput(
        label="أرسل لمن (offline/online/dnd/idle/all)", 
        placeholder="مثال: all", 
        required=True
    )
    message_content = discord.ui.TextInput(
        label="أدخل الرسالة التي تريد إرسالها", 
        style=discord.TextStyle.paragraph, 
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        status_map = {
            'offline': discord.Status.offline,
            'on': discord.Status.online,
            'online': discord.Status.online,
            'dnd': discord.Status.dnd,
            'idle': discord.Status.idle,
            'all': 'all'
        }
        
        target_status_value = self.target_status.value.lower()
        if target_status_value not in status_map:
            await interaction.response.send_message("❌ الحالة التي أدخلتها غير صحيحة. يرجى اختيار حالة من الخيارات المتاحة: (offline/online/dnd/idle/all)", ephemeral=True)
            return
        
        bot_info = bots_data.get(str(interaction.user.id))
        if not bot_info:
            await interaction.response.send_message("❌ حدث خطأ. بيانات البوت غير موجودة.", ephemeral=True)
            return

        bot_info['service_config'] = {
            'target_status': target_status_value,
            'message': self.message_content.value
        }
        bot_info['service'] = 'broadcast'
        save_bots_data(bots_data)

        await interaction.response.send_message("⚙️ جاري إعداد وتفعيل بوت البرودكاست...", ephemeral=True)
        await start_bot_instance(interaction.user.id, bot_info)

# --- أزرار لوحة التحكم ---
class ServiceSelectionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="بوت سيستم", style=discord.ButtonStyle.primary)
    async def system_bot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot_info = bots_data.get(str(interaction.user.id))
        bot_info['service'] = 'system'
        save_bots_data(bots_data)
        await interaction.response.send_modal(SystemBotModal())
    
    @discord.ui.button(label="بوت برودكاست", style=discord.ButtonStyle.secondary)
    async def broadcast_bot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot_info = bots_data.get(str(interaction.user.id))
        bot_info['service'] = 'broadcast'
        save_bots_data(bots_data)
        await interaction.response.send_modal(BroadcastModal())

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="تفعيل خدمة", style=discord.ButtonStyle.green, custom_id="activate_service_btn")
    async def activate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ActivationModal())

    @discord.ui.button(label="عرض الخدمات", style=discord.ButtonStyle.blurple, custom_id="view_services_btn")
    async def services_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        if user_id not in bots_data:
            await interaction.response.send_message("يجب عليك تفعيل خدمة أولاً عبر زر 'تفعيل خدمة'.", ephemeral=True)
            return
        
        bot_status = bots_data[user_id].get('status')
        if bot_status == 'online':
            await interaction.response.send_message("لديك بوت نشط بالفعل. يجب حذف البوت أولاً بواسطة المشرف.", ephemeral=True)
            return
        
        if bot_status == 'pending_service' or bot_status == 'offline':
            view = ServiceSelectionView()
            await interaction.response.send_message("اختر الخدمة التي تريدها لبوتك:", view=view, ephemeral=True)

# --- دوال إدارة البوتات ---
async def start_bot_instance(user_id: int, bot_config: Dict):
    user_id_str = str(user_id)
    if user_id_str in running_bots:
        return
    
    try:
        service_type = bot_config.get('service')
        if not service_type:
            return
        
        intents_sub = discord.Intents.all()
        client = commands.Bot(command_prefix=bot_config['prefix'], intents=intents_sub)
        client.service_config = bot_config.get('service_config', {})
        
        @client.event
        async def on_ready():
            if len(client.guilds) > 1:
                print(f"Bot {client.user} is in more than one server. Shutting down.")
                bots_data[user_id_str]['status'] = 'server_count_exceeded'
                save_bots_data(bots_data)
                await client.close()
                return
            print(f"--- Sub-bot {client.user} (Owner: {user_id_str}) is now online! ---")
            bot_info = bots_data.get(user_id_str, {})
            bot_info.update({'bot_id': client.user.id, 'bot_name': client.user.name, 'status': 'online'})
            save_bots_data(bots_data)

            if service_type == 'broadcast':
                await handle_broadcast(client)

        # --- دالة للتحقق من الصلاحيات ---
        def has_service_role(command_name):
            async def predicate(ctx):
                if not ctx.guild.me.guild_permissions.administrator:
                    await ctx.send("عذراً، لا يمكنني تنفيذ أي أمر دون صلاحية `Administrator`.")
                    return False
                role_id = ctx.bot.service_config.get(command_name)
                if not role_id:
                    return False
                return any(role.id == role_id for role in ctx.author.roles)
            return commands.check(predicate)

        # --- تعريف الأوامر حسب نوع الخدمة ---
        if service_type == 'system':
            # --- أوامر الإدارة ---
            @client.command()
            @has_service_role('ban')
            async def ban(ctx, member: discord.Member, *, reason: str = "No reason provided"):
                await member.ban(reason=reason)
                await ctx.send(f"✅ Banned {member.mention}.")
            @ban.error
            async def ban_error(ctx, error):
                if isinstance(error, commands.MissingRequiredArgument):
                    await ctx.send("❌ يرجى تحديد العضو. الاستخدام الصحيح: `{}ban <@عضو> [السبب]`".format(ctx.prefix))
                elif isinstance(error, commands.BadArgument):
                    await ctx.send("❌ لم يتم العثور على العضو.")
            
            @client.command()
            @has_service_role('unban')
            async def unban(ctx, *, user_id: int, reason: str = "No reason provided"):
                user = await client.fetch_user(user_id)
                await ctx.guild.unban(user, reason=reason)
                await ctx.send(f"✅ Unbanned {user.mention}.")
            @unban.error
            async def unban_error(ctx, error):
                if isinstance(error, commands.MissingRequiredArgument):
                    await ctx.send("❌ يرجى تحديد ID العضو. الاستخدام الصحيح: `{}unban <ID_العضو> [السبب]`".format(ctx.prefix))
                elif isinstance(error, commands.BadArgument):
                    await ctx.send("❌ يجب أن يكون ID العضو رقماً صحيحاً.")
            
            @client.command()
            @has_service_role('kick')
            async def kick(ctx, member: discord.Member, *, reason: str = "No reason provided"):
                await member.kick(reason=reason)
                await ctx.send(f"✅ Kicked {member.mention}.")
            @kick.error
            async def kick_error(ctx, error):
                if isinstance(error, commands.MissingRequiredArgument):
                    await ctx.send("❌ يرجى تحديد العضو. الاستخدام الصحيح: `{}kick <@عضو> [السبب]`".format(ctx.prefix))
                elif isinstance(error, commands.BadArgument):
                    await ctx.send("❌ لم يتم العثور على العضو.")
            @client.command()
            @has_service_role('timeout')
            async def timeout(ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
                unit_map = {"s": 1, "m": 60, "h": 3600, "d": 86400}
                try:
                    amount, unit = int(duration[:-1]), duration[-1].lower()
                except (ValueError, IndexError):
                    await ctx.send("❌ صيغة المدة غير صحيحة. الاستخدام الصحيح: `{}timeout <@عضو> <وقت> (مثال: 5m, 2h)`".format(ctx.prefix))
                    return
                if unit not in unit_map:
                    await ctx.send("❌ وحدة الوقت غير صحيحة. استخدم (s, m, h, d).")
                    return
                delta = datetime.timedelta(seconds=amount * unit_map[unit])
                await member.timeout(delta, reason=reason)
                await ctx.send(f"✅ Timed out {member.mention} for {amount}{unit}.")
            @timeout.error
            async def timeout_error(ctx, error):
                if isinstance(error, commands.MissingRequiredArgument):
                    await ctx.send("❌ يرجى تحديد العضو والمدة. الاستخدام الصحيح: `{}timeout <@عضو> <وقت> [السبب]`".format(ctx.prefix))
                elif isinstance(error, commands.BadArgument):
                    await ctx.send("❌ لم يتم العثور على العضو.")
            @client.command()
            @has_service_role('untimeout')
            async def untimeout(ctx, member: discord.Member, *, reason: str = "No reason provided"):
                await member.timeout(None, reason=reason)
                await ctx.send(f"✅ Removed timeout from {member.mention}.")
            @untimeout.error
            async def untimeout_error(ctx, error):
                if isinstance(error, commands.MissingRequiredArgument):
                    await ctx.send("❌ يرجى تحديد العضو. الاستخدام الصحيح: `{}untimeout <@عضو> [السبب]`".format(ctx.prefix))
                elif isinstance(error, commands.BadArgument):
                    await ctx.send("❌ لم يتم العثور على العضو.")
            
            @client.command()
            @has_service_role('nick')
            async def nick(ctx, member: discord.Member, *, new_nickname: str):
                await member.edit(nick=new_nickname)
                await ctx.send(f"✅ Changed nickname for {member.mention}.")
            @nick.error
            async def nick_error(ctx, error):
                if isinstance(error, commands.MissingRequiredArgument):
                    await ctx.send("❌ يرجى تحديد العضو واللقب الجديد. الاستخدام الصحيح: `{}nick <@عضو> <اللقب_الجديد>`".format(ctx.prefix))
                elif isinstance(error, commands.BadArgument):
                    await ctx.send("❌ لم يتم العثور على العضو.")
            @client.command()
            @has_service_role('lock')
            async def lock(ctx, channel: discord.TextChannel = None):
                channel = channel or ctx.channel
                await channel.set_permissions(ctx.guild.default_role, send_messages=False)
                await ctx.send(f"🔒 Locked {channel.mention}.")
            @lock.error
            async def lock_error(ctx, error):
                if isinstance(error, commands.BadArgument):
                    await ctx.send("❌ لم يتم العثور على القناة. الاستخدام الصحيح: `{}lock [قناة]`".format(ctx.prefix))
            
            @client.command()
            @has_service_role('unlock')
            async def unlock(ctx, channel: discord.TextChannel = None):
                channel = channel or ctx.channel
                await channel.set_permissions(ctx.guild.default_role, send_messages=True)
                await ctx.send(f"🔓 Unlocked {channel.mention}.")
            @unlock.error
            async def unlock_error(ctx, error):
                if isinstance(error, commands.BadArgument):
                    await ctx.send("❌ لم يتم العثور على القناة. الاستخدام الصحيح: `{}unlock [قناة]`".format(ctx.prefix))
            
        elif service_type == 'broadcast':
            async def handle_broadcast(bot_client):
                config = bot_client.service_config
                target_status_str = config.get('target_status')
                message = config.get('message')
                owner_id = bot_config.get('owner_id')
                owner = await bot.fetch_user(owner_id)

                if not owner:
                    print(f"Could not find owner for bot with ID {bot_client.user.id}.")
                    return

                sent_count = 0
                failed_count = 0
                
                status_map = {
                    'offline': discord.Status.offline,
                    'on': discord.Status.online,
                    'online': discord.Status.online,
                    'dnd': discord.Status.dnd,
                    'idle': discord.Status.idle,
                }
                
                target_status_obj = status_map.get(target_status_str)
                
                for guild in bot_client.guilds:
                    await owner.send(f"⏳ جاري إرسال البرودكاست في سيرفر `{guild.name}`...")
                    for member in guild.members:
                        if member.bot:
                            continue
                        
                        if target_status_str == 'all' or member.status == target_status_obj:
                            try:
                                await member.send(message)
                                sent_count += 1
                                # تأخير بسيط لتجنب حدود معدل الإرسال (Rate Limit)
                                await asyncio.sleep(1) 
                            except discord.Forbidden:
                                failed_count += 1
                            except Exception as e:
                                print(f"Failed to send DM to {member.name}: {e}")
                                failed_count += 1

                await owner.send(f"✅ انتهت عملية البرودكاست بنجاح!\nعدد الأشخاص الذين تم الإرسال لهم: {sent_count}\nعدد الأشخاص الذين فشل الإرسال لهم: {failed_count}")
                await bot_client.close()

        task = asyncio.create_task(client.start(bot_config['token']))
        running_bots[user_id_str] = {'client': client, 'task': task}
    except discord.LoginFailure:
        print(f"Login failed for bot of user {user_id_str}.")
        bots_data[user_id_str]['status'] = 'token_invalid'
        save_bots_data(bots_data)
    except Exception as e:
        print(f"Error starting bot for user {user_id_str}: {e}")
        bots_data[user_id_str]['status'] = 'error'
        save_bots_data(bots_data)

async def stop_bot_instance(bot_id: str) -> Optional[str]:
    target_user_id = next((uid for uid, data in bots_data.items() if str(data.get('bot_id')) == bot_id), None)
    if target_user_id and target_user_id in running_bots:
        instance = running_bots.pop(target_user_id)
        instance['task'].cancel()
        await instance['client'].close()
        bots_data[target_user_id]['status'] = 'offline'
        save_bots_data(bots_data)
        return target_user_id
    return None

async def stop_bot_instance_by_owner(owner_id: str) -> Optional[str]:
    if owner_id in running_bots:
        instance = running_bots.pop(owner_id)
        instance['task'].cancel()
        await instance['client'].close()
        bots_data[owner_id]['status'] = 'offline'
        save_bots_data(bots_data)
        return owner_id
    return None

async def restart_all_bots():
    print("Restarting all active bots from data file...")
    for user_id, config in bots_data.items():
        if config.get('status') == 'online':
            await start_bot_instance(int(user_id), config)

# --- أوامر البوت الرئيسي (Prefix Commands) ---
@bot.command(name="panel")
@commands.has_role(ADMIN_ROLE_ID)
async def panel(ctx: commands.Context):
    await ctx.message.delete()
    embed = discord.Embed(title="🤖 لوحة التحكم بالبوتات", description="استخدم الأزرار أدناه لتفعيل وإدارة خدمات بوتك الخاص.", color=discord.Color.dark_blue())
    embed.set_footer(text="Developed By: Alfajr Tools")
    await ctx.send(embed=embed, view=PanelView())

@panel.error
async def panel_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("❌ ليس لديك صلاحية استخدام هذا الأمر.", delete_after=10)

@bot.command(name="show")
@commands.has_role(ADMIN_ROLE_ID)
async def show(ctx: commands.Context):
    embed = discord.Embed(title="📊 قائمة البوتات النشطة", color=discord.Color.green())
    active_bots = [data for data in bots_data.values() if data.get('status') == 'online']
    if not active_bots:
        embed.description = "لا توجد بوتات نشطة حاليًا."
    else:
        description = ""
        for i, data in enumerate(active_bots, 1):
            owner = ctx.guild.get_member(data['owner_id'])
            description += f"**{i} - {data.get('bot_name', 'N/A')}**\n> **Owner:** {owner.mention if owner else data['owner_name']}\n> **Owner ID:** `{data['owner_id']}`\n> **Bot ID:** `{data.get('bot_id', 'N/A')}`\n> **Service:** `{data.get('service', 'N/A')}`\n--------------------\n"
        embed.description = description
    await ctx.send(embed=embed)

@bot.command(name="mg")
@commands.has_role(ADMIN_ROLE_ID)
async def mg(ctx: commands.Context, bot_id: str = None):
    if not bot_id:
        await ctx.send("الرجاء تحديد ID البوت. مثال: `+mg 123456789...`")
        return
    stopped_user_id = await stop_bot_instance(bot_id)
    if stopped_user_id:
        await ctx.send(f"✅ تم إيقاف البوت صاحب الـ ID: `{bot_id}`.")
    else:
        await ctx.send("❌ لم يتم العثور على بوت نشط بهذا الـ ID.")

@bot.command(name="re")
@commands.has_role(ADMIN_ROLE_ID)
async def re(ctx: commands.Context, bot_id: str = None):
    if not bot_id:
        await ctx.send("الرجاء تحديد ID البوت. مثال: `+re 123456789...`")
        return
    target_user_id = next((uid for uid, data in bots_data.items() if str(data.get('bot_id')) == bot_id), None)
    if not target_user_id:
        await ctx.send("❌ لا يوجد بوت بهذا الـ ID في قاعدة البيانات.")
        return
    if target_user_id in running_bots:
        await ctx.send("⚠️ هذا البوت يعمل بالفعل.")
        return
    await start_bot_instance(int(target_user_id), bots_data[target_user_id])
    await ctx.send(f"🔄 جاري إعادة تشغيل البوت `{bot_id}`.")

@bot.command(name="delete")
@commands.has_role(ADMIN_ROLE_ID)
async def delete(ctx: commands.Context, bot_id: str = None):
    if not bot_id:
        await ctx.send("الرجاء تحديد ID البوت. مثال: `+delete 123456789...`")
        return
    target_user_id = next((uid for uid, data in bots_data.items() if str(data.get('bot_id')) == bot_id), None)
    if not target_user_id:
        await ctx.send("❌ لا يوجد بوت بهذا الـ ID في قاعدة البيانات.")
        return
    await stop_bot_instance(bot_id)
    if target_user_id in bots_data:
        del bots_data[target_user_id]
        save_bots_data(bots_data)
        await ctx.send(f"🗑️ تم حذف البوت `{bot_id}` وكل بياناته نهائيًا.")
    else:
        await ctx.send("حدث خطأ ما أثناء محاولة الحذف.")

@bot.command(name="stats")
async def stats(ctx: commands.Context, bot_id: str = None):
    if not bot_id:
        await ctx.send("الرجاء تحديد ID البوت. مثال: `+stats 123456789...`")
        return
    bot_info = next((data for data in bots_data.values() if str(data.get('bot_id')) == bot_id), None)
    if not bot_info:
        await ctx.send("❌ لم يتم العثور على بوت بهذا الـ ID.")
        return
    owner = await bot.fetch_user(bot_info['owner_id'])
    embed = discord.Embed(title=f"بيانات البوت: {bot_info.get('bot_name', 'N/A')}", color=discord.Color.orange())
    embed.add_field(name="🆔 Bot ID", value=f"`{bot_info.get('bot_id', 'N/A')}`", inline=True)
    embed.add_field(name="👑 Owner ID", value=f"`{bot_info['owner_id']}`", inline=True)
    embed.add_field(name="👤 Owner", value=f"{owner.mention}", inline=False)
    embed.set_footer(text="Developed By: Al-fajr Tools")
    await ctx.send(embed=embed)

# --- تشغيل البوت الرئيسي ---
if __name__ == "__main__":
    if MAIN_BOT_TOKEN == "YOUR_MAIN_BOT_TOKEN" or ADMIN_ROLE_ID == 1234567890:
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n!!! الرجاء تعديل التوكن و ID رتبة الأدمن في ملف الكود !!!\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    else:
        bot.run(MAIN_BOT_TOKEN)