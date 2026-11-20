import os
import requests

API_TOKEN = os.environ["GROWATT_TOKEN"]
DEVICE_SN = os.environ["GROWATT_SN"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_IDS = [cid.strip() for cid in os.environ["TG_CHAT_ID"].split(",") if cid.strip()]
IS_MANUAL = os.environ.get("EVENT_NAME") == "workflow_dispatch"
STATE_FILE = "state.txt"

BATTERY_STATUSES = {2}
GRID_STATUSES = {1, 5, 6}


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

        # Підтримка і звичайних повідомлень/груп (message), і постів у каналі (channel_post)
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
    status = int(data.get("status", -1))
    status_text = data.get("SPF5000StatusText") or data.get("statusText", "")
    vac = round(float(data.get("vac", 0)), 1)
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
        mode = f"other_{status}"

    line1 = f"🔋 Заряд АКБ: *{soc}%* ({vbat} V)"
    line2 = f"🔌 Вхідна мережа: *{vac} V*"
    line3 = f"⚡ Навантаження: *{load_w} W*"
    line4 = f"📊 Статус: {status} ({status_text})"
    details_block = f"{line1}\n{line2}\n{line3}\n{line4}"

    return mode, soc, details_block, err_key, err_desc


def main():
    try:
        current_mode, soc, details_block, err_key, err_desc = get_inverter_status()
    except Exception as e:
        send_telegram(f"🛠 *Збій моніторингу Growatt:*\n`{e}`")
        raise

    # Формат state.txt: mode:alert_level:err_key:last_update_id
    last_mode = None
    last_alert = 100
    last_err = "0"
    last_update_id = 0

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            parts = f.read().strip().split(":")
            if len(parts) >= 1 and parts[0]:
                last_mode = parts[0]
            if len(parts) >= 2 and parts[1].isdigit():
                last_alert = int(parts[1])
            if len(parts) >= 3:
                last_err = parts[2]
            if len(parts) >= 4 and parts[3].isdigit():
                last_update_id = int(parts[3])

    # Перевіряємо чергу команд Telegram (/status або "статус")
    new_update_id, requester_chat_id = check_status_command(last_update_id)

    # 1. Сповіщення про критичні помилки інвертора / BMS
    if err_key != "0" and err_key != last_err:
        send_telegram(f"🔥 *АВАРІЯ / ПОМИЛКА ІНВЕРТОРА!*\n{err_desc}\n\n{details_block}")
    elif err_key == "0" and last_err != "0":
        send_telegram(f"✅ *Помилку інвертора усунуто!* Робота в нормі.\n\n{details_block}")

    # 2. Сповіщення при зміні режиму, першому запуску, ручному Run workflow або запиті статусу
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
        send_telegram(f"✅ *Моніторинг запущено.* Зараз інвертор працює {state_ua}.\n\n{details_block}")
    elif IS_MANUAL:
        state_ua = "від батареї 🔋" if current_mode == "battery" else "від мережі ⚡"
        send_telegram(f"🔄 *Ручна перевірка:* інвертор працює {state_ua}.\n\n{details_block}")
    elif requester_chat_id:
        state_ua = "від батареї 🔋" if current_mode == "battery" else "від мережі ⚡"
        send_telegram(
            f"📊 *Поточний стан:* інвертор працює {state_ua}.\n\n{details_block}",
            target_chat_id=requester_chat_id,
        )

    # 3. Попередження при падінні заряду АКБ нижче 50% та 30%
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
        f.write(f"{current_mode}:{current_alert}:{err_key}:{new_update_id}")


if __name__ == "__main__":
    main()
