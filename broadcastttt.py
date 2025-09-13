import discord

from discord.ext import commands

# استخدام جميع النوايا (intents)

intents = discord.Intents.all()

bot = commands.Bot(command_prefix="!", intents=intents)

# معرف صاحب البوت

OWNER_ID = 1058036441462095916

@bot.event

async def on_ready():

    print(f"✅ تم تسجيل الدخول باسم {bot.user}")

@bot.command()

async def bc(ctx, status: str, *, message: str):

    """إرسال رسالة خاصة للأعضاء الذين لديهم حالة معينة"""

    

    # التأكد من أن المستخدم هو صاحب البوت

    if ctx.author.id != OWNER_ID:

        return await ctx.send("❌ ليس لديك الصلاحية لاستخدام هذا الأمر!")

    # التحقق من طول الرسالة

    if len(message) > 5000:

        return await ctx.send("❌ الرسالة تتجاوز الحد المسموح به (5000 كلمة)!")

    # الحالات المقبولة

    statuses = {

        "on": discord.Status.online,

        "off": discord.Status.offline,

        "idle": discord.Status.idle,

        "dnd": discord.Status.dnd

    }

    if status not in statuses:

        return await ctx.send("❌ الحالة غير صحيحة! استخدم: `on`, `off`, `idle`, `dnd`")

    await ctx.send("⏳ جاري الإرسال...")

    sent_count = 0

    failed_count = 0

    for member in ctx.guild.members:

        if not member.bot:  # تجاهل البوتات

            try:

                if member.status == statuses[status]:  # التحقق من الحالة المطلوبة

                    dm_channel = member.dm_channel or await member.create_dm()

                    await dm_channel.send(message)

                    sent_count += 1

            except:

                failed_count += 1

    await ctx.send(f"✅ تم الإرسال إلى {sent_count} شخصًا، وفشل الإرسال إلى {failed_count}.")

bot.run("MTQwNjcxNDE1MDk5Mzc4ODk2OA.GS-r-y.9_8T8agFxXYvXQb58lXpEm0pbo5vwHFeLwwHic") 