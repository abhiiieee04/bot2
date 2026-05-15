import asyncio
import random

async def run_broadcast(worker, active_data, status_msg):
    active_data["is_running"] = True
    groups = active_data["groups"]
    message = active_data["msg"]
    cooldown = active_data["cooldown"]
    
    cycle = 1
    total = len(groups)
    
    while active_data["is_running"]:
        sent, failed = 0, 0
        
        for idx, g in enumerate(groups, 1):
            if not active_data["is_running"]: break 
                
            status_text = ""
            try:
                entity = g.strip().split('/')[-1].replace('@','')
                if '+' in g or 'joinchat' in g:
                    entity = await worker.get_entity(g)
                await worker.send_message(entity, message)
                sent += 1
                status_text = "✅ Sent"
            except Exception:
                failed += 1
                status_text = "❌ Not Sent"
                
            try:
                await status_msg.edit(
                    f"🚀 **Broadcasting (Cycle {cycle})...**\n"
                    f"Progress: {idx}/{total}\nTarget: `{g}` -> {status_text}\n"
                    f"📤 Sent: {sent} | ❌ Fail: {failed}"
                )
            except Exception:
                pass 
                
            await asyncio.sleep(random.uniform(1.4, 1.9))
            
        if not active_data["is_running"] or cooldown <= 0:
            await status_msg.edit(f"🛑 **Broadcast Finished/Stopped.**\nFinal Cycle: {cycle}\n📤 Total Sent: {sent} | ❌ Total Fail: {failed}")
            break
            
        await status_msg.edit(f"✅ **Cycle {cycle} Complete!**\nSent: {sent} | Fail: {failed}\n\n⏳ Waiting {cooldown} seconds before re-firing...\n*(Type /stop to cancel)*")
        
        for _ in range(cooldown):
            if not active_data["is_running"]: break
            await asyncio.sleep(1)
            
        cycle += 1