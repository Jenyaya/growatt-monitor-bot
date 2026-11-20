import os
import requests

API_TOKEN = os.environ["GROWATT_TOKEN"]
DEVICE_SN = os.environ["GROWATT_SN"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]
STATE_FILE = "state.txt"

BATTERY_STATUSES = {2}
GRID_STATUSES = {1, 5, 6}

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

    line1 = f"🔋 Заряд АКБ: *{soc}%* ({vbat} V)"
    line2 = f"🔌 Вхідна мережа: *{vac} V*"
    line3 = f"⚡ Навантаження: *{load_w} W*"
    line4 = f"📊 Статус: {status} ({status_text})"
    details_block = f"{line1}\n{line2}\n{line3}\n{line4}"

    return mode, soc, details_block

def main():
    current_mode, soc, details_block = get_inverter_status()

    last_mode = None
    last_alert = 100
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            raw = f.read().strip()
            if ":" in raw:
                last_mode, alert_part = raw.split(":", 1)
                last_alert = int(alert_part) if alert_part.isdigit() else 100
            elif raw:
                last_mode = raw

    if last_mode and current_mode != last_mode:
        if current_mode == "battery":
            send_telegram(f"🚨 *Зникла мережа! Інвертор перейшов на батарею.*\n\n{details_block}")
            last_alert = 100
        elif current_mode == "grid":
            send_telegram(f"✅ *Мережа з'явилася! Інвертор працює від мережі.*\n\n{details_block}")
            last_alert = 100
        else:
            send_telegram(f"ℹ️ *Зміна режиму інвертора*\n\n{details_block}")
    elif not last_mode:
        state_ua = "від батареї 🔋" if current_mode == "battery" else "від мережі ⚡"
        send_telegram(f"✅ *Моніторинг оновлено.* Зараз інвертор працює {state_ua}.\n\n{details_block}")

    current_alert = last_alert
    if current_mode == "battery":
        if soc < 30 and last_alert > 30:
            send_telegram(f"🆘 *Критично низький заряд АКБ (менше 30%): {soc}%!*\n\n{details_block}")
            current_alert = 30
        elif soc < 50 and last_alert > 50:
            send_telegram(f"⚠️ *Заряд АКБ впав нижче 50%: {soc}%*\n\n{details_block}")
            current_alert = 50
    elif soc >= 55:
        current_alert = 100

    with open(STATE_FILE, "w") as f:
        f.write(f"{current_mode}:{current_alert}")

if __name__ == "__main__":
    main()
