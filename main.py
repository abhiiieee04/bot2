import os
import io
import asyncio
from telethon import TelegramClient, events, Button
from modules import config, auth, checklinks, joining, broadcast

# 1. CLIENT SETUP
bot = TelegramClient('data/controller_bot', config.API_ID, config.API_HASH)
worker = TelegramClient('data/ptmc_worker', config.API_ID, config.API_HASH)

# 2. GLOBAL STATE
user_state = {}
session_temp = {}
active_data = {"groups": [], "msg": "", "cooldown": 0, "is_running": False}

# 3. ROUTER
@bot.on(events.NewMessage(from_users=config.ADMIN_IDS))
async def router(event):
    sid = event.sender_id
    text = event.text

    if text == '/start':
        await event.respond("🏥 **PTMC Command Center**\n`/broadcast` | `/checklinks` | `/login` | `/sessions` | `/stop`")
        
    elif text == '/stop':
        active_data["is_running"] = False
        await event.respond("🛑 **Kill switch activated.** Stopping all active worker tasks.")

    elif text == '/sessions':
        try:
            if not worker.is_connected(): await worker.connect()
            me = await worker.get_me()
            await event.respond(f"🟢 **ACTIVE WORKER**\n👤 {me.first_name}\n📞 +{me.phone}")
        except:
            await event.respond("⚠️ Worker offline. Use `/login`.")

    # --- LOGIN MODULE ---
    elif text == '/login':
        user_state[sid] = 'login_phone'
        await event.respond("📱 Enter phone (+91...):")

    elif user_state.get(sid) == 'login_phone':
        session_temp['phone'] = text
        if not worker.is_connected(): await worker.connect()
        session_temp['hash'] = await auth.start_login(worker, text)
        user_state[sid] = 'login_code'
        await event.respond("📩 Enter OTP:")

    elif user_state.get(sid) == 'login_code':
        res = await auth.complete_login(worker, session_temp['phone'], text.replace(" ",""), session_temp['hash'])
        if res == "SUCCESS":
            await event.respond("✅ Worker Authenticated!")
            user_state[sid] = None
        elif res == "2FA_REQUIRED":
            user_state[sid] = 'login_2fa'
            await event.respond("🔒 Enter 2FA Password:")

    elif user_state.get(sid) == 'login_2fa':
        res = await auth.complete_login(worker, None, None, None, password=text)
        if res == "SUCCESS":
            await event.respond("✅ 2FA Login Successful!")
            user_state[sid] = None

    # --- FILE HANDLERS (CHECKER & BROADCAST) ---
    elif text == '/checklinks':
        user_state[sid] = 'checking'
        await event.respond("🔍 Upload `.txt` list to verify:")

    elif text == '/broadcast':
        user_state[sid] = 'awaiting_broadcast_file'
        await event.respond("📋 Upload `.txt` group list:")

    elif event.document and event.document.mime_type == 'text/plain':
        file = await event.download_media(file=bytes)
        entries = [l.strip() for l in file.decode("utf-8", errors="ignore").splitlines() if l.strip()]
        
        if user_state.get(sid) == 'checking':
            status = await event.respond("🔍 Starting scan...")
            g, c, u = await checklinks.validate_links(bot, entries, status)
            
            out = []
            if g: f=io.BytesIO("\n".join(g).encode()); f.name="groups.txt"; out.append(f)
            if c: f=io.BytesIO("\n".join(c).encode()); f.name="channels.txt"; out.append(f)
            if u: f=io.BytesIO("\n".join(u).encode()); f.name="users.txt"; out.append(f)
            
            if out:
                await event.respond(f"✅ **Check Complete**\nGroups: {len(g)}\nChannels: {len(c)}\nUsers: {len(u)}", file=out)
            else:
                await event.respond("⚠️ No valid public Groups, Channels, or Users found in that file.")
                
            user_state[sid] = None

        elif user_state.get(sid) == 'awaiting_broadcast_file':
            active_data["groups"] = entries
            user_state[sid] = 'awaiting_broadcast_msg'
            await event.respond(f"✅ {len(entries)} groups loaded.\n\nType the Alert Message:")

    elif user_state.get(sid) == 'awaiting_broadcast_msg' and text:
        active_data["msg"] = text
        user_state[sid] = 'awaiting_cooldown'
        await event.respond("⏱ **Enter Re-fire Cooldown (in seconds)**:\n*(Type '0' to run once and stop)*")

    elif user_state.get(sid) == 'awaiting_cooldown' and text:
        try:
            active_data["cooldown"] = int(text.strip())
            user_state[sid] = None
            btns = [[Button.inline("🛡️ PRE-JOIN", b'pre_join')], [Button.inline("🚀 BLAST", b'blast')]]
            await event.respond(f"⚠️ **READY**\nGroups: {len(active_data['groups'])}\nCooldown: {active_data['cooldown']}s\nMsg: `{active_data['msg'][:30]}...`", buttons=btns)
        except ValueError:
            await event.respond("⚠️ Please enter a valid number.")

# 4. BUTTON CALLBACKS
@bot.on(events.CallbackQuery(from_users=config.ADMIN_IDS))
async def handle_buttons(event):
    await event.answer() 
    if not worker.is_connected(): await worker.connect()
    
    if event.data == b'pre_join':
        status_msg = await event.edit("⏳ **Starting Pre-Join...**")
        await joining.run_prejoin(worker, active_data, status_msg)

    elif event.data == b'blast':
        status_msg = await event.edit("🚀 **Starting Broadcast...**")
        await broadcast.run_broadcast(worker, active_data, status_msg)

async def main():
    print("🏥 PTMC Server Booting...")
    await bot.start(bot_token=config.BOT_TOKEN)
    try: await worker.start()
    except: pass
    print("✅ System Ready.")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())