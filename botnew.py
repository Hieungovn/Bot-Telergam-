# -*- coding: utf-8 -*-
import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

import telebot
from telebot import types

# =============================
# Configuration & Constants
# =============================
API_TOKEN = os.getenv('BOT_TOKEN') or os.getenv('API_TOKEN') or 'REPLACE_WITH_YOUR_TOKEN'

CONFIG_FILE = 'config.json'
WITHDRAW_PENDING_FILE = 'withdraw_pending.json'
WITHDRAW_LOGS_FILE = 'withdraw_logs.json'
USER_DATA_FILE = 'userdata.json'

# Supported modes
MODE_CODE = 'CODE'       # 🎁 Rút CODE
MODE_STK = 'STK'         # 💳 Rút STK
MODE_NHANVAT = 'NHANVAT' # 🧙 Rút TÊN NHÂN VẬT
SUPPORTED_MODES = {MODE_CODE, MODE_STK, MODE_NHANVAT}

# Admin list (keep or update as needed)
admins = [5627516174, 7205961265]

# Global bot
bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')

# =============================
# Storage helpers
# =============================

def _load_json(path: str, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path: str, data: Any) -> None:
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =============================
# User data helpers (required by spec)
# =============================
user_data: Dict[str, Dict[str, Any]] = _load_json(USER_DATA_FILE, {})


def initialize_user(user_id: int) -> None:
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {
            'balance': 0,
            'referrals': []
        }
        save_user_data(user_data)


def save_user_data(data: Dict[str, Dict[str, Any]]) -> None:
    _save_json(USER_DATA_FILE, data)


def get_user_balance(user_id: int) -> int:
    initialize_user(user_id)
    return int(user_data[str(user_id)].get('balance', 0))


def update_user_balance(user_id: int, amount_delta: int) -> None:
    initialize_user(user_id)
    user_data[str(user_id)]['balance'] = int(user_data[str(user_id)].get('balance', 0)) + int(amount_delta)
    save_user_data(user_data)


# =============================
# Withdraw config & persistence
# =============================

def load_config() -> Dict[str, Any]:
    cfg = _load_json(CONFIG_FILE, {})
    if 'active_withdraw_mode' not in cfg or cfg['active_withdraw_mode'] not in SUPPORTED_MODES:
        cfg['active_withdraw_mode'] = MODE_CODE
        save_config(cfg)
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    _save_json(CONFIG_FILE, cfg)


def load_pending() -> List[Dict[str, Any]]:
    return _load_json(WITHDRAW_PENDING_FILE, [])


def save_pending(items: List[Dict[str, Any]]) -> None:
    _save_json(WITHDRAW_PENDING_FILE, items)


def append_log(entry: Dict[str, Any]) -> None:
    logs = _load_json(WITHDRAW_LOGS_FILE, [])
    logs.append(entry)
    _save_json(WITHDRAW_LOGS_FILE, logs)


# =============================
# UI helpers (Reply Keyboard only)
# =============================

def main_keyboard_for(user_id: int) -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton('💸 Rút tiền'))
    if user_id in admins:
        markup.add(
            types.KeyboardButton('⚙️ Cấu hình rút tiền'),
            types.KeyboardButton('📋 Duyệt rút tiền')
        )
    return markup


def mode_to_label(mode: str) -> str:
    if mode == MODE_CODE:
        return '🎁 Rút CODE'
    if mode == MODE_STK:
        return '💳 Rút STK'
    if mode == MODE_NHANVAT:
        return '🧙 Rút TÊN NHÂN VẬT'
    return mode


def config_keyboard() -> types.ReplyKeyboardMarkup:
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(
        types.KeyboardButton('🎁 Rút CODE'),
        types.KeyboardButton('💳 Rút STK'),
        types.KeyboardButton('🧙 Rút TÊN NHÂN VẬT'),
        types.KeyboardButton('🔙 Quay lại')
    )
    return markup


# =============================
# Conversation state
# =============================
# Simple in-memory state per-user. Production code should persist if needed.
user_states: Dict[int, Dict[str, Any]] = {}


def set_state(user_id: int, key: str, value: Any) -> None:
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id][key] = value


def get_state(user_id: int, key: str, default=None) -> Any:
    return user_states.get(user_id, {}).get(key, default)


def clear_state(user_id: int) -> None:
    user_states[user_id] = {}


# =============================
# Utility parsing
# =============================

def parse_amount(text: str) -> int:
    cleaned = ''.join(ch for ch in text if ch.isdigit())
    if not cleaned:
        raise ValueError('Số tiền không hợp lệ')
    amount = int(cleaned)
    if amount <= 0:
        raise ValueError('Số tiền phải lớn hơn 0')
    return amount


def parse_withdraw_input(text: str, mode: str) -> Tuple[int, Dict[str, Any]]:
    # Normalize dash variants
    normalized = text.replace('—', '-').replace('–', '-')
    parts = [p.strip() for p in normalized.split('-')]

    if mode == MODE_CODE:
        # Only amount
        amount = parse_amount(parts[0] if parts else '')
        return amount, {}

    if mode == MODE_STK:
        # amount - account_no - receiver_name - bank_name
        if len(parts) < 4:
            raise ValueError('Vui lòng nhập theo mẫu: số tiền - số tài khoản - tên người nhận - tên ngân hàng')
        amount = parse_amount(parts[0])
        details = {
            'account_number': parts[1],
            'receiver_name': parts[2],
            'bank_name': parts[3]
        }
        return amount, details

    if mode == MODE_NHANVAT:
        # amount - character_name
        if len(parts) < 2:
            raise ValueError('Vui lòng nhập theo mẫu: số tiền - tên nhân vật')
        amount = parse_amount(parts[0])
        details = {
            'character_name': parts[1]
        }
        return amount, details

    raise ValueError('Chế độ rút tiền không hợp lệ')


def build_request_id(user_id: int, mode: str, amount: int) -> str:
    return f"{user_id}:{mode}:{amount}"


# =============================
# Core features
# =============================

def create_pending_withdraw(user_id: int, mode: str, amount: int, details: Dict[str, Any]) -> Dict[str, Any]:
    pending = load_pending()
    req_id = build_request_id(user_id, mode, amount)
    entry = {
        'id': req_id,
        'user_id': user_id,
        'mode': mode,
        'amount': amount,
        'details': details,
        'status': 'pending',
        'created_at': datetime.utcnow().isoformat() + 'Z'
    }
    pending.append(entry)
    save_pending(pending)
    return entry


def list_pending_summary() -> str:
    pending = load_pending()
    if not pending:
        return 'Hiện không có yêu cầu rút tiền nào đang chờ duyệt.'

    lines: List[str] = ['Danh sách yêu cầu chờ duyệt:']
    for item in pending:
        if item.get('status') != 'pending':
            continue
        uid = item.get('user_id')
        mode = item.get('mode')
        amount = item.get('amount')
        rid = item.get('id')  # should be userID:mode:amount
        lines.append(f"- User: <code>{uid}</code>, Loại: <b>{mode}</b>, Số tiền: <b>{amount}</b>, ID: <code>{rid}</code>")
    if len(lines) == 1:
        return 'Hiện không có yêu cầu rút tiền nào đang chờ duyệt.'

    lines.append('\nNhập:')
    lines.append('DUYET userID:TYPE:AMOUNT')
    lines.append('HUY userID:TYPE:AMOUNT')
    return '\n'.join(lines)


def find_pending_by_id(request_id: str) -> Optional[Dict[str, Any]]:
    pending = load_pending()
    for item in pending:
        if item.get('id') == request_id and item.get('status') == 'pending':
            return item
    return None


def update_pending_status(request_id: str, new_status: str, moderator_id: int) -> Optional[Dict[str, Any]]:
    pending = load_pending()
    updated: Optional[Dict[str, Any]] = None
    for item in pending:
        if item.get('id') == request_id and item.get('status') == 'pending':
            item['status'] = new_status
            item['processed_at'] = datetime.utcnow().isoformat() + 'Z'
            item['moderated_by'] = moderator_id
            updated = item
            break
    if updated is not None:
        save_pending(pending)
    return updated


# =============================
# Handlers (Reply Keyboard only, no commands)
# =============================

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_all_text(message):
    user_id = message.from_user.id
    text = (message.text or '').strip()

    # Ensure user exists
    initialize_user(user_id)

    # Quick route for admin approve/reject commands (free-form)
    if user_id in admins and (text.upper().startswith('DUYET ') or text.upper().startswith('HUY ')):
        return handle_admin_review_action(message, text)

    # Navigation
    if text == '🔙 Quay lại':
        clear_state(user_id)
        return send_main_menu(message)

    # Entry points
    if text == '💸 Rút tiền':
        return handle_withdraw_entry(message)

    if user_id in admins and text == '⚙️ Cấu hình rút tiền':
        return handle_config_entry(message)

    if user_id in admins and text == '📋 Duyệt rút tiền':
        return handle_review_entry(message)

    # In-flow inputs
    if get_state(user_id, 'awaiting_withdraw_input', False):
        return handle_withdraw_input(message)

    if user_id in admins and get_state(user_id, 'awaiting_admin_mode_selection', False):
        return handle_mode_selection(message)

    if user_id in admins and get_state(user_id, 'awaiting_review_action', False):
        # Admin is reviewing; allow DUYET/HUY lines, otherwise reprint help
        return handle_review_entry(message)

    # Fallback: Always show main menu
    return send_main_menu(message)


# =============================
# User: Withdraw flow
# =============================

def handle_withdraw_entry(message):
    user_id = message.from_user.id
    cfg = load_config()
    active = cfg.get('active_withdraw_mode', MODE_CODE)

    set_state(user_id, 'awaiting_withdraw_input', True)
    set_state(user_id, 'mode', active)

    if active == MODE_CODE:
        guide = (
            'Chế độ hiện tại: <b>🎁 Rút CODE</b>\n'
            'Vui lòng nhập <b>số tiền</b> bạn muốn rút.'
        )
    elif active == MODE_STK:
        guide = (
            'Chế độ hiện tại: <b>💳 Rút STK</b>\n'
            'Vui lòng nhập theo mẫu:\n'
            '<code>số tiền - số tài khoản - tên người nhận - tên ngân hàng</code>'
        )
    else:  # MODE_NHANVAT
        guide = (
            'Chế độ hiện tại: <b>🧙 Rút TÊN NHÂN VẬT</b>\n'
            'Vui lòng nhập theo mẫu:\n'
            '<code>số tiền - tên nhân vật</code>'
        )

    bot.send_message(
        message.chat.id,
        f"{guide}\n\nLưu ý: Yêu cầu sẽ được lưu để admin duyệt.",
        reply_markup=main_keyboard_for(user_id)
    )


def handle_withdraw_input(message):
    user_id = message.from_user.id
    text = (message.text or '').strip()
    mode = get_state(user_id, 'mode', MODE_CODE)

    try:
        amount, details = parse_withdraw_input(text, mode)
    except ValueError as e:
        bot.send_message(message.chat.id, f"❌ {str(e)}", reply_markup=main_keyboard_for(user_id))
        return

    # Create pending request (no deduction yet)
    entry = create_pending_withdraw(user_id, mode, amount, details)

    clear_state(user_id)

    # Acknowledge to user
    bot.send_message(
        message.chat.id,
        (
            '✅ Yêu cầu rút tiền đã được ghi nhận.\n'
            f"• ID duyệt: <code>{entry['id']}</code>\n"
            f"• Loại: <b>{mode}</b>\n"
            f"• Số tiền: <b>{amount}</b>\n"
            'Vui lòng chờ admin duyệt.'
        ),
        reply_markup=main_keyboard_for(user_id)
    )


# =============================
# Admin: Configure active mode
# =============================

def handle_config_entry(message):
    user_id = message.from_user.id
    cfg = load_config()
    active = cfg.get('active_withdraw_mode', MODE_CODE)

    set_state(user_id, 'awaiting_admin_mode_selection', True)

    bot.send_message(
        message.chat.id,
        (
            '⚙️ Cấu hình rút tiền\n'
            f"• Chế độ đang hoạt động: <b>{mode_to_label(active)}</b>\n\n"
            'Chọn một chế độ để kích hoạt:'
        ),
        reply_markup=config_keyboard()
    )


def handle_mode_selection(message):
    user_id = message.from_user.id
    choice = (message.text or '').strip()
    mapping = {
        '🎁 Rút CODE': MODE_CODE,
        '💳 Rút STK': MODE_STK,
        '🧙 Rút TÊN NHÂN VẬT': MODE_NHANVAT,
    }

    if choice not in mapping:
        bot.send_message(message.chat.id, '❌ Vui lòng chọn một chế độ hợp lệ.', reply_markup=config_keyboard())
        return

    cfg = load_config()
    cfg['active_withdraw_mode'] = mapping[choice]
    save_config(cfg)

    clear_state(user_id)

    bot.send_message(
        message.chat.id,
        f"✅ Đã kích hoạt chế độ: <b>{choice}</b>",
        reply_markup=main_keyboard_for(user_id)
    )


# =============================
# Admin: Review & approve/reject
# =============================

def handle_review_entry(message):
    user_id = message.from_user.id
    set_state(user_id, 'awaiting_review_action', True)

    summary = list_pending_summary()
    bot.send_message(
        message.chat.id,
        summary,
        reply_markup=main_keyboard_for(user_id)
    )


def handle_admin_review_action(message, raw_text: str):
    user_id = message.from_user.id
    text = raw_text.strip()

    # Expected: DUYET userID:TYPE:AMOUNT or HUY userID:TYPE:AMOUNT
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        bot.send_message(message.chat.id, '❌ Cú pháp không hợp lệ.', reply_markup=main_keyboard_for(user_id))
        return

    action, request_id = parts[0].upper(), parts[1].strip()

    # Basic request_id validation
    try:
        uid_str, typ, amt_str = request_id.split(':', 2)
        _ = int(uid_str)
        _ = int(amt_str)
        if typ not in SUPPORTED_MODES:
            raise ValueError('invalid mode')
    except Exception:
        bot.send_message(message.chat.id, '❌ ID duyệt không hợp lệ. Định dạng: userID:TYPE:AMOUNT', reply_markup=main_keyboard_for(user_id))
        return

    item = find_pending_by_id(request_id)
    if not item:
        bot.send_message(message.chat.id, '❌ Không tìm thấy yêu cầu chờ duyệt khớp ID hoặc đã được xử lý.', reply_markup=main_keyboard_for(user_id))
        return

    if action == 'DUYET':
        # Deduct balance then mark approved
        target_user = int(item['user_id'])
        amount = int(item['amount'])
        current_balance = get_user_balance(target_user)
        if current_balance < amount:
            bot.send_message(message.chat.id, f"❌ Số dư của user {target_user} không đủ (hiện: {current_balance}).", reply_markup=main_keyboard_for(user_id))
            return

        update_pending_status(request_id, 'approved', user_id)
        update_user_balance(target_user, -amount)

        # Notify user
        bot.send_message(target_user, (
            '✅ Yêu cầu rút tiền của bạn đã được <b>duyệt</b>.\n'
            f"• ID: <code>{request_id}</code>\n"
            f"• Loại: <b>{item['mode']}</b>\n"
            f"• Số tiền: <b>{amount}</b>"
        ))

        # Log
        append_log({
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'action': 'approved',
            'moderator_id': user_id,
            'user_id': target_user,
            'mode': item['mode'],
            'amount': amount,
            'details': item.get('details', {})
        })

        bot.send_message(message.chat.id, '✅ Đã duyệt yêu cầu và trừ tiền người dùng.', reply_markup=main_keyboard_for(user_id))
        return

    if action == 'HUY':
        update_pending_status(request_id, 'rejected', user_id)

        # Notify user
        bot.send_message(item['user_id'], (
            '❌ Yêu cầu rút tiền của bạn đã bị <b>từ chối</b>.\n'
            f"• ID: <code>{request_id}</code>\n"
            f"• Loại: <b>{item['mode']}</b>\n"
            f"• Số tiền: <b>{item['amount']}</b>"
        ))

        # Log
        append_log({
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'action': 'rejected',
            'moderator_id': user_id,
            'user_id': item['user_id'],
            'mode': item['mode'],
            'amount': item['amount'],
            'details': item.get('details', {})
        })

        bot.send_message(message.chat.id, '✅ Đã hủy yêu cầu (không trừ tiền).', reply_markup=main_keyboard_for(user_id))
        return

    # Unknown action
    bot.send_message(message.chat.id, '❌ Hành động không hợp lệ. Dùng DUYET hoặc HUY.', reply_markup=main_keyboard_for(user_id))


# =============================
# Common helpers
# =============================

def send_main_menu(message):
    user_id = message.from_user.id
    cfg = load_config()
    active = cfg.get('active_withdraw_mode', MODE_CODE)
    kb = main_keyboard_for(user_id)

    bot.send_message(
        message.chat.id,
        (
            '👋 Chào bạn!\n'
            f"Chế độ rút tiền hiện tại: <b>{mode_to_label(active)}</b>\n\n"
            'Chọn chức năng bằng các nút bên dưới.'
        ),
        reply_markup=kb
    )


# =============================
# Entrypoint
# =============================
if __name__ == '__main__':
    # Ensure config and storage files exist with valid defaults
    _ = load_config()
    _ = load_pending()
    _save_json(WITHDRAW_LOGS_FILE, _load_json(WITHDRAW_LOGS_FILE, []))

    # Start polling
    bot.infinity_polling(skip_pending=True)
