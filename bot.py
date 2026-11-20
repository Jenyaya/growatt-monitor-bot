import os
import requests

API_TOKEN = os.environ["GROWATT_TOKEN"]
DEVICE_SN = os.environ["GROWATT_SN"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]
STATE_FILE = "state.txt"

BATTERY_STATUSES = {2}       # 2 = Battery Discharging
GRID_STATUSES = {1, 5, 6}    # 1 = Charge, 5 = Bypass / Grid

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"}, timeout=15)

def get_inverter_status():
    url = "https://openapi.growatt.com/v1/device/storage/storage_last_data"
    headers = {"token": API_TOKEN}
    res = requests.post(url, headers=headers, data={"storage_sn": DEVICE_SN}, timeout=15).json()

    if res.get("error_code") != 0:
        raise RuntimeError(f"Growatt API error: {res}")

    data = res.get("data", {})
    status = int(data.get("status", -1))
    status_text = data.get("SPF5000StatusText") or data.get("statusText", "")
    vac = round(float(data.get("vac", 0)), 1)
    soc = int(float(data.get("capacity", 0)))
    vbat = round(float(data.get("vBat", 0)), 2)
    load_w = int(float(data.get("outPutPower", 0)))

    if status in BATTERY_STATUSES or (vac == 0 and "discharge" in status_text.lower()):
        mode = "battery"
    elif status in GRID_STATUSES or vac > 170:
        mode = "grid"
    else:
        mode = f"other_{status}"

    details_block = (
        f"🔋 Заряд АКБ: *{soc}%* ({vbat} V)\n"
        f"🔌 Вхідна мережа: *{vac} V*\n"
        f"⚡ Навантаження: *{load_w} W*\n"
        f
