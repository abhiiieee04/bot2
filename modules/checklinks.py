import io
import re
import asyncio

USERNAME_RE = re.compile(r"^@?[A-Za-z0-9_]{5,32}$")
TG_LINK_RE = re.compile(r"^https?://t\.me/(.+)$", re.I)
TG_ID_RE = re.compile(r"^-100\d{10,}$")
INVITE_RE = re.compile(r"^(https?://t\.me/\+|https?://t\.me/joinchat/)", re.I)

def normalize_entry(line: str) -> str:
    return line.strip().split("?")[0].split("#")[0].strip()

def parse_entry(line: str):
    s = normalize_entry(line)
    if not s: return "empty", None
    if INVITE_RE.match(s): return "invite", s
    if TG_ID_RE.match(s): return "chat_id", s
        
    m = TG_LINK_RE.match(s)
    if m:
        tail = m.group(1).strip("/")
        if tail.startswith("+") or tail.startswith("joinchat/"): return "invite", s
        if "/" in tail: tail = tail.split("/")[0]
        if tail.startswith("c/"): return "chat_id", s
        return "username", tail.lstrip("@")

    if USERNAME_RE.match(s): return "username", s.lstrip("@")
    return "invalid", s

async def validate_links(bot, entries, status_msg):
    groups, channels, users = [], [], []
    total = len(entries)

    for idx, raw in enumerate(entries, 1):
        kind, parsed = parse_entry(raw)

        if kind in ("empty", "invalid", "invite"):
            pass
        else:
            query = parsed
            if kind == "username": query = "@" + parsed
            elif kind == "chat_id":
                try: query = int(parsed)
                except ValueError: pass

            try:
                entity = await bot.get_entity(query)
                from telethon.tl.types import Channel, Chat, User
                
                if isinstance(entity, User): users.append(raw)
                elif isinstance(entity, Channel):
                    if entity.broadcast: channels.append(raw)
                    else: groups.append(raw)
                elif isinstance(entity, Chat): groups.append(raw)
            except Exception:
                pass 

        if idx % 10 == 0 or idx == total:
            try: await status_msg.edit(f"🔍 **Checking Links...**\nProgress: {idx}/{total}")
            except Exception: pass 
                
        await asyncio.sleep(0.3)

    return groups, channels, users