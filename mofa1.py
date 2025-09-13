import asyncio

import json

import re

import requests

import websockets

import time

import random

import os

USER_TOKEN = "MTM5OTkwMjMyNDI3Njg1ODk0MQ.GlUnbd.LLUdA5V9W89IHcARXYz-WvDBPpIKyqEXQuIWG4"

AUTHORIZED_IDS = {"1396869479421444107", "1187703379716231241", "452191806541529091"}

GATEWAY_URL = "wss://gateway.discord.gg/?v=9&encoding=json"

PFX = "+"

kep_task = None

kep_messages = []

# Load kep messages from file

TOKENS_FILE = "dkep.json"

if os.path.exists(TOKENS_FILE):

    try:

        with open(TOKENS_FILE, encoding="utf-8") as f:

            data = json.load(f)

            if isinstance(data, list):

                kep_messages = data

            else:

                print("⚠ dkep.json is not a list. Ignoring.")

    except Exception as e:

        print(f"⚠ Error reading dkep.json: {e}")

else:

    print("⚠ dkep.json not found. Using empty list.")

def get_headers():

    return {

        "Authorization": USER_TOKEN,

        "User-Agent": "Mozilla/5.0",

        "Content-Type": "application/json"

    }

async def heartbeat(ws, interval):

    while True:

        await asyncio.sleep(interval / 1000)

        try:

            await ws.send(json.dumps({"op": 1, "d": None}))

        except:

            break

async def _send(ch, content):

    try:

        requests.post(

            f"https://discord.com/api/v9/channels/{ch}/messages",

            headers=get_headers(),

            json={"content": content}

        )

    except Exception as e:

        print(f"Send error: {e}")

async def _kep(ch, cmd, author_id):

    global kep_task

    

    if author_id not in AUTHORIZED_IDS:

        return  # تجاهل أي شخص غير مصرح له

    if not kep_messages:

        await _send(ch, "No kep")

        return

    parts = cmd.split(maxsplit=2)

    if len(parts) < 2:

        await _send(ch, "invalid")

        return

    action = parts[1].lower()

    # إيقاف البوت بأي حال

    if action == "off":

        if kep_task:

            kep_task.cancel()

            kep_task = None

        await _send(ch, ".")

        return

    # تشغيل البوت

    if action == "on":

        if len(parts) < 3:

            await _send(ch, "!")

            return

        

        # إلغاء أي مهمة سابقة إذا كانت تعمل

        if kep_task:

            kep_task.cancel()

        

        # استخراج جميع الـ IDs المذكورة

        user_ids = re.findall(r"<@!?(\d+)>", parts[2])

        if not user_ids:

            await _send(ch, "!!")

            return

        async def sender():

            try:

                while True:

                    msgs = kep_messages + random.sample(kep_messages, len(kep_messages))

                    for msg in msgs:

                        # إنشاء المنشنات لكل المستخدمين

                        mentions = ' '.join([f'<@{uid}>' for uid in user_ids])

                        requests.post(

                            f"https://discord.com/api/v9/channels/{ch}/messages",

                            headers=get_headers(),

                            json={"content": f"{msg} {mentions}"}

                        )

                        await asyncio.sleep(0.2)

            except asyncio.CancelledError:

                pass  # تم إلغاء المهمة بشكل طبيعي

        kep_task = asyncio.create_task(sender())

        await _send(ch, " ")

        return

async def connect_gateway():

    while True:

        try:

            async with websockets.connect(GATEWAY_URL) as ws:

                hello = json.loads(await ws.recv())

                asyncio.create_task(heartbeat(ws, hello["d"]["heartbeat_interval"]))

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

                            "status": "online",

                            "since": 0,

                            "activities": [],

                            "afk": False

                        }

                    }

                }))

                while True:

                    event = json.loads(await ws.recv())

                    if event.get("t") == "MESSAGE_CREATE":

                        data = event.get("d", {})

                        author_id = data.get("author", {}).get("id")

                        if author_id not in AUTHORIZED_IDS:

                            continue

                        content = data.get("content", "").strip()

                        ch = data.get("channel_id")

                        if content.startswith(f"{PFX}kep"):

                            await _kep(ch, content, author_id)

        except Exception as e:

            print(f"Connection error: {e}")

            await asyncio.sleep(10)

asyncio.run(connect_gateway())