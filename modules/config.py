import os

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

raw_admins = os.environ.get("ADMIN_ID", "0")
ADMIN_IDS = [int(i.strip()) for i in raw_admins.split(",") if i.strip()]