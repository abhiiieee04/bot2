import asyncio
import io
import os
import random
import re
from telethon import TelegramClient, events, Button
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors.rpcerrorlist import (
    PeerFloodError, 
    ChatWriteForbiddenError, 
    UserAlreadyParticipantError,
    InviteHashExpiredError,
    UsernameInvalidError,
    FloodWaitError,
    SessionPasswordNeededError
)

# ── 1. CREDENTIALS (RAILWAY ENVIRONMENT VARIABLES) ─────────────────────────────
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_IDS = [int(i.strip()) for i in os.environ.get("ADMIN_ID").split(",")]

# ── 2. CLIENT SETUP ────────────────────────────────────────────────────────────
bot = TelegramClient('controller_bot', API_ID, API_HASH)
worker = TelegramClient('ptmc_worker', API_ID, API_HASH)

# Global State Management
user_state = {"mode": None}
broadcast_data = {"groups": [], "message": ""}
login_data = {"phone": None, "phone_code_hash": None}

# ── 3. WORKER FUNCTIONS (JOINING & CHECKING) ───────────────────────────────────
async def safe_join(group_link):
    try:
        if '+' in group_link or 'joinchat' in group_link:
            hash_string = group_link.split('+')[-1] if '+' in group_link else group_link.split('/')[-1]
            await worker(ImportChatInviteRequest(hash_string))
        else:
            entity = group_link.split('/')[-1].replace('@', '')
            await worker(JoinChannelRequest(entity))
        return True, "✅ Joined successfully"
    except UserAlreadyParticipantError:
        return True, "ℹ️ Already a member"
    except (InviteHashExpiredError, UsernameInvalidError):
        return False, "❌ Invalid or Expired link"
    except PeerFloodError:
        return False, "🛑 RATE LIMIT HIT"
    except FloodWaitError as e:
        return False, f"🛑 FLOOD WAIT: {e.seconds}s"
    except Exception as e:
        return False, f"❌ Error: {type(e).__name__}"

async def check_one_link(raw_link):
    result = {"link": raw_link, "status": "unknown"}
    if '+' in raw_link or 'joinchat' in raw_link:
        result["status"] = "private_invite (Cannot verify without joining)"
        return result
    try:
        entity_name = raw_link.split('/')[-1].replace('@', '')
        entity = await worker.get_entity(entity_name)
        title = getattr(entity, 'title', getattr(entity, 'username', 'Unknown'))
        result["status"] = f"✅ OK - {title}"
    except ValueError:
        result["status"] = "❌ Not Found / Invalid"
    except Exception as e:
        result["status"] = f"❌ Error: {type(e).__name__}"
    return result

# ── 4. CONTROLLER INTERFACE (TELEGRAM BOT) ─────────────────────────────────────

@bot.on(events.NewMessage(pattern='/start', from_users=ADMIN_IDS))
async def cmd_start(event):
    user_state["mode"] = None
    await event.respond(
        "🏥 **PTMC Command Center**\n\n"
        "**Commands:**\n"
        "🟢 `/broadcast` - Setup an emergency alert\n"
        "🔍 `/checklinks` - Validate a list of groups\n"
        "📱 `/login` - Authenticate a new worker account via OTP\n"
        "⚙️ `/sessions` - View current active worker data\n"
        "❌ `/cancel` - Abort current operation"
    )

@bot.on(events.NewMessage(pattern='/cancel', from_users=ADMIN_IDS))
async def cmd_cancel(event):
    user_state["mode"] = None
    broadcast_data["groups"] = []
    broadcast_data["message"] = ""
    login_data["phone"] = None
    await event.respond("🛑 Operation cancelled. Returning to standby.")

# --- SESSION INFO MODULE ---
@bot.on(events.NewMessage(pattern='/sessions', from_users=ADMIN_IDS))
async def cmd_sessions(event):
    status_msg = await event.respond("⚙️ Fetching active worker data...")
    try:
        if not worker.is_connected():
            await worker.connect()
        me = await worker.get_me()
        if me is None:
            raise Exception("Not logged in")
            
        name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        username = f"@{me.username}" if me.username else "No Username"
        phone = f"+{me.phone}" if me.phone else "Hidden"
        
        await status_msg.edit(
            f"🟢 **CURRENT ACTIVE SESSION**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Name:** {name}\n"
            f"🔗 **Username:** {username}\n"
            f"📞 **Phone:** {phone}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
    except Exception:
        await status_msg.edit("⚠️ Worker is offline or not authenticated. Use `/login` to connect an account.")

# --- REMOTE LOGIN MODULE ---
@bot.on(events.NewMessage(pattern='/login', from_users=ADMIN_IDS))
async def cmd_login(event):
    user_state["mode"] = "awaiting_phone"
    await event.respond("📱 **Remote Login Protocol**\n\nPlease reply with the phone number of the worker account in international format (e.g., +1234567890).")

# --- BROADCAST & CHECKLINKS TRIGGER ---
@bot.on(events.NewMessage(pattern='/broadcast', from_users=ADMIN_IDS))
async def cmd_broadcast(event):
    user_state["mode"] = "awaiting_broadcast_file"
    await event.respond("📋 **Broadcast Mode**\nPlease upload the `.txt` file containing your group links.")

@bot.on(events.NewMessage(pattern='/checklinks', from_users=ADMIN_IDS))
async def cmd_checklinks(event):
    user_state["mode"] = "awaiting_check_file"
    await event.respond("🔍 **Link Checker Mode**\nPlease upload the `.txt` file containing the links to verify.")

# --- UNIVERSAL TEXT & FILE HANDLER ---
@bot.on(events.NewMessage(from_users=ADMIN_IDS))
async def universal_handler(event):
    if event.text and event.text.startswith('/'): return

    # --- 1. HANDLE LOGIN: PHONE NUMBER ---
    if user_state["mode"] == "awaiting_phone" and event.text:
        login_data["phone"] = event.text.strip()
        status_msg = await event.respond("⏳ Requesting OTP code from Telegram...")
        try:
            if not worker.is_connected():
                await worker.connect()
            result = await worker.send_code_request(login_data["phone"])
            login_data["phone_code_hash"] = result.phone_code_hash
            user_state["mode"] = "awaiting_code"
            await status_msg.edit("📩 **Code Sent!**\nPlease enter the OTP you received.\n*(If Telegram blocks it, send it with spaces like: `123 45`)*")
        except Exception as e:
            await status_msg.edit(f"❌ Error sending code: {e}")
            user_state["mode"] = None
        return

    # --- 2. HANDLE LOGIN: OTP CODE ---
    if user_state["mode"] == "awaiting_code" and event.text:
        code = event.text.replace(" ", "").replace("-", "")
        status_msg = await event.respond("⏳ Authenticating...")
        try:
            await worker.sign_in(login_data["phone"], code, phone_code_hash=login_data["phone_code_hash"])
            me = await worker.get_me()
            user_state["mode"] = None
            await status_msg.edit(f"✅ **Login Successful! Session Saved.**\nWorker is now online as: **{me.first_name}**")
        except SessionPasswordNeededError:
            user_state["mode"] = "awaiting_password"
            await status_msg.edit("🔒 **Two-Step Verification Enabled.**\nPlease reply with your 2FA password:")
        except Exception as e:
            await status_msg.edit(f"❌ Login failed: {e}")
            user_state["mode"] = None
        return

    # --- 3. HANDLE LOGIN: 2FA PASSWORD ---
    if user_state["mode"] == "awaiting_password" and event.text:
        status_msg = await event.respond("⏳ Verifying password...")
        try:
            await worker.sign_in(password=event.text.strip())
            me = await worker.get_me()
            user_state["mode"] = None
            await status_msg.edit(f"✅ **Login Successful! Session Saved.**\nWorker is now online as: **{me.first_name}**")
        except Exception as e:
            await status_msg.edit(f"❌ Password incorrect or login failed: {e}")
            user_state["mode"] = None
        return

    # --- 4. HANDLE FILE UPLOADS (.txt files) ---
    if event.document and event.document.mime_type == 'text/plain':
        if user_state["mode"] not in ["awaiting_broadcast_file", "awaiting_check_file"]:
            await event.respond("⚠️ Please send `/broadcast` or `/checklinks` first.")
            return

        status_msg = await event.respond("📥 Downloading file to Railway server...")
        file_path = await event.download_media(file=bytes)
        text_data = file_path.decode("utf-8", errors="ignore")
        groups = [line.strip() for line in text_data.splitlines() if line.strip()]
        
        if not groups:
            await status_msg.edit("⚠️ File is empty or invalid. Try again.")
            return

        # Path A: Check Links Execution
        if user_state["mode"] == "awaiting_check_file":
            await status_msg.edit(f"🔍 **Checking {len(groups)} links...**\nThis will take a moment.")
            user_state["mode"] = None
            valid_lines, invalid_lines = [], []
            
            for i, link in enumerate(groups, 1):
                res = await check_one_link(link)
                line_str = f"{link} — {res['status']}"
                if "✅" in res["status"] or "private_invite" in res["status"]:
                    valid_lines.append(line_str)
                else:
                    invalid_lines.append(line_str)
                    
                if i % 10 == 0:
                    await status_msg.edit(f"🔍 Checking... {i}/{len(groups)}")
                await asyncio.sleep(0.3)
                
            files_to_send = []
            
            if valid_lines:
                valid_file = io.BytesIO("\n".join(valid_lines).encode())
                valid_file.name = "valid_links.txt"
                files_to_send.append(valid_file)
                
            if invalid_lines:
                invalid_file = io.BytesIO("\n".join(invalid_lines).encode())
                invalid_file.name = "invalid_links.txt"
                files_to_send.append(invalid_file)
                
            await event.respond(
                f"✅ **Check Complete**\n✔️ Valid: {len(valid_lines)}\n❌ Invalid: {len(invalid_lines)}", 
                file=files_to_send
            )
            return

        # Path B: Broadcast Execution
        if user_state["mode"] == "awaiting_broadcast_file":
            broadcast_data["groups"] = groups
            user_state["mode"] = "awaiting_broadcast_msg"
            await status_msg.edit(f"✅ Loaded **{len(groups)}** groups.\n\nNow, type the **Emergency Alert Message** directly to me:")
            return

    # --- 5. HANDLE BROADCAST MESSAGE INPUT ---
    if event.text and user_state["mode"] == "awaiting_broadcast_msg":
        broadcast_data["message"] = event.text
        user_state["mode"] = None
        
        buttons = [
            [Button.inline("🛡️ RUN PRE-JOIN (Slow & Safe)", b"pre_join")],
            [Button.inline("🚀 START 11-MIN BROADCAST", b"blast")]
        ]
        await event.respond(
            f"⚠️ **DATA LOCKED IN**\n"
            f"• Groups: {len(broadcast_data['groups'])}\n"
            f"• Message Preview: `{event.text[:50]}...`\n\n"
            f"Select operation:", buttons=buttons
        )

# ── 5. EXECUTION ENGINE (BUTTON CALLBACKS) ─────────────────────────────────────
@bot.on(events.CallbackQuery(from_users=ADMIN_IDS))
async def button_handler(event):
    data = event.data.decode()
    groups = broadcast_data["groups"]
    msg = broadcast_data["message"]
    
    # Pre-broadcast sanity check
    if not worker.is_connected():
        await worker.connect()
    
    if data == "pre_join":
        await event.edit("⏳ **Pre-Join Protocol Initiated...**\n(Using safe 15-30s delay between joins).")
        success_count = 0
        
        for group in groups:
            success, status = await safe_join(group)
            if success: success_count += 1
            if "RATE LIMIT" in status or "FLOOD WAIT" in status:
                await bot.send_message(ADMIN_IDS, f"🛑 **CRITICAL HALT:** {status}")
                break
            await asyncio.sleep(random.uniform(15.0, 30.0))
            
        await bot.send_message(ADMIN_IDS, f"🎉 **Pre-Join Complete.** Account successfully entered {success_count} groups.")

    elif data == "blast":
        await event.edit("🚀 **Emergency Broadcast Initiated.**\n(Using 1.4s-1.9s random delay).")
        sent_count, fail_count = 0, 0
        
        for group in groups:
            try:
                entity = group.split('/')[-1].replace('@', '')
                if '+' in group or 'joinchat' in group:
                    entity = await worker.get_entity(group)
                await worker.send_message(entity, msg)
                sent_count += 1
            except ChatWriteForbiddenError:
                fail_count += 1 
            except FloodWaitError as e:
                await bot.send_message(ADMIN_IDS, f"🛑 **FLOOD WAIT!** Telegram paused the worker for {e.seconds} seconds.")
                await asyncio.sleep(e.seconds + 5)
            except PeerFloodError:
                await bot.send_message(ADMIN_IDS, "🛑 **RATE LIMIT HIT!** The worker account is pausing for 5 minutes...")
                await asyncio.sleep(300)
            except Exception:
                fail_count += 1
                
            # EXACT 11-MINUTE PURE DELAY LOGIC
            await asyncio.sleep(random.uniform(1.4, 1.9))
            
        await bot.send_message(ADMIN_IDS, f"✅ **Broadcast Complete!**\n📤 Delivered: {sent_count}\n❌ Failed/Skipped: {fail_count}\nSystem returning to standby.")

# ── 6. INITIALIZATION ──────────────────────────────────────────────────────────
async def main():
    print("🏥 PTMC Railway Server Booting Up...")
    await bot.start(bot_token=BOT_TOKEN)
    
    # Connect worker if session exists in the Railway Volume
    try:
        await worker.connect()
        me = await worker.get_me()
        if me:
            print(f"✅ Worker System Online as {me.first_name}.")
        else:
            print("⚠️ Worker connected but not authenticated. Use /login on Telegram.")
    except Exception as e:
        print(f"⚠️ Worker init status: {e}")
        
    print("✅ System fully online and connected to Telegram Command Center.")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())