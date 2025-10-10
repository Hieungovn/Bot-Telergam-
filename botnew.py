# -*- coding: utf-8 -*-
"""
Telegram withdraw management bot (pyTelegramBotAPI) using ONLY Reply Keyboard.

Features:
- User main menu: [💸 Rút tiền]
- Admin main menu adds: [⚙️ Cấu hình rút tiền], [📋 Duyệt rút tiền]
- Single active withdraw mode stored in config.json: CODE / STK / NHANVAT
- Users submit withdraw request according to active mode; request is stored to withdraw_pending.json with status "pending"
- Admin reviews pending list and approves/rejects by typing: DUYET userID:type:amount or HUY userID:type:amount
- On approve: bot deducts user balance and notifies; status -> "approved"
- On reject: no deduction; status -> "rejected"
- Optional logging to withdraw_logs.json on approve/reject

This file defines and uses: initialize_user(), save_user_data(), user_data, admins.
No /commands or InlineKeyboard are used anywhere; everything is via Reply Keyboard.
"""
from __future__ import annotations

import os
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, Message

# ==============================
# Configuration and file paths
# ==============================
# Read token from env for safety; fall back to placeholder string
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_BOT_TOKEN:
    # As a last resort, you can set token here during local testing
    TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Admin list (use your existing admin IDs here)
admins: List[int] = [5627516174, 7205961265]

# Data files
CONFIG_FILE = "config.json"
WITHDRAW_PENDING_FILE = "withdraw_pending.json"
WITHDRAW_LOGS_FILE = "withdraw_logs.json"
user_data_file = "userdata.json"  # keep original name to match existing save_user_data signature

# Supported withdraw modes (exact labels used in admin selection menu)
MODE_CODE = "CODE"
MODE_STK = "STK"
MODE_NHANVAT = "NHANVAT"

ADMIN_BTN_CONFIG = "⚙️ Cấu hình rút tiền"
ADMIN_BTN_REVIEW = "📋 Duyệt rút tiền"
USER_BTN_WITHDRAW = "💸 Rút tiền"

ADMIN_SEL_CODE = "🎁 Rút CODE"
ADMIN_SEL_STK = "💳 Rút STK"
ADMIN_SEL_NHANVAT = "🧙 Rút TÊN NHÂN VẬT"
BTN_BACK = "⬅️ Quay lại"

# ==============================
# In-memory state
# ==============================
user_data: Dict[str, Dict[str, Any]] = {}
user_states: Dict[int, str] = {}  # per-user ephemeral state: "awaiting_withdraw", "choosing_mode"

# ==============================
# JSON helpers
# ==============================

def _load_json(path: str, default: Any) -> Any:
    try:
        if not os.path.exists(path):
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_currency(amount: int) -> str:
    try:
        return f"{amount:,}".replace(",", ".")
    except Exception:
        return str(amount)


# ==============================
# Required existing-like functions
# ==============================

def initialize_user(user_id: int) -> None:
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {
            "balance": 0
        }
        save_user_data(user_data)


def save_user_data(data: Dict[str, Dict[str, Any]]) -> None:
    _save_json(user_data_file, data)


# ==============================
# Config helpers (active withdraw mode)
# ==============================

def ensure_config_files() -> None:
    # config.json
    cfg = _load_json(CONFIG_FILE, {})
    if "active_withdraw_mode" not in cfg:
        cfg["active_withdraw_mode"] = MODE_CODE
        _save_json(CONFIG_FILE, cfg)
    # withdraw_pending.json
    pending = _load_json(WITHDRAW_PENDING_FILE, None)
    if pending is None or not isinstance(pending, list):
        _save_json(WITHDRAW_PENDING_FILE, [])
    # withdraw_logs.json
    logs = _load_json(WITHDRAW_LOGS_FILE, None)
    if logs is None or not isinstance(logs, list):
        _save_json(WITHDRAW_LOGS_FILE, [])


def get_active_mode() -> str:
    cfg = _load_json(CONFIG_FILE, {})
    mode = cfg.get("active_withdraw_mode", MODE_CODE)
    if mode not in (MODE_CODE, MODE_STK, MODE_NHANVAT):
        mode = MODE_CODE
    return mode


def set_active_mode(mode: str) -> None:
    cfg = _load_json(CONFIG_FILE, {})
    cfg["active_withdraw_mode"] = mode
    _save_json(CONFIG_FILE, cfg)


# ==============================
# Pending requests and logs
# ==============================

def _build_approval_id(user_id: int, mode: str, amount: int) -> str:
    return f"{user_id}:{mode}:{amount}"


def add_pending_withdraw(user_id: int, mode: str, amount: int, payload: Dict[str, Any]) -> str:
    approval_id = _build_approval_id(user_id, mode, amount)
    entry = {
        "user_id": user_id,
        "mode": mode,
        "amount": amount,
        "payload": payload,  # structured details depending on mode
        "status": "pending",
        "approval_id": approval_id,
        "created_at": _now_iso(),
    }
    pendings: List[Dict[str, Any]] = _load_json(WITHDRAW_PENDING_FILE, [])
    pendings.append(entry)
    _save_json(WITHDRAW_PENDING_FILE, pendings)
    return approval_id


def list_pending_brief() -> List[str]:
    pendings: List[Dict[str, Any]] = _load_json(WITHDRAW_PENDING_FILE, [])
    lines: List[str] = []
    for p in pendings:
        if p.get("status") == "pending":
            uid = p.get("user_id")
            mode = p.get("mode")
            amount = p.get("amount", 0)
            lines.append(f"{uid}:{mode}:{amount}")
    return lines


def find_first_pending_by_approval_id(approval_id: str) -> Optional[Dict[str, Any]]:
    pendings: List[Dict[str, Any]] = _load_json(WITHDRAW_PENDING_FILE, [])
    for p in pendings:
        if p.get("approval_id") == approval_id and p.get("status") == "pending":
            return p
    return None


def update_pending_status(approval_id: str, new_status: str) -> bool:
    pendings: List[Dict[str, Any]] = _load_json(WITHDRAW_PENDING_FILE, [])
    updated = False
    for p in pendings:
        if p.get("approval_id") == approval_id and p.get("status") in ("pending",):
            p["status"] = new_status
            if new_status == "approved":
                p["approved_at"] = _now_iso()
            elif new_status == "rejected":
                p["rejected_at"] = _now_iso()
            updated = True
            break
    if updated:
        _save_json(WITHDRAW_PENDING_FILE, pendings)
    return updated


def log_action(user_id: int, mode: str, amount: int, action: str, admin_id: Optional[int] = None, approval_id: Optional[str] = None) -> None:
    logs: List[Dict[str, Any]] = _load_json(WITHDRAW_LOGS_FILE, [])
    logs.append({
        "timestamp": _now_iso(),
        "user_id": user_id,
        "mode": mode,
        "amount": amount,
        "action": action,  # "approved" | "rejected"
        "admin_id": admin_id,
        "approval_id": approval_id,
    })
    _save_json(WITHDRAW_LOGS_FILE, logs)


# ==============================
# Keyboards
# ==============================

def is_admin(user_id: int) -> bool:
    return user_id in admins


def main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton(USER_BTN_WITHDRAW))
    if is_admin(user_id):
        kb.row(KeyboardButton(ADMIN_BTN_CONFIG), KeyboardButton(ADMIN_BTN_REVIEW))
    return kb


def config_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton(ADMIN_SEL_CODE), KeyboardButton(ADMIN_SEL_STK))
    kb.row(KeyboardButton(ADMIN_SEL_NHANVAT), KeyboardButton(BTN_BACK))
    return kb


# ==============================
# Parsing helpers
# ==============================

def _parse_amount(raw: str) -> Optional[int]:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    try:
        value = int(digits)
        if value <= 0:
            return None
        return value
    except Exception:
        return None


def parse_withdraw_input(mode: str, text: str) -> Tuple[Optional[int], Optional[Dict[str, Any]], Optional[str]]:
    """Return (amount, payload, error_message)."""
    text = text.strip()
    if mode == MODE_CODE:
        amount = _parse_amount(text)
        if amount is None:
            return None, None, "Vui lòng nhập một số tiền hợp lệ. Ví dụ: 100000"
        return amount, {}, None

    if mode == MODE_STK:
        parts = [p.strip() for p in text.split("-")]
        if len(parts) != 4:
            return None, None, "Sai mẫu. Nhập: số tiền - số tài khoản - tên người nhận - tên ngân hàng"
        amount = _parse_amount(parts[0])
        if amount is None:
            return None, None, "Số tiền không hợp lệ. Ví dụ: 250000"
        payload = {
            "account_number": parts[1],
            "recipient_name": parts[2],
            "bank_name": parts[3],
        }
        return amount, payload, None

    if mode == MODE_NHANVAT:
        parts = [p.strip() for p in text.split("-")]
        if len(parts) != 2:
            return None, None, "Sai mẫu. Nhập: số tiền - tên nhân vật"
        amount = _parse_amount(parts[0])
        if amount is None:
            return None, None, "Số tiền không hợp lệ. Ví dụ: 150000"
        payload = {
            "character_name": parts[1],
        }
        return amount, payload, None

    return None, None, "Chế độ rút không hợp lệ. Hãy báo admin."


# ==============================
# Messaging helpers
# ==============================

def send_main_menu(message: Message, extra: Optional[str] = None) -> None:
    uid = message.from_user.id
    active = get_active_mode()
    info = f"Chế độ rút hiện tại: {active}"
    text = info if extra is None else f"{extra}\n\n{info}"
    bot.send_message(uid, text, reply_markup=main_keyboard(uid))


def send_withdraw_prompt(message: Message) -> None:
    uid = message.from_user.id
    active = get_active_mode()
    if active == MODE_CODE:
        bot.send_message(uid, "Hãy nhập số tiền bạn muốn rút (VD: 100000).", reply_markup=main_keyboard(uid))
    elif active == MODE_STK:
        bot.send_message(uid, "Nhập theo mẫu: số tiền - số tài khoản - tên người nhận - tên ngân hàng\nVD: 250000 - 0123456789 - NGUYEN VAN A - VIETCOMBANK", reply_markup=main_keyboard(uid))
    elif active == MODE_NHANVAT:
        bot.send_message(uid, "Nhập theo mẫu: số tiền - tên nhân vật\nVD: 150000 - TenNhanVat", reply_markup=main_keyboard(uid))
    else:
        bot.send_message(uid, "Chế độ rút chưa được cấu hình hợp lệ. Hãy báo admin.", reply_markup=main_keyboard(uid))


def send_admin_pending_list(message: Message) -> None:
    uid = message.from_user.id
    items = list_pending_brief()
    if not items:
        bot.send_message(uid, "Không có yêu cầu chờ duyệt.", reply_markup=main_keyboard(uid))
        return

    # Send in chunks to avoid message length limits
    header = "Danh sách chờ duyệt (ID duyệt: userID:type:amount):"
    chunk: List[str] = []
    for i, row in enumerate(items, 1):
        chunk.append(f"{i}. {row}")
        if len(chunk) >= 25:
            bot.send_message(uid, f"{header}\n" + "\n".join(chunk))
            chunk = []
    if chunk:
        bot.send_message(uid, f"{header}\n" + "\n".join(chunk))

    bot.send_message(
        uid,
        "Nhập lệnh để xử lý:\n"
        "- DUYET userID:type:amount\n"
        "- HUY userID:type:amount",
        reply_markup=main_keyboard(uid),
    )


# ==============================
# Core handlers (no /commands)
# ==============================
@bot.message_handler(content_types=["text"])
def handle_text(message: Message) -> None:
    uid = message.from_user.id
    text = (message.text or "").strip()

    # Ensure user exists in storage
    initialize_user(uid)

    # Admin-only quick commands for review flow
    upper = text.upper()
    if is_admin(uid) and (upper.startswith("DUYET ") or upper.startswith("HUY ")):
        handle_admin_decision(message, upper)
        return

    # Main menu buttons
    if text == USER_BTN_WITHDRAW:
        user_states[uid] = "awaiting_withdraw"
        send_withdraw_prompt(message)
        return

    if is_admin(uid) and text == ADMIN_BTN_CONFIG:
        user_states[uid] = "choosing_mode"
        active = get_active_mode()
        bot.send_message(uid, f"Chọn chế độ rút đang hoạt động (hiện tại: {active}):", reply_markup=config_keyboard())
        return

    if is_admin(uid) and text == ADMIN_BTN_REVIEW:
        send_admin_pending_list(message)
        return

    # Admin choosing mode
    if user_states.get(uid) == "choosing_mode" and is_admin(uid):
        if text == ADMIN_SEL_CODE:
            set_active_mode(MODE_CODE)
            user_states.pop(uid, None)
            bot.send_message(uid, "Đã bật chế độ rút: CODE", reply_markup=main_keyboard(uid))
            return
        if text == ADMIN_SEL_STK:
            set_active_mode(MODE_STK)
            user_states.pop(uid, None)
            bot.send_message(uid, "Đã bật chế độ rút: STK", reply_markup=main_keyboard(uid))
            return
        if text == ADMIN_SEL_NHANVAT:
            set_active_mode(MODE_NHANVAT)
            user_states.pop(uid, None)
            bot.send_message(uid, "Đã bật chế độ rút: TÊN NHÂN VẬT", reply_markup=main_keyboard(uid))
            return
        if text == BTN_BACK:
            user_states.pop(uid, None)
            send_main_menu(message)
            return
        # If they typed anything else, re-show selection
        bot.send_message(uid, "Vui lòng chọn một chế độ rút từ các nút bên dưới.", reply_markup=config_keyboard())
        return

    # User submit withdraw details when awaiting
    if user_states.get(uid) == "awaiting_withdraw":
        mode = get_active_mode()
        amount, payload, err = parse_withdraw_input(mode, text)
        if err:
            bot.send_message(uid, err, reply_markup=main_keyboard(uid))
            return
        approval_id = add_pending_withdraw(uid, mode, amount or 0, payload or {})
        user_states.pop(uid, None)
        pretty_amount = _format_currency(amount or 0)
        note = ""
        if mode == MODE_STK:
            note = f"\nSTK: {payload.get('account_number')} | {payload.get('recipient_name')} | {payload.get('bank_name')}"
        elif mode == MODE_NHANVAT:
            note = f"\nNhân vật: {payload.get('character_name')}"
        bot.send_message(
            uid,
            f"Đã gửi yêu cầu rút {mode} số tiền {pretty_amount}đ.{note}\nMã duyệt: {approval_id}\nVui lòng chờ admin duyệt.",
            reply_markup=main_keyboard(uid),
        )
        return

    # Fallback: show main menu with current mode hint
    send_main_menu(message, extra="Chào bạn! Hãy chọn thao tác từ menu.")


# ==============================
# Admin decision handlers
# ==============================

def _parse_approval_from_command(text_upper: str) -> Optional[str]:
    # Expected: DUYET userID:type:amount or HUY userID:type:amount
    try:
        parts = text_upper.split(maxsplit=1)
        if len(parts) != 2:
            return None
        token = parts[1].strip()
        # Preserve original case for matching; the stored approval_id uses original values.
        # But amount digits are case-insensitive anyway; we need the exact stored fmt. We'll accept the exact string after the space.
        return token
    except Exception:
        return None


def handle_admin_decision(message: Message, text_upper: str) -> None:
    uid = message.from_user.id
    if not is_admin(uid):
        send_main_menu(message, extra="Bạn không có quyền thực hiện thao tác này.")
        return

    is_approve = text_upper.startswith("DUYET ")
    is_reject = text_upper.startswith("HUY ")
    approval_id_raw = _parse_approval_from_command(text_upper)
    if not approval_id_raw:
        bot.send_message(uid, "Cú pháp không đúng. VD: DUYET 123456:CODE:100000", reply_markup=main_keyboard(uid))
        return

    # Try to find pending entry by approval_id EXACT match
    approval_id_exact = approval_id_raw
    pending = find_first_pending_by_approval_id(approval_id_exact)

    # If not found, try tolerant rebuild (in case the admin typed with different case for mode)
    if not pending:
        # Try to reconstruct if shape looks like user:mode:amount
        try:
            parts = approval_id_raw.split(":")
            if len(parts) == 3:
                u_str, mode_str, amt_str = parts
                u_int = int(u_str)
                amt_int = int("".join(ch for ch in amt_str if ch.isdigit()))
                mode_norm = mode_str.upper()
                candidate = _build_approval_id(u_int, mode_norm, amt_int)
                pending = find_first_pending_by_approval_id(candidate)
                approval_id_exact = candidate if pending else approval_id_exact
        except Exception:
            pass

    if not pending:
        bot.send_message(uid, "Không tìm thấy yêu cầu chờ duyệt với mã đã nhập.", reply_markup=main_keyboard(uid))
        return

    target_user_id = int(pending.get("user_id"))
    mode = str(pending.get("mode"))
    amount = int(pending.get("amount", 0))

    if is_approve:
        # Deduct balance immediately
        target_user_id_str = str(target_user_id)
        initialize_user(target_user_id)
        user_data[target_user_id_str]["balance"] = user_data[target_user_id_str].get("balance", 0) - amount
        save_user_data(user_data)

        update_pending_status(approval_id_exact, "approved")
        log_action(target_user_id, mode, amount, "approved", admin_id=uid, approval_id=approval_id_exact)

        # Notify both sides
        bot.send_message(uid, f"ĐÃ DUYỆT: {approval_id_exact}")
        try:
            bot.send_message(target_user_id, f"Yêu cầu rút {mode} số tiền {_format_currency(amount)}đ đã được duyệt. Vui lòng chờ xử lý.")
        except Exception:
            pass
        return

    if is_reject:
        update_pending_status(approval_id_exact, "rejected")
        log_action(target_user_id, mode, amount, "rejected", admin_id=uid, approval_id=approval_id_exact)

        bot.send_message(uid, f"ĐÃ HỦY: {approval_id_exact}")
        try:
            bot.send_message(target_user_id, f"Yêu cầu rút {mode} số tiền {_format_currency(amount)}đ đã bị từ chối.")
        except Exception:
            pass
        return

    # Should not reach here
    bot.send_message(uid, "Cú pháp không đúng. Dùng DUYET hoặc HUY.", reply_markup=main_keyboard(uid))


# ==============================
# Startup
# ==============================

def _startup() -> None:
    global user_data
    ensure_config_files()
    # Load users
    user_data = _load_json(user_data_file, {})


_startup()

if __name__ == "__main__":
    # Long-polling run loop
    bot.infinity_polling(skip_pending=True)
