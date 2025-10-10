# -*- coding: utf-8 -*-
import os
import json
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# =========================
# Configuration & Globals
# =========================
API_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("API_TOKEN") or "PUT_YOUR_TELEGRAM_BOT_TOKEN_HERE"

# NOTE: Update admin IDs as needed or set ADMINS env var as comma-separated IDs
_env_admins = os.getenv("ADMINS", "").strip()
if _env_admins:
    try:
        admins = [int(x) for x in _env_admins.split(",") if x.strip()]
    except Exception:
        admins = []
else:
    admins = []  # e.g., [123456789, 987654321]

bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML")

# Files
USER_DATA_FILE = "user_data.json"
CONFIG_FILE = "config.json"
WITHDRAW_PENDING_FILE = "withdraw_pending.json"
WITHDRAW_LOGS_FILE = "withdraw_logs.json"

# Withdraw modes
MODE_CODE = "CODE"
MODE_STK = "STK"
MODE_NHAN_VAT = "NHÂN VẬT"
VALID_MODES = [MODE_CODE, MODE_STK, MODE_NHAN_VAT]

# In-memory state
user_data: Dict[str, Dict[str, Any]] = {}
user_states: Dict[int, Dict[str, Any]] = {}
admin_states: Dict[int, Dict[str, Any]] = {}

_file_lock = threading.Lock()

# =========================
# Persistence helpers
# =========================

def _load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data: Any) -> None:
    with _file_lock:
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)


# =========================
# Existing bot helpers (as requested)
# =========================

def initialize_user(user_id: int) -> None:
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {"balance": 0}
        save_user_data(user_data)


def save_user_data(data: Dict[str, Dict[str, Any]]) -> None:
    _save_json(USER_DATA_FILE, data)


def load_user_data() -> Dict[str, Dict[str, Any]]:
    return _load_json(USER_DATA_FILE, {})


# =========================
# Business helpers: users & balance
# =========================

def get_user_balance(user_id: int) -> int:
    initialize_user(user_id)
    return int(user_data.get(str(user_id), {}).get("balance", 0))


def set_user_balance(user_id: int, new_balance: int) -> None:
    initialize_user(user_id)
    user_data[str(user_id)]["balance"] = int(max(0, new_balance))
    save_user_data(user_data)


def add_user_balance(user_id: int, amount: int) -> None:
    initialize_user(user_id)
    current = get_user_balance(user_id)
    set_user_balance(user_id, current + int(amount))


def subtract_user_balance(user_id: int, amount: int) -> bool:
    initialize_user(user_id)
    current = get_user_balance(user_id)
    amount = int(amount)
    if amount <= current:
        set_user_balance(user_id, current - amount)
        return True
    return False


# =========================
# Business helpers: config & withdraw
# =========================

def ensure_config() -> Dict[str, Any]:
    cfg = _load_json(CONFIG_FILE, {})
    if "active_withdraw_mode" not in cfg:
        cfg["active_withdraw_mode"] = MODE_CODE
        _save_json(CONFIG_FILE, cfg)
    return cfg


def get_active_mode() -> str:
    cfg = ensure_config()
    mode = cfg.get("active_withdraw_mode", MODE_CODE)
    if mode not in VALID_MODES:
        mode = MODE_CODE
    return mode


def set_active_mode(mode: str) -> None:
    if mode not in VALID_MODES:
        raise ValueError("Invalid withdraw mode")
    cfg = ensure_config()
    cfg["active_withdraw_mode"] = mode
    _save_json(CONFIG_FILE, cfg)


def list_pending_requests() -> List[Dict[str, Any]]:
    items = _load_json(WITHDRAW_PENDING_FILE, [])
    return [it for it in items if it.get("status") == "pending"]


def _save_pending_list(items: List[Dict[str, Any]]) -> None:
    _save_json(WITHDRAW_PENDING_FILE, items)


def _append_pending(item: Dict[str, Any]) -> None:
    items = _load_json(WITHDRAW_PENDING_FILE, [])
    items.append(item)
    _save_pending_list(items)


def _append_log(entry: Dict[str, Any]) -> None:
    logs = _load_json(WITHDRAW_LOGS_FILE, [])
    logs.append(entry)
    _save_json(WITHDRAW_LOGS_FILE, logs)


def _make_approval_id(user_id: int, mode: str, amount: int) -> str:
    return f"{user_id}:{mode}:{amount}"


def find_pending_by_id_str(id_str: str) -> Optional[Tuple[int, Dict[str, Any]]]:
    # id_str format: userID:type:amount
    parts = id_str.split(":")
    if len(parts) != 3:
        return None
    try:
        uid = int(parts[0])
        mode = parts[1]
        amount = int(parts[2])
    except Exception:
        return None

    items = _load_json(WITHDRAW_PENDING_FILE, [])
    for idx, it in enumerate(items):
        if it.get("status") != "pending":
            continue
        if it.get("user_id") == uid and it.get("type") == mode and int(it.get("amount", 0)) == amount:
            return idx, it
    return None


# =========================
# UI helpers: keyboards & prompts
# =========================

def build_main_menu(is_admin: bool) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    row1 = [KeyboardButton("💸 Rút tiền")]
    kb.row(*row1)
    if is_admin:
        kb.row(KeyboardButton("⚙️ Cấu hình rút tiền"))
        kb.row(KeyboardButton("📋 Duyệt rút tiền"))
    return kb


def build_config_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("🎁 Rút CODE"))
    kb.row(KeyboardButton("💳 Rút STK"))
    kb.row(KeyboardButton("🧙 Rút TÊN NHÂN VẬT"))
    kb.row(KeyboardButton("◀️ Quay lại"))
    return kb


def send_main_menu(chat_id: int, is_admin: bool) -> None:
    kb = build_main_menu(is_admin)
    bot.send_message(chat_id, "Chọn chức năng:", reply_markup=kb)


def parse_amount(text: str) -> Optional[int]:
    digits = "".join([ch for ch in str(text) if ch.isdigit()])
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


def format_currency(amount: int) -> str:
    return f"{int(amount):,}".replace(",", ".")


# =========================
# Start-up: load user data
# =========================
user_data = load_user_data()


# =========================
# Handlers
# =========================
@bot.message_handler(commands=["start"])  # Only for onboarding; all control is via reply keyboard
def handle_start(message):
    user_id = message.from_user.id
    initialize_user(user_id)
    is_admin = user_id in admins
    send_main_menu(message.chat.id, is_admin)


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = (message.text or "").strip()
    is_admin = user_id in admins

    # Global quick actions
    if text == "◀️ Quay lại":
        user_states.pop(user_id, None)
        admin_states.pop(user_id, None)
        send_main_menu(chat_id, is_admin)
        return

    # Admin approve/reject commands typed as text (no slash commands)
    upper = text.upper()
    if is_admin and (upper.startswith("DUYET ") or upper.startswith("HUY ")):
        parts = text.split(" ", 1)
        if len(parts) != 2:
            bot.send_message(chat_id, "Sai định dạng. Vui lòng nhập: DUYET userID:type:amount hoặc HUY userID:type:amount")
            return
        action, id_str = parts[0].upper(), parts[1].strip()
        _handle_admin_approval_action(user_id, chat_id, action, id_str)
        return

    # Main menu entries
    if text == "💸 Rút tiền":
        _handle_withdraw_entry(user_id, chat_id)
        return

    if is_admin and text == "⚙️ Cấu hình rút tiền":
        kb = build_config_keyboard()
        mode = get_active_mode()
        bot.send_message(chat_id, f"Chọn chế độ rút đang hoạt động (hiện tại: <b>{mode}</b>):", reply_markup=kb)
        admin_states[user_id] = {"state": "awaiting_config_choice"}
        return

    if is_admin and text == "📋 Duyệt rút tiền":
        _handle_list_pending(chat_id)
        admin_states[user_id] = {"state": "awaiting_approval_input"}
        return

    # Admin config choices
    st = admin_states.get(user_id, {})
    if is_admin and st.get("state") == "awaiting_config_choice":
        mapping = {
            "🎁 Rút CODE": MODE_CODE,
            "💳 Rút STK": MODE_STK,
            "🧙 Rút TÊN NHÂN VẬT": MODE_NHAN_VAT,
        }
        if text in mapping:
            set_active_mode(mapping[text])
            bot.send_message(chat_id, f"Đã bật chế độ rút: <b>{mapping[text]}</b>")
            admin_states.pop(user_id, None)
            send_main_menu(chat_id, True)
            return
        else:
            bot.send_message(chat_id, "Vui lòng chọn 1 trong 3 chế độ rút hoặc nhấn ◀️ Quay lại")
            return

    # Withdraw flow input
    ust = user_states.get(user_id)
    if ust and ust.get("state") == "awaiting_withdraw_input":
        _handle_withdraw_input(user_id, chat_id, ust.get("mode"), text)
        return

    # Fallback: show main menu
    send_main_menu(chat_id, is_admin)


# =========================
# Flow implementations
# =========================

def _handle_withdraw_entry(user_id: int, chat_id: int) -> None:
    mode = get_active_mode()
    user_states[user_id] = {"state": "awaiting_withdraw_input", "mode": mode}

    if mode == MODE_CODE:
        bot.send_message(chat_id, (
            "Chế độ rút hiện tại: <b>CODE</b>\n\n"
            "Vui lòng nhập số tiền muốn rút.\n"
            "Ví dụ: 100000"
        ), reply_markup=build_main_menu(user_id in admins))
    elif mode == MODE_STK:
        bot.send_message(chat_id, (
            "Chế độ rút hiện tại: <b>STK</b>\n\n"
            "Nhập theo mẫu:\n"
            "<code>số tiền - số tài khoản - tên người nhận - tên ngân hàng</code>\n"
            "Ví dụ: 150000 - 0123456789 - Nguyen Van A - Vietcombank"
        ), reply_markup=build_main_menu(user_id in admins))
    elif mode == MODE_NHAN_VAT:
        bot.send_message(chat_id, (
            "Chế độ rút hiện tại: <b>TÊN NHÂN VẬT</b>\n\n"
            "Nhập theo mẫu:\n"
            "<code>số tiền - tên nhân vật</code>\n"
            "Ví dụ: 200000 - AChiChi"
        ), reply_markup=build_main_menu(user_id in admins))
    else:
        bot.send_message(chat_id, "Chế độ rút không hợp lệ. Liên hệ admin.")
        user_states.pop(user_id, None)


def _handle_withdraw_input(user_id: int, chat_id: int, mode: str, text: str) -> None:
    initialize_user(user_id)

    if mode == MODE_CODE:
        amount = parse_amount(text)
        if not amount or amount <= 0:
            bot.send_message(chat_id, "Số tiền không hợp lệ. Vui lòng nhập lại (ví dụ: 100000)")
            return
        request = {
            "user_id": user_id,
            "type": MODE_CODE,
            "amount": amount,
            "details": {},
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }
        _append_pending(request)
        user_states.pop(user_id, None)
        bot.send_message(chat_id, (
            f"Đã gửi yêu cầu rút <b>CODE</b> số tiền <b>{format_currency(amount)}</b>.\n"
            f"Mã duyệt: <code>{_make_approval_id(user_id, MODE_CODE, amount)}</code>\n"
            "Vui lòng chờ admin duyệt."
        ))
        _notify_admins_new_request(request)
        return

    if mode == MODE_STK:
        parts = [p.strip() for p in text.split("-")]
        if len(parts) < 4:
            bot.send_message(chat_id, "Định dạng không đúng. Mẫu: số tiền - số tài khoản - tên người nhận - tên ngân hàng")
            return
        amount = parse_amount(parts[0])
        so_tai_khoan = parts[1]
        ten_nguoi_nhan = parts[2]
        ten_ngan_hang = parts[3]
        if not amount or amount <= 0:
            bot.send_message(chat_id, "Số tiền không hợp lệ. Vui lòng nhập lại.")
            return
        request = {
            "user_id": user_id,
            "type": MODE_STK,
            "amount": amount,
            "details": {
                "so_tai_khoan": so_tai_khoan,
                "ten_nguoi_nhan": ten_nguoi_nhan,
                "ten_ngan_hang": ten_ngan_hang,
            },
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }
        _append_pending(request)
        user_states.pop(user_id, None)
        bot.send_message(chat_id, (
            f"Đã gửi yêu cầu rút <b>STK</b> số tiền <b>{format_currency(amount)}</b>.\n"
            f"Mã duyệt: <code>{_make_approval_id(user_id, MODE_STK, amount)}</code>\n"
            "Vui lòng chờ admin duyệt."
        ))
        _notify_admins_new_request(request)
        return

    if mode == MODE_NHAN_VAT:
        parts = [p.strip() for p in text.split("-")]
        if len(parts) < 2:
            bot.send_message(chat_id, "Định dạng không đúng. Mẫu: số tiền - tên nhân vật")
            return
        amount = parse_amount(parts[0])
        ten_nhan_vat = parts[1]
        if not amount or amount <= 0:
            bot.send_message(chat_id, "Số tiền không hợp lệ. Vui lòng nhập lại.")
            return
        request = {
            "user_id": user_id,
            "type": MODE_NHAN_VAT,
            "amount": amount,
            "details": {
                "ten_nhan_vat": ten_nhan_vat,
            },
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }
        _append_pending(request)
        user_states.pop(user_id, None)
        bot.send_message(chat_id, (
            f"Đã gửi yêu cầu rút <b>TÊN NHÂN VẬT</b> số tiền <b>{format_currency(amount)}</b>.\n"
            f"Mã duyệt: <code>{_make_approval_id(user_id, MODE_NHAN_VAT, amount)}</code>\n"
            "Vui lòng chờ admin duyệt."
        ))
        _notify_admins_new_request(request)
        return

    bot.send_message(chat_id, "Chế độ rút không hợp lệ. Liên hệ admin.")
    user_states.pop(user_id, None)


def _notify_admins_new_request(request: Dict[str, Any]) -> None:
    uid = request.get("user_id")
    mode = request.get("type")
    amount = int(request.get("amount", 0))
    approval_id = _make_approval_id(uid, mode, amount)
    details = request.get("details", {})

    detail_lines: List[str] = []
    if mode == MODE_STK:
        detail_lines.append(f"STK: {details.get('so_tai_khoan','')}")
        detail_lines.append(f"Tên: {details.get('ten_nguoi_nhan','')}")
        detail_lines.append(f"Ngân hàng: {details.get('ten_ngan_hang','')}")
    elif mode == MODE_NHAN_VAT:
        detail_lines.append(f"Nhân vật: {details.get('ten_nhan_vat','')}")

    text = (
        "📥 Yêu cầu rút tiền mới\n"
        f"• User: <code>{uid}</code>\n"
        f"• Loại: <b>{mode}</b>\n"
        f"• Số tiền: <b>{format_currency(amount)}</b>\n"
        + ("• " + " | ".join(detail_lines) + "\n" if detail_lines else "")
        + f"• ID duyệt: <code>{approval_id}</code>\n\n"
        "Duyệt: <code>DUYET userID:type:amount</code>\n"
        "Huỷ: <code>HUY userID:type:amount</code>"
    )
    for admin_id in admins:
        try:
            bot.send_message(admin_id, text)
        except Exception:
            pass


def _handle_list_pending(chat_id: int) -> None:
    items = list_pending_requests()
    if not items:
        bot.send_message(chat_id, "Hiện không có yêu cầu chờ duyệt.")
        return

    lines: List[str] = ["Danh sách yêu cầu chờ duyệt:"]
    for it in items:
        uid = it.get("user_id")
        mode = it.get("type")
        amount = int(it.get("amount", 0))
        approval_id = _make_approval_id(uid, mode, amount)
        lines.append(f"- <code>{approval_id}</code>")
    lines.append("\nNhập: <code>DUYET userID:type:amount</code> hoặc <code>HUY userID:type:amount</code>")

    bot.send_message(chat_id, "\n".join(lines))


def _handle_admin_approval_action(admin_user_id: int, chat_id: int, action: str, id_str: str) -> None:
    found = find_pending_by_id_str(id_str)
    if not found:
        bot.send_message(chat_id, "Không tìm thấy yêu cầu đang chờ với ID đã nhập.")
        return

    idx, item = found
    items = _load_json(WITHDRAW_PENDING_FILE, [])

    uid = item.get("user_id")
    mode = item.get("type")
    amount = int(item.get("amount", 0))

    if action == "DUYET":
        # Deduct balance on approval
        if subtract_user_balance(uid, amount):
            item["status"] = "approved"
            item["approved_at"] = datetime.utcnow().isoformat()
            item["approved_by"] = admin_user_id
            items[idx] = item
            _save_pending_list(items)

            log_entry = {
                "time": datetime.utcnow().isoformat(),
                "user_id": uid,
                "amount": amount,
                "type": mode,
                "action": "approved",
                "admin_id": admin_user_id,
            }
            _append_log(log_entry)

            bot.send_message(chat_id, f"Đã duyệt yêu cầu: <code>{id_str}</code>. Số dư đã được trừ.")
            try:
                bot.send_message(uid, (
                    f"✅ Yêu cầu rút tiền <b>{mode}</b> số tiền <b>{format_currency(amount)}</b> đã được duyệt."
                ))
            except Exception:
                pass
        else:
            # Reject due to insufficient funds
            item["status"] = "rejected"
            item["rejected_at"] = datetime.utcnow().isoformat()
            item["rejected_by"] = admin_user_id
            item["reason"] = "insufficient_balance"
            items[idx] = item
            _save_pending_list(items)

            log_entry = {
                "time": datetime.utcnow().isoformat(),
                "user_id": uid,
                "amount": amount,
                "type": mode,
                "action": "rejected",
                "admin_id": admin_user_id,
                "reason": "insufficient_balance",
            }
            _append_log(log_entry)

            bot.send_message(chat_id, f"Không đủ số dư để duyệt yêu cầu <code>{id_str}</code>. Yêu cầu đã bị từ chối.")
            try:
                bot.send_message(uid, (
                    f"❌ Yêu cầu rút tiền <b>{mode}</b> số tiền <b>{format_currency(amount)}</b> đã bị từ chối do không đủ số dư."
                ))
            except Exception:
                pass
    elif action == "HUY":
        item["status"] = "rejected"
        item["rejected_at"] = datetime.utcnow().isoformat()
        item["rejected_by"] = admin_user_id
        items[idx] = item
        _save_pending_list(items)

        log_entry = {
            "time": datetime.utcnow().isoformat(),
            "user_id": uid,
            "amount": amount,
            "type": mode,
            "action": "rejected",
            "admin_id": admin_user_id,
            "reason": "admin_cancelled",
        }
        _append_log(log_entry)

        bot.send_message(chat_id, f"Đã huỷ yêu cầu: <code>{id_str}</code>.")
        try:
            bot.send_message(uid, (
                f"❌ Yêu cầu rút tiền <b>{mode}</b> số tiền <b>{format_currency(amount)}</b> đã bị từ chối."
            ))
        except Exception:
            pass
    else:
        bot.send_message(chat_id, "Hành động không hợp lệ. Dùng DUYET hoặc HUY.")


# =========================
# Bot runner
# =========================
if __name__ == "__main__":
    print("Bot is running... (Reply Keyboard only)")
    # Avoid long polling configuration errors in some environments
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
