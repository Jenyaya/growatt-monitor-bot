import os
import requests

API_TOKEN = os.environ["GROWATT_TOKEN"]
DEVICE_SN = os.environ["GROWATT_SN"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]
STATE_FILE = "state.txt"

# Коди статусів Growatt Storage (SPF)
BATTERY_STATUSES = {2}          # 2 = storage.status.discharge (робота від АКБ)
GRID_STATUSES = {1, 5, 6}       # 1 = charge, 5 = bypass (робота від мережі)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=15)

def get_inverter_status():
    url = "https://openapi.growatt.com/v1/device/storage/storage_data_info"
    headers = {"token": API_TOKEN}
    res = requests.get(url, headers=headers, params={"device_sn": DEVICE_SN}, timeout=15).json()

    if res.get("error_code") != 0:
        raise RuntimeError(f"Growatt API error: {res}")

    data = res.get("data", {})
    if data.get("lost") is True:
        return None, "Інвертор офлайн (lost=true)"

    status = int(data.get("status", -1))
    status_text = data.get("statusText", "")

    if status in BATTERY_STATUSES or "discharge" in status_text.lower():
        mode = "battery"
    elif status in GRID_STATUSES or "bypass" in status_text.lower() or "charge" in status_text.lower():
        mode = "grid"
    else:
        mode = f"other_{status}"

    return mode, f"status={status} ({status_text})"

def main():
    current_mode, details = get_inverter_status()
    if current_mode is None:
        print(details)
        return

    last_mode = None
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            last_mode = f.read().strip()

    if last_mode and current_mode != last_mode:
        if current_mode == "battery":
            send_telegram(f"🔋 Зникла мережа! Інвертор перейшов на батарею.\nДеталі: {details}")
        elif current_mode == "grid":
            send_telegram(f"⚡ Мережа з'явилася! Інвертор працює від мережі.\nДеталі: {details}")
        else:
            send_telegram(f"ℹ️ Зміна стану інвертора: {details}")
    elif not last_mode:
        state_ua = "від батареї 🔋" if current_mode == "battery" else "від мережі ⚡"
        send_telegram(f"✅ Моніторинг запущено. Зараз інвертор працює {state_ua}.\n({details})")

    with open(STATE_FILE, "w") as f:
        f.write(current_mode)

if __name__ == "__main__":
    main()
