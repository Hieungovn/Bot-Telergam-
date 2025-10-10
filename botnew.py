# -*- coding: utf-8 -*-
"""
Telegram Withdraw Bot (Reply Keyboard Only)
- Single main menu for users: "💸 Rút tiền"
- Admin sees extra: "⚙️ Cấu hình rút tiền", "📋 Duyệt rút tiền"
- 3 withdraw modes (one active at a time): CODE / STK / NHÂN VẬT
- User submits request following active mode format; request is stored as pending
- Admin reviews with plain text: DUYET userID:type:amount or HUY userID:type:amount
- On approval: deduct user balance and notify; on rejection: no deduction; both logged optionally

Notes:
- No inline buttons or slash-command controls; only Reply Keyboards are used for flow
- Uses existing helpers: initialize_user(), save_user_data(), user_data, admins
- JSON files: config.json, withdraw_pending.json, withdraw_logs.json, userdata.json
"""

import os
import json
from datetime import datetime
from typing import Any, Dict, List

import telebot
from telebot import types
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# ========= Configuration =========
API_TOKEN = os.getenv('TELEGRAM_API_TOKEN', '8233954383:AAG9eY8I1rKcF-4IiltEvowkcTf13S6RCTo')
bot = telebot.TeleBot(API_TOKEN, parse_mode=None)

CONFIG_FILE = 'config.json'
PENDING_FILE = 'withdraw_pending.json'
LOG_FILE = 'withdraw_logs.json'
USER_DATA_FILE = 'userdata.json'

# Buttons
BTN_WITHDRAW = '💸 Rút tiền'
BTN_CONFIG = '⚙️ Cấu hình rút tiền'
BTN_REVIEW = '📋 Duyệt rút tiền'
BTN_BACK = '🔙 Quay lại'

# Mode labels
MODE_CODE = 'CODE'
MODE_STK = 'STK'
MODE_NHANVAT = 'NHANVAT'
MODE_LABEL_TO_CODE = {
    '🎁 Rút CODE': MODE_CODE,
    '💳 Rút STK': MODE_STK,
    '🧙 Rút TÊN NHÂN VẬT': MODE_NHANVAT,
}

# ========= Admin list and user data =========
# IMPORTANT: Keep these names to satisfy the requirement
admins = [5627516174, 7205961265]
user_data: Dict[str, Dict[str, Any]] = {}

# ========= Utilities for JSON storage =========

def load_json(path: str, default: Any) -> Any:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: str, data: Any) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ========= Existing helper functions (kept) =========

def initialize_user(user_id: int) -> None:
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {
            'balance': 0,
        }
        save_user_data(user_data)


def save_user_data(user_data_obj: Dict[str, Dict[str, Any]]) -> None:
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as file:
        json.dump(user_data_obj, file, ensure_ascii=False, indent=2)


# ========= Load boot data =========
user_data = load_json(USER_DATA_FILE, {})
config = load_json(CONFIG_FILE, {"active_withdraw_mode": MODE_CODE})
pending_requests: List[Dict[str, Any]] = load_json(PENDING_FILE, [])
withdraw_logs: List[Dict[str, Any]] = load_json(LOG_FILE, [])


# ========= Small helpers =========

def is_admin(user_id: int) -> bool:
    return user_id in admins


def get_active_mode() -> str:
    mode = config.get('active_withdraw_mode', MODE_CODE)
    if mode not in (MODE_CODE, MODE_STK, MODE_NHANVAT):
        mode = MODE_CODE
    return mode


def set_active_mode(mode: str) -> None:
    config['active_withdraw_mode'] = mode
    save_json(CONFIG_FILE, config)


def get_balance(user_id: int) -> int:
    initialize_user(user_id)
    return int(user_data.get(str(user_id), {}).get('balance', 0))


def deduct_balance(user_id: int, amount: int) -> bool:
    """Deduct amount safely. Returns True if success, False if insufficient funds."""
    initialize_user(user_id)
    user_id_str = str(user_id)
    current = int(user_data[user_id_str].get('balance', 0))
    if amount <= 0:
        return False
    if current < amount:
        return False
    user_data[user_id_str]['balance'] = current - amount
    save_user_data(user_data)
    return True


def next_iso_timestamp() -> str:
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def build_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if is_admin(user_id):
        mk.add(KeyboardButton(BTN_WITHDRAW))
        mk.add(KeyboardButton(BTN_CONFIG), KeyboardButton(BTN_REVIEW))
    else:
        mk.add(KeyboardButton(BTN_WITHDRAW))
    return mk


def build_config_keyboard() -> ReplyKeyboardMarkup:
    mk = types.ReplyKeyboardMarkup(resize_keyboard=True)
    mk.add(KeyboardButton('🎁 Rút CODE'))
    mk.add(KeyboardButton('💳 Rút STK'))
    mk.add(KeyboardButton('🧙 Rút TÊN NHÂN VẬT'))
    mk.add(KeyboardButton(BTN_BACK))
    return mk


# ========= State management for per-user flows =========
user_states: Dict[str, Dict[str, Any]] = {}


def set_user_state(user_id: int, key: str, value: Any) -> None:
    state = user_states.setdefault(str(user_id), {})
    state[key] = value


def get_user_state(user_id: int, key: str, default: Any = None) -> Any:
    return user_states.get(str(user_id), {}).get(key, default)


def clear_user_state(user_id: int) -> None:
    user_states.pop(str(user_id), None)


# ========= Formatting helpers =========

def format_withdraw_instructions(mode: str) -> str:
    if mode == MODE_CODE:
        return (
            '🎁 Chế độ hiện tại: Rút CODE\n'
            'Nhập số tiền muốn rút (chỉ số):\n'
            'VD: 50000'
        )
    if mode == MODE_STK:
        return (
            '💳 Chế độ hiện tại: Rút STK\n'
            'Nhập theo mẫu: số tiền - số tài khoản - tên người nhận - tên ngân hàng\n'
            'VD: 200000 - 0123456789 - Nguyen Van A - ACB'
        )
    if mode == MODE_NHANVAT:
        return (
            '🧙 Chế độ hiện tại: Rút TÊN NHÂN VẬT\n'
            'Nhập theo mẫu: số tiền - tên nhân vật\n'
            'VD: 150000 - Songoku'
        )
    return 'Chế độ rút tiền chưa được cấu hình.'


def make_request_id(user_id: int, mode: str, amount: int) -> str:
    return f"{user_id}:{mode}:{amount}"


# ========= Persist helpers for withdraws =========

def add_pending_request(req: Dict[str, Any]) -> None:
    pending_requests.append(req)
    save_json(PENDING_FILE, pending_requests)


def find_pending_request_by_id(request_id: str) -> Dict[str, Any] | None:
    for r in pending_requests:
        if r.get('status') == 'pending' and make_request_id(r['user_id'], r['type'], int(r['amount'])) == request_id:
            return r
    return None


def list_pending_requests() -> List[Dict[str, Any]]:
    return [r for r in pending_requests if r.get('status') == 'pending']


def update_request(req: Dict[str, Any], status: str) -> None:
    req['status'] = status
    save_json(PENDING_FILE, pending_requests)


def log_withdraw(action: str, user_id: int, amount: int, wtype: str, admin_id: int | None = None, reason: str | None = None) -> None:
    entry = {
        'time': next_iso_timestamp(),
        'action': action,  # 'approved' or 'rejected' or 'created'
        'user_id': user_id,
        'amount': int(amount),
        'type': wtype,
        'admin_id': admin_id,
        'reason': reason,
    }
    withdraw_logs.append(entry)
    save_json(LOG_FILE, withdraw_logs)


# ========= Message handlers =========

@bot.message_handler(commands=['start'])
def handle_start(message: types.Message) -> None:
    user_id = message.from_user.id
    initialize_user(user_id)
    mk = build_main_keyboard(user_id)
    bot.send_message(message.chat.id, 'Chào bạn! Hãy chọn chức năng.', reply_markup=mk)


@bot.message_handler(func=lambda m: m.text == BTN_WITHDRAW)
def handle_user_withdraw_entry(message: types.Message) -> None:
    user_id = message.from_user.id
    mk = build_main_keyboard(user_id)

    mode = get_active_mode()
    set_user_state(user_id, 'awaiting', 'withdraw_input')
    set_user_state(user_id, 'mode', mode)

    bot.send_message(
        message.chat.id,
        format_withdraw_instructions(mode) + f"\n\nLưu ý: yêu cầu sẽ được lưu chờ duyệt.",
        reply_markup=mk,
    )


@bot.message_handler(func=lambda m: m.text == BTN_CONFIG)
def handle_admin_config(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        bot.reply_to(message, '❌ Bạn không có quyền truy cập.')
        return
    mk = build_config_keyboard()
    current = get_active_mode()
    bot.send_message(message.chat.id, f'⚙️ Cấu hình rút tiền\nChế độ đang bật: {current}', reply_markup=mk)


@bot.message_handler(func=lambda m: m.text in MODE_LABEL_TO_CODE.keys())
def handle_admin_mode_select(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        bot.reply_to(message, '❌ Bạn không có quyền truy cập.')
        return
    mode = MODE_LABEL_TO_CODE[message.text]
    set_active_mode(mode)
    bot.send_message(message.chat.id, f'✅ Đã bật chế độ rút: {mode}', reply_markup=build_main_keyboard(message.from_user.id))


@bot.message_handler(func=lambda m: m.text == BTN_REVIEW)
def handle_admin_review(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        bot.reply_to(message, '❌ Bạn không có quyền truy cập.')
        return

    pendings = list_pending_requests()
    if not pendings:
        bot.send_message(message.chat.id, '📋 Hiện không có yêu cầu chờ duyệt.', reply_markup=build_main_keyboard(message.from_user.id))
        return

    lines = ['📋 Danh sách yêu cầu chờ duyệt:']
    for r in pendings:
        rid = make_request_id(r['user_id'], r['type'], int(r['amount']))
        lines.append(f"- ID: {rid} | user: {r['user_id']} | loại: {r['type']} | số tiền: {r['amount']}")
    lines.append('—')
    lines.append('Nhập: DUYET userID:type:amount hoặc HUY userID:type:amount')

    bot.send_message(message.chat.id, '\n'.join(lines), reply_markup=build_main_keyboard(message.from_user.id))


@bot.message_handler(func=lambda m: isinstance(m.text, str) and (m.text.strip().upper().startswith('DUYET ') or m.text.strip().upper().startswith('HUY ')))
def handle_admin_approve_or_reject(message: types.Message) -> None:
    if not is_admin(message.from_user.id):
        return

    text = message.text.strip()
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        bot.reply_to(message, 'Cú pháp không hợp lệ.')
        return

    action = parts[0].upper()  # DUYET or HUY
    rid = parts[1].strip()

    # Validate format userID:type:amount
    try:
        uid_str, type_str, amt_str = rid.split(':')
        uid = int(uid_str)
        amt = int(amt_str)
        type_upper = type_str.upper()
        if type_upper not in (MODE_CODE, MODE_STK, MODE_NHANVAT):
            raise ValueError('invalid type')
    except Exception:
        bot.reply_to(message, 'ID không hợp lệ. Định dạng: userID:type:amount')
        return

    req = find_pending_request_by_id(f"{uid}:{type_upper}:{amt}")
    if not req:
        bot.reply_to(message, '❌ Không tìm thấy yêu cầu phù hợp hoặc đã được xử lý.')
        return

    if action == 'DUYET':
        # Deduct balance and approve
        if not deduct_balance(uid, amt):
            update_request(req, 'rejected')
            log_withdraw('rejected', uid, amt, type_upper, admin_id=message.from_user.id, reason='insufficient_balance')
            bot.reply_to(message, '❌ Người dùng không đủ số dư. Yêu cầu đã bị từ chối.')
            try:
                bot.send_message(uid, f'❌ Yêu cầu rút {amt} ({type_upper}) đã bị từ chối do không đủ số dư.')
            except Exception:
                pass
            return

        update_request(req, 'approved')
        log_withdraw('approved', uid, amt, type_upper, admin_id=message.from_user.id)
        bot.reply_to(message, f'✅ Đã duyệt yêu cầu {rid}. Đã trừ {amt} khỏi số dư của user {uid}.')
        try:
            bot.send_message(uid, f'✅ Yêu cầu rút {amt} ({type_upper}) của bạn đã được duyệt. Vui lòng chờ xử lý tiếp theo nếu cần.')
        except Exception:
            pass
    else:  # HUY
        update_request(req, 'rejected')
        log_withdraw('rejected', uid, amt, type_upper, admin_id=message.from_user.id, reason='admin_cancel')
        bot.reply_to(message, f'🚫 Đã hủy yêu cầu {rid}. Không trừ tiền.')
        try:
            bot.send_message(uid, f'🚫 Yêu cầu rút {amt} ({type_upper}) của bạn đã bị từ chối.')
        except Exception:
            pass


@bot.message_handler(func=lambda m: True)
def handle_all_text(message: types.Message) -> None:
    user_id = message.from_user.id
    text = (message.text or '').strip()

    # 1) If user is in withdraw input flow, try parse and create pending
    if get_user_state(user_id, 'awaiting') == 'withdraw_input':
        mode = get_user_state(user_id, 'mode')
        amt = None
        details: Dict[str, Any] = {}

        if mode == MODE_CODE:
            # Expect only integer amount
            try:
                amt = int(text.replace(',', '').replace('.', ''))
            except Exception:
                bot.reply_to(message, '❌ Vui lòng nhập số tiền hợp lệ. VD: 50000')
                return
            if amt <= 0:
                bot.reply_to(message, '❌ Số tiền phải lớn hơn 0.')
                return

        elif mode == MODE_STK:
            # Format: amount - account - receiver - bank
            parts = [p.strip() for p in text.split('-')]
            if len(parts) != 4:
                bot.reply_to(message, '❌ Sai định dạng. VD: 200000 - 0123456789 - Nguyen Van A - ACB')
                return
            try:
                amt = int(parts[0].replace(',', '').replace('.', ''))
            except Exception:
                bot.reply_to(message, '❌ Số tiền không hợp lệ.')
                return
            if amt <= 0:
                bot.reply_to(message, '❌ Số tiền phải lớn hơn 0.')
                return
            details = {
                'account_number': parts[1],
                'receiver_name': parts[2],
                'bank_name': parts[3],
            }

        elif mode == MODE_NHANVAT:
            # Format: amount - character name
            parts = [p.strip() for p in text.split('-')]
            if len(parts) != 2:
                bot.reply_to(message, '❌ Sai định dạng. VD: 150000 - Songoku')
                return
            try:
                amt = int(parts[0].replace(',', '').replace('.', ''))
            except Exception:
                bot.reply_to(message, '❌ Số tiền không hợp lệ.')
                return
            if amt <= 0:
                bot.reply_to(message, '❌ Số tiền phải lớn hơn 0.')
                return
            details = {
                'character_name': parts[1],
            }
        else:
            bot.reply_to(message, '❌ Chế độ rút tiền chưa được cấu hình.')
            clear_user_state(user_id)
            return

        # Save pending request
        req = {
            'user_id': user_id,
            'type': mode,
            'amount': int(amt),
            'details': details,
            'status': 'pending',
            'created_at': next_iso_timestamp(),
        }
        add_pending_request(req)
        log_withdraw('created', user_id, int(amt), mode)

        rid = make_request_id(user_id, mode, int(amt))
        bot.send_message(
            message.chat.id,
            f'📨 Đã gửi yêu cầu rút thành công!\nID: {rid}\nTrạng thái: pending. Vui lòng chờ admin duyệt.',
            reply_markup=build_main_keyboard(user_id),
        )
        clear_user_state(user_id)
        return

    # 2) Otherwise, show main menu again for any text
    bot.send_message(message.chat.id, 'Vui lòng chọn chức năng:', reply_markup=build_main_keyboard(user_id))


if __name__ == '__main__':
    # Start polling
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=20, skip_pending=True)
        except Exception as e:
            # Basic retry on network errors
            import time
            time.sleep(3)
