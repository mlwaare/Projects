import httpx, threading, time, json, asyncio, socket, struct

import websockets

TOKEN = "MTM5Njg2OTQ3OTQyMTQ0NDEwNw.GzSaji.yLuMqPqvfOLizeUXswic4yJ1100ayPecpOY7H4"

API_BASE = "https://discord.com/api/v9"

HEADERS = {"Authorization": TOKEN, "Content-Type": "application/json"}

# متغيرات عالمية

user_id = None

session_id = None

voice_token = None

voice_endpoint = None

guild_id = None

channel_id = None

udp_sock = None

ssrc = None

endpoint_ip, endpoint_port = None, None

def log(msg):

    if channel_id:

        try:

            httpx.post(f"{API_BASE}/channels/{channel_id}/messages", headers=HEADERS, json={"content": f"`{msg}`"})

        except Exception as e:

            print("خطأ أثناء الإرسال للقناة:", e)

def init_self():

    global user_id

    try:

        res = httpx.get(f"{API_BASE}/users/@me", headers=HEADERS)

        res.raise_for_status()

        user_id = res.json()["id"]

        print(f"✅ Logged in as: {user_id}")

    except Exception as e:

        print("❌ Error fetching user info:", e)

        exit()

def find_voice(name):

    global guild_id

    try:

        guilds = httpx.get(f"{API_BASE}/users/@me/guilds", headers=HEADERS).json()

        for g in guilds:

            chs = httpx.get(f"{API_BASE}/guilds/{g['id']}/channels", headers=HEADERS).json()

            for ch in chs:

                if ch["type"] == 2 and ch["name"].lower() == name.lower():

                    guild_id = g["id"]

                    return ch["id"]

    except Exception as e:

        log(f"خطأ أثناء جلب الرومات: {e}")

    return None

async def voice_connect():

    global udp_sock, ssrc, endpoint_ip, endpoint_port

    uri = f"wss://{voice_endpoint}?v=4"

    try:

        async with websockets.connect(uri) as ws:

            await ws.send(json.dumps({

                "op": 0,

                "d": {

                    "server_id": guild_id,

                    "user_id": user_id,

                    "session_id": session_id,

                    "token": voice_token

                }

            }))

            log("🔊 Voice WS started")

            while True:

                m = json.loads(await ws.recv())

                if m["op"] == 2:

                    ssrc = m["d"]["ssrc"]

                    ip_d = m["d"]["ip"]

                    port_d = m["d"]["port"]

                    hb = m["d"]["heartbeat_interval"]

                    asyncio.create_task(voice_hb(ws, hb / 1000))

                    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

                    udp_sock.settimeout(5)

                    pkt = bytearray(70)

                    struct.pack_into(">I", pkt, 0, ssrc)

                    udp_sock.sendto(pkt, (ip_d, port_d))

                    data, _ = udp_sock.recvfrom(70)

                    ip_e = data[4:data.find(b'\x00', 4)].decode()

                    port_e = struct.unpack_from(">H", data, len(data) - 2)[0]

                    endpoint_ip, endpoint_port = ip_e, port_e

                    await ws.send(json.dumps({

                        "op": 1,

                        "d": {

                            "protocol": "udp",

                            "data": {

                                "address": ip_e,

                                "port": port_e,

                                "mode": "xsalsa20_poly1305"

                            }

                        }

                    }))

                    threading.Thread(target=udp_keepalive, daemon=True).start()

                    log("✅ Connected to voice")

                elif m["op"] in (4, 6):

                    continue

    except Exception as e:

        log(f"❌ Voice Connect Error: {e}")

async def voice_hb(ws, interval):

    while True:

        await asyncio.sleep(interval)

        try:

            await ws.send(json.dumps({"op": 3, "d": int(time.time() * 1000)}))

        except:

            break

def udp_keepalive():

    while True:

        try:

            udp_sock.sendto(b'\xf8\xff\xfe' + bytes(57), (endpoint_ip, endpoint_port))

        except:

            pass

        time.sleep(5)

async def gateway_loop():

    global session_id, voice_token, voice_endpoint, channel_id

    try:

        async with websockets.connect("wss://gateway.discord.gg/?v=9&encoding=json") as ws:

            hi = json.loads(await ws.recv())

            hb_i = hi["d"]["heartbeat_interval"] / 1000

            asyncio.create_task(gateway_hb(ws, hb_i))

            await ws.send(json.dumps({

                "op": 2,

                "d": {

                    "token": TOKEN,

                    "intents": 513,

                    "properties": {

                        "$os": "linux",

                        "$browser": "chrome",

                        "$device": "pc"

                    }

                }

            }))

            while True:

                m = json.loads(await ws.recv())

                t = m.get("t")

                if t == "MESSAGE_CREATE":

                    d = m["d"]

                    author = d["author"]["id"]

                    if author != user_id:

                        continue

                    txt = d["content"].strip()

                    channel_id = d["channel_id"]

                    if txt.startswith("+join "):

                        name = txt[6:].strip()

                        ch = find_voice(name)

                        if ch:

                            await ws.send(json.dumps({

                                "op": 4,

                                "d": {

                                    "guild_id": guild_id,

                                    "channel_id": ch,

                                    "self_mute": False,

                                    "self_deaf": True

                                }

                            }))

                            log(f"🎤 Joining `{name}`")

                    elif txt == "+help":

                        httpx.post(f"{API_BASE}/channels/{channel_id}/messages", headers=HEADERS, json={

                            "content": "`+join <اسم الروم>` — join\n`+help` — help"

                        })

                elif t == "VOICE_STATE_UPDATE" and m["d"]["user_id"] == user_id:

                    session_id = m["d"]["session_id"]

                elif t == "VOICE_SERVER_UPDATE":

                    voice_token = m["d"]["token"]

                    voice_endpoint = m["d"]["endpoint"]

                    asyncio.create_task(voice_connect())

    except Exception as e:

        log(f"❌ Gateway Error: {e}")

async def gateway_hb(ws, interval):

    while True:

        await asyncio.sleep(interval)

        try:

            await ws.send(json.dumps({"op": 1, "d": None}))

        except:

            break

if __name__ == "__main__":

    init_self()

    asyncio.run(gateway_loop())

