import asyncio
import websockets
import json
import requests
import re
import threading
import time
import socket
import struct
from itertools import cycle
from datetime import datetime
from io import BytesIO

USER_TOKEN = "MTQxMTMxNDI3OTcyNTkyODUxMA.G97AkD.ai1NlQj1vjWEMo1WljqAHxeKKzOipV8D2vfwaw"
ALLOWED_USER_ID = "1411314279725928510"
GATEWAY_URL = "wss://gateway.discord.gg/?v=9&encoding=json"
INTENTS = (1 << 9)|(1 << 15)|(1 << 12)|(1 << 14)|(1 << 17)|(1 << 18)|(1 << 1)|(1 << 0)|(1 << 7)

RECONNECT_DELAY = 16
PFX = ".."

# Voice connection variables
voice_session_id = None
voice_token = None
voice_endpoint = None
voice_guild_id = None
voice_channel_id = None
voice_udp_sock = None
voice_ssrc = None
voice_endpoint_ip = None
voice_endpoint_port = None
voice_heartbeat_task = None
voice_udp_keepalive_thread = None
voice_ws = None
ng_tasks = {}
kep_task = None
status_task = None

# New variables for auto-reply and logging
auto_reply = {"enabled": False, "text": ""}
dm_logging_enabled = False # DM logging enabled by default

TOKENS_FILE = "dkep.json"
try:
    with open(TOKENS_FILE, encoding="utf8") as f:
        kep_messages = json.load(f)
        if not isinstance(kep_messages, list):
            kep_messages = list(kep_messages)
except:
    kep_messages = []

def get_headers():
    return {
        "Authorization": USER_TOKEN,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json"
    }

def console(msg, c='\033[92m'):
    print(f"{c}{msg}\033[0m")

async def heartbeat(ws, interval):
    while True:
        await asyncio.sleep(interval/1000)
        try:
            await ws.send(json.dumps({"op": 1, "d": None}))
        except:
            break

async def keep_alive(ws):
    while True:
        await asyncio.sleep(60)
        try:
            await ws.ping()
        except:
            break

def voice_udp_keepalive():
    while True:
        try:
            if voice_udp_sock:
                voice_udp_sock.sendto(b'\xf8\xff\xfe' + bytes(57), (voice_endpoint_ip, voice_endpoint_port))
        except Exception as e:
            console(f"⚠ UDP Keepalive error: {e}", '\033[91m')
        time.sleep(5)

async def voice_heartbeat(ws, interval):
    while True:
        try:
            await ws.send(json.dumps({"op": 3, "d": int(time.time() * 1000)}))
            await asyncio.sleep(interval)
        except Exception as e:
            console(f"⚠ Voice heartbeat error: {e}", '\033[91m')
            break

async def connect_voice():
    global voice_ws, voice_udp_sock, voice_ssrc, voice_endpoint_ip, voice_endpoint_port, voice_heartbeat_task, voice_udp_keepalive_thread

    if not voice_token or not voice_endpoint:
        console("❌ No voice token or endpoint", '\033[91m')
        return

    uri = f"wss://{voice_endpoint}?v=4"
    try:
        voice_ws = await websockets.connect(uri)
        await voice_ws.send(json.dumps({
            "op": 0,
            "d": {
                "server_id": voice_guild_id,
                "user_id": ALLOWED_USER_ID,
                "session_id": voice_session_id,
                "token": voice_token
            }
        }))

        console("🔊 Voice WS connected", '\033[96m')

        while True:
            message = await voice_ws.recv()
            data = json.loads(message)

            if data["op"] == 2:
                voice_ssrc = data["d"]["ssrc"]
                ip = data["d"]["ip"]
                port = data["d"]["port"]

                voice_udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                voice_udp_sock.setblocking(False)

                packet = bytearray(70)
                struct.pack_into(">I", packet, 0, voice_ssrc)
                voice_udp_sock.sendto(packet, (ip, port))

                voice_udp_keepalive_thread = threading.Thread(target=voice_udp_keepalive, daemon=True)
                voice_udp_keepalive_thread.start()

                hb_interval = data["d"]["heartbeat_interval"] / 1000
                voice_heartbeat_task = asyncio.create_task(voice_heartbeat(voice_ws, hb_interval))

                console("✅ Voice connection established", '\033[92m')

            elif data["op"] == 4:
                pass

    except Exception as e:
        console(f"❌ Voice connection error: {e}", '\033[91m')
        await asyncio.sleep(10)
        await connect_voice()

async def disconnect_voice():
    global voice_ws, voice_udp_sock, voice_heartbeat_task, voice_udp_keepalive_thread

    if voice_heartbeat_task:
        voice_heartbeat_task.cancel()
        voice_heartbeat_task = None

    if voice_udp_keepalive_thread:
        voice_udp_keepalive_thread.join(0.1)
        voice_udp_keepalive_thread = None

    if voice_udp_sock:
        voice_udp_sock.close()
        voice_udp_sock = None

    if voice_ws:
        await voice_ws.close()
        voice_ws = None

    console("🔇 Disconnected from voice", '\033[93m')

def find_voice_channel(guild_id, name):
    try:
        headers = get_headers()
        channels = requests.get(
            f"https://discord.com/api/v9/guilds/{guild_id}/channels",
            headers=headers
        ).json()

        for channel in channels:
            if channel["type"] == 2 and channel["name"].lower() == name.lower():
                return channel["id"]
    except Exception as e:
        console(f"⚠ Error finding voice channel: {e}", '\033[91m')
    return None

async def connect_gateway():
    global kep_task, status_task, voice_session_id

    while True:
        try:
            async with websockets.connect(GATEWAY_URL, max_size=16 * 1024 * 1024) as ws:
                console("🔌 Connected", '\033[96m')
                hello = json.loads(await ws.recv())
                asyncio.create_task(heartbeat(ws, hello["d"]["heartbeat_interval"]))
                asyncio.create_task(keep_alive(ws))

                await ws.send(json.dumps({
                    "op": 2,
                    "d": {
                        "token": USER_TOKEN,
                        "capabilities": 4093,
                        "properties": {
                            "$os": "windows",
                            "$browser": "chrome",
                            "$device": "pc"
                        },
                        "presence": {
                            "status": "dnd",
                            "since": 0,
                            "activities": [{
                                "type": 4,
                                "state": "Conan! - Version 2.1",
                                "emoji": {"name": "🥀"}
                            }],
                            "afk": False
                        },
                        "client_state": {
                            "guild_versions": {},
                            "highest_last_message_id": "0",
                            "read_state_version": 0,
                            "user_guild_settings_version": -1,
                            "user_settings_version": -1
                        }
                    }
                }))

                while True:
                    data = json.loads(await ws.recv())
                    if data.get("t") == "READY":
                        u = data["d"]["user"]
                        console(f"✅ Logged in as {u['username']}#{u['discriminator']}", '\033[96m')
                        break

                console(f"🎧 Listening for commands with prefix '{PFX}' V3", '\033[93m')

                while True:
                    evt = json.loads(await ws.recv())
                    t = evt.get("t")
                    m = evt.get("d")

                    if not isinstance(m, dict):
                        continue

                    if t == "VOICE_STATE_UPDATE" and m.get("user_id") == ALLOWED_USER_ID:
                        voice_session_id = m.get("session_id")
                        voice_channel_id = m.get("channel_id")
                        if not voice_channel_id:
                            await disconnect_voice()

                    elif t == "VOICE_SERVER_UPDATE" and m.get("guild_id") == voice_guild_id:
                        global voice_token, voice_endpoint
                        voice_token = m.get("token")
                        voice_endpoint = m.get("endpoint")
                        asyncio.create_task(connect_voice())

                    elif t == "MESSAGE_CREATE":
                        author_id = m.get("author", {}).get("id")
                        text = m.get("content", "").strip()
                        ch = m.get("channel_id")

                        # Auto-reply for DMs (if enabled)
                        if (auto_reply["enabled"] and
                            m.get("guild_id") is None and # DM only
                            author_id != ALLOWED_USER_ID): # Not from self
                            await _send(ch, auto_reply["text"])

                        if author_id == ALLOWED_USER_ID:
                            if not text.startswith(PFX):
                                continue

                            cmd = text[len(PFX):]
                            await _delete(ch, m["id"])

                            if cmd.startswith("clear"):
                                await _clear(ch, cmd)
                            elif cmd.startswith("spam"):
                                await _spam(ch, cmd)
                            elif cmd == "help":
                                await _help(ch)
                            elif cmd.startswith("avatar"):
                                await _avatar(ch, cmd)
                            elif cmd.startswith("ng"):
                                await _ng(ch, cmd)
                            elif cmd.startswith("raid") and "guild_id" in m:
                                await _clearserver(m["guild_id"], ch)
                            elif cmd.startswith("k"):
                                await _kep(ch, cmd)
                            elif cmd.startswith("status"):
                                await _status(ws, ch, cmd)
                            elif cmd.startswith("j"):
                                await _join(ws, ch, cmd)
                            elif cmd == "l":
                                await _leave(ws, ch)
                            elif cmd.startswith("auto-r"):
                                await _auto_reply(ch, cmd)
                            elif cmd.startswith("log"):
                                await _log_setting(ch, cmd)

                    # DM logging for deleted/edited messages
                    elif dm_logging_enabled and t in ("MESSAGE_DELETE", "MESSAGE_UPDATE"):
                        ch = m.get("channel_id")
                        # Only process DMs (no guild_id) and ensure we have channel and author info
                        if not ch or m.get("guild_id") or not m.get("author"):
                            continue

                        ts = datetime.now().strftime("%H:%M:%S")
                        user = m["author"].get("username", "?")

                        if t == "MESSAGE_DELETE":
                            old = m.get("content", "[no content]")
                            msg = f"[{ts}] 🗑 Deleted in DM by {user}: {old}"
                        else:
                            old = m.get("old_content", "[no content]")
                            new = m.get("content", "[no content]")
                            msg = f"[{ts}] ✏ Edited in DM by {user}:\n   Before: {old}\n   After: {new}"

                        console(f"📩 Log: {msg}", '\033[90m')
                        await _send(ch, msg)

        except Exception as e:
            console(f"⚠ Connection error: {e}", '\033[91m')
            await asyncio.sleep(RECONNECT_DELAY)

async def _delete(ch, mid):
    try:
        headers = get_headers()
        requests.delete(
            f"https://discord.com/api/v9/channels/{ch}/messages/{mid}",
            headers=headers
        )
    except Exception as e:
        console(f"⚠ Error deleting message: {e}", '\033[91m')

async def _send(ch, content):
    try:
        headers = get_headers()
        requests.post(
            f"https://discord.com/api/v9/channels/{ch}/messages",
            headers=headers,
            json={"content": content}
        )
    except Exception as e:
        console(f"⚠ Error sending message: {e}", '\033[91m')

async def _clear(ch, cmd):
    try:
        parts = cmd.split()
        limit = 50
        if len(parts) > 1 and parts[1].isdigit():
            limit = int(parts[1])

        headers = get_headers()
        msgs = requests.get(
            f"https://discord.com/api/v9/channels/{ch}/messages?limit={limit}",
            headers=headers
        ).json()

        for m in msgs:
            if m.get("author", {}).get("id") == ALLOWED_USER_ID:
                requests.delete(
                    f"https://discord.com/api/v9/channels/{ch}/messages/{m['id']}",
                    headers=headers
                )
                await asyncio.sleep(0.1)
    except Exception as e:
        console(f"⚠ Error clearing messages: {e}", '\033[91m')

async def _spam(ch, cmd):
    parts = cmd.split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        return

    count = int(parts[1])
    text = parts[2]

    headers = get_headers()
    for _ in range(count):
        requests.post(
            f"https://discord.com/api/v9/channels/{ch}/messages",
            headers=headers,
            json={"content": text}
        )
        await asyncio.sleep(0.2)

async def _help(ch):
    cmds = [
        "+clear <amount> - Delete your messages (default: 50)",
        "+spam <amount> <msg> - Spam Messages",
        "+avatar <@mention> - Get user's avatar",
        "+ng on <words>/off - Rotate channel name",
        "+status (1/2/3/inv/666) (text) - Change status",
        "+raid - Nuke The Server",
        "+join <voice_name> - Join voice channel",
        "+leave - Leave voice channel",
        "+auto-r on <text>/off - Auto-reply in DMs",
        "+log on/off - Enable/disable DM logging"
    ]
    await _send(ch, "**Commands V3.8:**\n" + "\n".join(cmds))

async def _avatar(ch, cmd):
    m = re.search(r"<@!?(\d+)>", cmd)
    if not m:
        return

    uid = m.group(1)
    try:
        headers = get_headers()
        user_data = requests.get(
            f"https://discord.com/api/v9/users/{uid}",
            headers=headers
        ).json()

        img = requests.get(
            f"https://cdn.discordapp.com/avatars/{uid}/{user_data.get('avatar')}.png"
        ).content

        requests.post(
            f"https://discord.com/api/v9/channels/{ch}/messages",
            headers=headers,
            files={"file": ("avatar.png", BytesIO(img))}
        )
    except Exception as e:
        console(f"⚠ Error getting avatar: {e}", '\033[91m')

async def _ng(ch, cmd):
    parts = cmd.split()
    if len(parts) > 1 and parts[1].lower().startswith("off"):
        task = ng_tasks.pop(ch, None)
        if task:
            task.cancel()
            console(f"🛑 ng stopped in channel {ch}", '\033[93m')
        await _send(ch, ".")
        return

    if len(parts) < 3:
        await _send(ch, "⚠ usage: ..ng on <word1 word2 ...>")
        return

    words = " ".join(parts[2:]).split()

    async def rotator():
        headers = get_headers()
        for w in cycle(words):
            requests.patch(
                f"https://discord.com/api/v9/channels/{ch}",
                headers=headers,
                json={"name": w}
            )
            await asyncio.sleep(0.4)

    ng_tasks[ch] = asyncio.create_task(rotator())
    console(f"🔁 ng started with {words}", '\033[93m')
    await _send(ch, f" ")

async def _kep(ch, cmd):
    global kep_task
    parts = cmd.split(maxsplit=2)

    if len(parts) < 2:
        await _send(ch, "⚠ usage: ..k on [mentions]/off")
        return

    action = parts[1].lower()

    if action == "off":
        if kep_task:
            kep_task.cancel()
            kep_task = None
            console("🛑 kep stopped", '\033[93m')
        await _send(ch, ".")
        return

    if action == "on":
        mentions = re.findall(r"<@!?(\d+)>", cmd)

        async def sender():
            import random
            headers = get_headers()
            while True:
                # First, send all messages from the list
                for msg in kep_messages:
                    if mentions:
                        mention_str = " ".join(f"<@{uid}>" for uid in mentions)
                        requests.post(
                            f"https://discord.com/api/v9/channels/{ch}/messages",
                            headers=headers,
                            json={"content": f"{msg} {mention_str}"}
                        )
                    else:
                        requests.post(
                            f"https://discord.com/api/v9/channels/{ch}/messages",
                            headers=headers,
                            json={"content": f"{msg}"}
                        )
                    await asyncio.sleep(0.2)
                
                # Then, shuffle and send again
                shuffled = kep_messages[:]
                random.shuffle(shuffled)
                for msg in shuffled:
                    if mentions:
                        mention_str = " ".join(f"<@{uid}>" for uid in mentions)
                        requests.post(
                            f"https://discord.com/api/v9/channels/{ch}/messages",
                            headers=headers,
                            json={"content": f"{msg} {mention_str}"}
                        )
                    else:
                        requests.post(
                            f"https://discord.com/api/v9/channels/{ch}/messages",
                            headers=headers,
                            json={"content": f"{msg}"}
                        )
                    await asyncio.sleep(0.2)


        kep_task = asyncio.create_task(sender())
        console(f"🔁 kep started", '\033[93m')
        await _send(ch, f" ")
        return

    await _send(ch, "⚠ usage: ..k on [mentions]/off")

async def send_presence(ws, type_, text):
    payload = {"op": 3, "d": {"status": "online", "since": 0, "activities": [], "afk": False}}
    if type_ is not None:
        payload["d"]["activities"].append({"type": type_, "name": text or ""})
    await ws.send(json.dumps(payload))

async def _status(ws, ch, cmd):
    global status_task
    parts = cmd.split(maxsplit=2)

    if len(parts) < 2:
        return await _send(ch, "⚠ usage: ..status (1/2/3/inv/666) (text)")

    opt = parts[1]
    text = parts[2] if len(parts) >= 3 else ""

    if status_task:
        status_task.cancel()
        status_task = None

    if opt == "1":
        await send_presence(ws, 0, text)
        await _send(ch, "✅ Status set to **Playing**.")
    elif opt == "2":
        await send_presence(ws, 2, text)
        await _send(ch, "✅ Status set to **Listening**.")
    elif opt == "3":
        await send_presence(ws, 3, text)
        await _send(ch, "✅ Status set to **Watching**.")
    elif opt.lower() == "inv":
        await send_presence(ws, None, None)
        await _send(ch, "✅ Status set to **Invisible**.")
    elif opt == "666":
        words = text.split()
        idx = 0
        from itertools import cycle
        types = cycle([0, 2, 3])

        async def cycler():
            nonlocal idx
            while True:
                t = next(types)
                msg = " ".join(words[idx:] + words[:idx]) if words else ""
                idx = (idx + 1) % len(words) if words else 0
                await send_presence(ws, t, msg)
                await asyncio.sleep(60)

        status_task = asyncio.create_task(cycler())
        await _send(ch, "✅ Cycling status every Min.")
    else:
        await _send(ch, "**⚠ Invalid status type.**\n`1` = Playing\n`2` = Listening\n`3` = Watching\n`inv` = No status\n`666` = Rotate all every Min")

async def _clearserver(guild_id, ch):
    headers = get_headers()
    await _send(ch, "⚙ Nuking...")

    try:
        channels = requests.get(
            f"https://discord.com/api/v9/guilds/{guild_id}/channels",
            headers=headers
        ).json()

        for channel in channels:
            try:
                requests.delete(
                    f"https://discord.com/api/v9/channels/{channel['id']}",
                    headers=headers
                )
                await asyncio.sleep(0.2)
            except Exception as e:
                console(f"⚠ Error deleting channel {channel['id']}: {e}", '\033[91m')

        roles = requests.get(
            f"https://discord.com/api/v9/guilds/{guild_id}/roles",
            headers=headers
        ).json()

        for role in roles:
            if role["name"] != "@everyone":
                try:
                    requests.delete(
                        f"https://discord.com/api/v9/guilds/{guild_id}/roles/{role['id']}",
                        headers=headers
                    )
                    await asyncio.sleep(0.2)
                except Exception as e:
                    console(f"⚠ Error deleting role {role['id']}: {e}", '\033[91m')

        requests.patch(
            f"https://discord.com/api/v9/guilds/{guild_id}",
            headers=headers,
            json={"name": "By Al-Fajr Tool", "icon": None}
        )

        created_channels = []
        for _ in range(10):
            try:
                response = requests.post(
                    f"https://discord.com/api/v9/guilds/{guild_id}/channels",
                    headers=headers,
                    json={"name": "Al-Fajr Tool Is Here", "type": 0}
                )
                if response.status_code == 201:
                    created_channels.append(response.json()["id"])
                await asyncio.sleep(0.2)
            except Exception as e:
                console(f"⚠ Error creating channel: {e}", '\033[91m')

        for channel_id in created_channels:
            try:
                requests.post(
                    f"https://discord.com/api/v9/channels/{channel_id}/messages",
                    headers=headers,
                    json={"content": "# Nuked By Al-Fajr Tool @everyone @here"}
                )
                await asyncio.sleep(0.2)
            except Exception as e:
                console(f"⚠ Error sending message: {e}", '\033[91m')

        for i in range(10):
            try:
                requests.post(
                    f"https://discord.com/api/v9/guilds/{guild_id}/roles",
                    headers=headers,
                    json={"name": "Ha2cked-By-Al-Fajr-Tool"}
                )
                await asyncio.sleep(0.2)
            except Exception as e:
                console(f"⚠ Error creating role: {e}", '\033[91m')

        await _send(ch, "Server Ha2cked By Al-Fajr Tool!")

    except Exception as e:
        console(f"⚠ Error in server cleanup: {e}", '\033[91m')
        await _send(ch, "?")

async def _join(ws, ch, cmd):
    global voice_guild_id

    parts = cmd.split(maxsplit=1)
    if len(parts) < 2:
        await _send(ch, "⚠ usage: ..join <voice_channel_name>")
        return

    channel_name = parts[1].strip()

    try:
        headers = get_headers()
        channel_info = requests.get(
            f"https://discord.com/api/v9/channels/{ch}",
            headers=headers
        ).json()

        if "guild_id" not in channel_info:
            await _send(ch, "❌ This command only works in server channels")
            return

        voice_guild_id = channel_info["guild_id"]
        voice_channel_id = find_voice_channel(voice_guild_id, channel_name)

        if not voice_channel_id:
            await _send(ch, f"❌ Voice channel '{channel_name}' not found")
            return

        await ws.send(json.dumps({
            "op": 4,
            "d": {
                "guild_id": voice_guild_id,
                "channel_id": voice_channel_id,
                "self_mute": False,
                "self_deaf": True
            }
        }))

        await _send(ch, f"🎤 Joining voice channel: {channel_name}")
        console(f"🔊 Joining voice channel: {channel_name}", '\033[96m')

    except Exception as e:
        console(f"⚠ Error joining voice: {e}", '\033[91m')
        await _send(ch, f"❌ Error joining voice: {e}")

async def _leave(ws, ch):
    if not voice_guild_id:
        await _send(ch, "❌ Not in any voice channel")
        return

    await ws.send(json.dumps({
        "op": 4,
        "d": {
            "guild_id": voice_guild_id,
            "channel_id": None,
            "self_mute": False,
            "self_deaf": False
        }
    }))

    await disconnect_voice()
    await _send(ch, "🔇 Left voice channel")
    console("🔇 Left voice channel", '\033[93m')

async def _auto_reply(ch, cmd):
    global auto_reply
    parts = cmd.split(maxsplit=2)

    if len(parts) < 2:
        await _send(ch, "⚠ usage: ..auto-r on <text> or ..auto-r off")
        return

    action = parts[1].lower()

    if action == "on":
        if len(parts) < 3:
            await _send(ch, "⚠ usage: ..auto-r on <text>")
            return

        auto_reply["enabled"] = True
        auto_reply["text"] = parts[2]
        await _send(ch, f"✅ Auto-reply enabled: {auto_reply['text']}")
        console(f"✅ Auto-reply enabled: {auto_reply['text']}", '\033[92m')

    elif action == "off":
        auto_reply["enabled"] = False
        await _send(ch, "✅ Auto-reply disabled")
        console("✅ Auto-reply disabled", '\033[92m')

    else:
        await _send(ch, "!")

async def _log_setting(ch, cmd):
    global dm_logging_enabled
    parts = cmd.split()

    if len(parts) < 2:
        await _send(ch, "⚠ usage: ..log on or ..log off")
        return

    action = parts[1].lower()

    if action == "on":
        dm_logging_enabled = True
        await _send(ch, "✅ DM logging enabled")
        console("✅ DM logging enabled", '\033[92m')

    elif action == "off":
        dm_logging_enabled = False
        await _send(ch, "✅ DM logging disabled")
        console("✅ DM logging disabled", '\033[92m')

    else:
        await _send(ch, "⚠ usage: ..log on or ..log off")

asyncio.run(connect_gateway())