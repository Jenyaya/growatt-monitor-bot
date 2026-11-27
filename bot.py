import os
import requests

API_TOKEN = os.environ["GROWATT_TOKEN"]
DEVICE_SN = os.environ["GROWATT_SN"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_IDS = [cid.strip() for cid in os.environ["TG_CHAT_ID"].split(",") if cid.strip()]
STATE_FILE = "state.txt"

BATTERY_STATUSES = {2}
GRID_STATUSES = {1, 5, 6, 8, 9, 10, 11}
HIGH_LOAD_THRESHOLD_W = 2500
HIGH_LOAD_RESET_W = 1700


def send_telegram(text, target_chat_id=None):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    recipients = [target_chat_id] if target_chat_id else TG_CHAT_IDS
    for chat_id in recipients:
        try:
            res = requests.post(
                url,
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=15,
            ).json()
            if not res.get("ok"):
                print(f"Помилка Telegram API для чату {chat_id}: {res}")
        except Exception as e:
            print(f"Помилка відправки в чат {chat_id}: {e}")


def check_status_command(last_update_id):
    """Перевіряє вхідні повідомлення та пости в каналі на наявність команди /status або 'статус'."""
    url = f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates"
    try:
        res = requests.get(url, params={"offset": last_update_id + 1, "timeout": 5}, timeout=15).json()
    except Exception as e:
        print(f"Помилка читання getUpdates: {e}")
        return last_update_id, None

    if not res.get("ok"):
        return last_update_id, None

    new_update_id = last_update_id
    requester_chat_id = None

    for item in res.get("result", []):
        upd_id = item.get("update_id", 0)
        if upd_id > new_update_id:
            new_update_id = upd_id

        msg = item.get("message") or item.get("channel_post") or {}
        text = (msg.get("text") or "").strip().lower()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        if text.startswith("/status") or text == "статус":
            if not TG_CHAT_IDS or chat_id in TG_CHAT_IDS:
                requester_chat_id = chat_id

    return new_update_id, requester_chat_id


def get_inverter_status():
    url = "https://openapi.growatt.com/v1/device/storage/storage_last_data"
    headers = {"token": API_TOKEN}
    res = requests.post(url, headers=headers, data={"storage_sn": DEVICE_SN}, timeout=15).json()

    if res.get("error_code") != 0:
        raise RuntimeError(f"Помилка Growatt API: {res.get('error_msg')} (код {res.get('error_code')})")

    data = res.get("data", {})
    # print("DEBUG GROWATT KEYS:", {k: v for k, v in data.items() if "v" in k.lower() or "ac" in k.lower() or "grid" in k.lower()})

    status = int(data.get("status", -1))
    status_text = data.get("SPF5000StatusText") or data.get("statusText", "")

    vac = 0.0
    for key in ("vGrid", "vacr", "vac", "vAcInput", "gridVolt"):
        val = data.get(key)
        if val is not None and float(val) > 0:
            vac = round(float(val), 1)
            break

    soc = int(float(data.get("capacity", 0)))
    vbat = round(float(data.get("vBat", 0)), 2)
    load_w = int(float(data.get("outPutPower", 0)))

    inv_err_code = int(data.get("errorCode", 0))
    inv_err_text = data.get("errorText", "")
    bms_err = int(data.get("bmsError", 0))

    if inv_err_code != 0 or bms_err != 0:
        err_key = f"{inv_err_code}_{bms_err}"
        err_desc = f"Інвертор: {inv_err_code} ({inv_err_text}), BMS: {bms_err}"
    else:
        err_key = "0"
        err_desc = ""

    if status in BATTERY_STATUSES or (vac == 0 and "discharge" in status_text.lower()):
        mode = "battery"
    elif status in GRID_STATUSES or vac > 170:
        mode = "grid"
    else:
        mode = f
