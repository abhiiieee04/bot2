from telethon.errors.rpcerrorlist import SessionPasswordNeededError

async def start_login(worker, phone):
    res = await worker.send_code_request(phone)
    return res.phone_code_hash

async def complete_login(worker, phone, code, hash_val, password=None):
    try:
        if password:
            await worker.sign_in(password=password)
        else:
            await worker.sign_in(phone, code, phone_code_hash=hash_val)
        return "SUCCESS"
    except SessionPasswordNeededError:
        return "2FA_REQUIRED"
    except Exception as e:
        return str(e)