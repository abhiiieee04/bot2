import asyncio
import random
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

async def safe_join(worker, group_link):
    try:
        if '+' in group_link or 'joinchat' in group_link:
            hash_string = group_link.split('+')[-1] if '+' in group_link else group_link.split('/')[-1]
            await worker(ImportChatInviteRequest(hash_string))
        else:
            entity = group_link.strip().split('/')[-1].replace('@', '')
            await worker(JoinChannelRequest(entity))
        return True, "Joined"
    except Exception as e:
        return False, type(e).__name__

async def run_prejoin(worker, active_data, status_msg):
    active_data["is_running"] = True
    groups = active_data["groups"]
    success = 0
    total = len(groups)
    
    for idx, g in enumerate(groups, 1):
        if not active_data.get("is_running"):
            await status_msg.edit(f"🛑 **Pre-Join Aborted.**\nJoined: {success}/{total}")
            return
            
        await status_msg.edit(f"⏳ **Pre-Joining...**\nProgress: {idx}/{total}\nTarget: `{g}`\n✅ Total Joined: {success}")
        
        joined, reason = await safe_join(worker, g)
        if joined: success += 1
            
        await status_msg.edit(f"⏳ **Pre-Joining...**\nProgress: {idx}/{total}\nTarget: `{g}` -> {reason}\n✅ Total Joined: {success}")
            
        if idx < total:
            await asyncio.sleep(random.uniform(15, 30))
        
    await status_msg.edit(f"🎉 **Pre-Join Complete!**\n✅ Total Joined: {success}/{total}")