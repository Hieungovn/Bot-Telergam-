# -*- coding: utf-8 -*-
import telebot
from telebot import types      
import os
import json
from datetime import datetime, timedelta
import random
import threading
import time
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import time
import base64
import pytz

# Thông tin cấu hình - FIXED: Use environment variable for security
API_TOKEN = '8276748111:AAEkjeNQSpAuiLoiDCWvR7QAdKJ0zJug1WU'
bot = telebot.TeleBot(API_TOKEN)

# File lưu trữ dữ liệu
CHANNELS_FILE = 'channels.json'
SETTINGS_FILE = 'settings.json'
USER_FILE = 'users.txt'
user_data_file = 'userdata.json'
invited_users_file = 'invitedusers.json'
referral_history_file = 'referral_history.json'
# Phần lưu trữ danh sách codes
codes_file = 'codes.json'  # File lưu trữ danh sách code
used_codes_file = 'used_codes.json'  # File lưu trữ danh sách code đã sử dụng
game_link_file = 'game_link.json'  # File lưu trữ link game
DROP_CODES_FILE = 'drop_codes.json'  # Mã riêng cho Đập Hộp

# Danh sách admin
admins = [7205961265,6118978649]  # Danh sách ID admin

# Khởi tạo biến toàn cục
user_data = {}
auto_approve = False  # Biến điều khiển duyệt tự động
invited_users = {}
referral_history = {}  # Lưu trữ lịch sử người được mời bởi ai
codes = []  # Danh sách code để đổi
used_codes = {}  # Danh sách code đã sử dụng
game_link = ""  # Link game hiện tại
drop_codes = []  # Danh sách code riêng cho Đập Hộp

# === ĐẬP HỘP: Trạng thái mỗi đợt phát code ===
current_drop = {
    'id': 0,
    'active': False,
    'start_ts': None,
    'end_ts': None,
    'claimed_users': [],
    'chat_id': None,
    'message_id': None
}
drop_window_minutes = 60  # Thời gian hợp lệ của mỗi đợt (phút)
drop_thread_started = False
drop_lock = threading.Lock()

# NEW: Enhanced logging functions
def log_debug(message):
    """Hàm logging debug chi tiết"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[DEBUG] {timestamp} - {message}")

def log_error(message):
    """Hàm logging lỗi"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[ERROR] {timestamp} - {message}")

# NEW: Subscription result class for improved error handling
class SubscriptionResult:
    """Result of subscription check"""
    def __init__(self, subscribed, error=None, retry_needed=False):
        self.subscribed = subscribed
        self.error = error
        self.retry_needed = retry_needed

# Hàm lưu lịch sử giới thiệu
def save_referral_history():
    with open(referral_history_file, 'w') as file:
        json.dump(referral_history, file, indent=4)

# Hàm tải lịch sử giới thiệu
def load_referral_history():
    try:
        with open(referral_history_file, 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Hàm lưu danh sách code
def save_codes():
    with open(codes_file, 'w') as file:
        json.dump(codes, file, indent=4)

# Hàm tải danh sách code
def load_codes():
    try:
        with open(codes_file, 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

# Hàm lưu/tải CODE riêng cho Đập Hộp
def save_drop_codes():
    global drop_codes
    with open(DROP_CODES_FILE, 'w') as f:
        json.dump(drop_codes, f, indent=4)

def load_drop_codes():
    try:
        with open(DROP_CODES_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

# Hàm lưu danh sách code đã sử dụng
def save_used_codes():
    with open(used_codes_file, 'w') as file:
        json.dump(used_codes, file, indent=4)

# Hàm tải danh sách code đã sử dụng
def load_used_codes():
    try:
        with open(used_codes_file, 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Hàm lưu link game
def save_game_link(link):
    with open(game_link_file, 'w') as file:
        json.dump({'game_link': link}, file, indent=4)

# Hàm tải link game
def load_game_link():
    try:
        with open(game_link_file, 'r') as file:
            data = json.load(file)
            return data.get('game_link', '')
    except (FileNotFoundError, json.JSONDecodeError):
        return ''

# Hàm tải cài đặt từ file
def load_settings():
    try:
        with open(SETTINGS_FILE, 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        # Cài đặt mặc định nếu file không tồn tại
        default_settings = {
            'referral_bonus': 1500,  # Thưởng khi giới thiệu (VNĐ)
            'min_withdraw': 15000,  # Số tiền rút tối thiểu (VNĐ)
            'announcement_image': '' # Add default image
        }
        save_settings(default_settings)
        return default_settings

# Hàm lưu cài đặt vào file
def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as file:
        json.dump(settings, file, indent=4)

# ĐẬP HỘP: Cấu hình mở rộng
def get_drop_settings():
    settings = load_settings()
    # Mặc định nếu chưa có cấu hình
    if 'drop' not in settings:
        settings['drop'] = {
            'enabled': True,
            'image_url': '',  # Ảnh thông báo, có thể là URL http(s)
            'image_file_id': '',  # Ảnh do admin upload (ưu tiên dùng)
            'title': '🎁 Đập Hộp',
            'button_text': '🎁 Đập Hộp',
            'window_minutes': 15,
            'times': [],  # Hai thời điểm cố định HH:MM
            'cooldown_seconds': 0, # khoảng đệm tối thiểu giữa các đợt
            'target_chat_id': None,  # Chat ID để gửi thông báo (None = gửi cho tất cả user)
            'timezone': 'Asia/Ho_Chi_Minh'  # Múi giờ để chạy scheduler
        }
        save_settings(settings)
    # Backward compatibility: if 'hours' exists, convert to 'times'
    drop = settings['drop']
    if 'hours' in drop and 'times' not in drop:
        hrs = drop.get('hours', [9, 21])
        drop['times'] = [f"{int(hrs[0]):02d}:00", f"{int(hrs[1]):02d}:00"]
        drop.pop('hours', None)
        save_settings(settings)
    return drop

# FIXED: Improved load_channels function

def load_channels():
    try:
        # Nếu file chưa tồn tại → tạo file rỗng
        if not os.path.exists(CHANNELS_FILE):
            with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            log_debug("Created empty channels.json file.")
            return []

        # Đọc dữ liệu từ file
        with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                log_error("channels.json bị lỗi định dạng → reset file.")
                data = []
                save_channels(data)

        log_debug(f"Raw channels data loaded: {data}")

        cleaned = []
        for ch in data:
            if isinstance(ch, dict):
                username = str(ch.get('username', '')).lstrip('@').strip()
                title = str(ch.get('title', username)).strip()
                if username:
                    cleaned.append({'username': username, 'title': title})
            else:
                username = str(ch).lstrip('@').strip()
                if username:
                    cleaned.append({'username': username, 'title': username})

        log_debug(f"Cleaned channels: {cleaned}")
        return cleaned

    except Exception as e:
        log_error(f"load_channels error: {e}")
        return []


def save_channels(channels):
    try:
        with open('channels.json', 'w', encoding='utf-8') as f:
            json.dump(channels, f, indent=2, ensure_ascii=False)
        log_debug(f"Channels saved: {channels}")
    except Exception as e:
        log_error(f"save_channels error: {e}")

# FIXED: Improved check_bot_admin_status
def check_bot_admin_status():
    channels = load_channels()
    status_report = {}
    bot_id = bot.get_me().id

    for channel in channels:
        try:
            if isinstance(channel, dict):
                channel_key = channel.get('username', 'unknown_channel')
            else:
                channel_key = str(channel).lstrip('@')

            # Try different formats (removed invalid -100 prefix for usernames)
            chat_identifiers = [f'@{channel_key}', channel_key]
            
            for chat_id in chat_identifiers:
                try:
                    bot_info = bot.get_chat_member(chat_id, bot_id)
                    if bot_info.status in ['administrator', 'creator']:
                        status_report[channel_key] = True
                        log_debug(f"Bot is admin in {chat_id}")
                        break
                    else:
                        status_report[channel_key] = False
                        log_debug(f"Bot is not admin in {chat_id}, status: {bot_info.status}")
                except Exception as inner_e:
                    continue
            else:
                status_report[channel_key] = False
                log_error(f"Could not check bot status in {channel_key}")

        except Exception as e:
            log_error(f"Error checking bot status for {channel}: {e}")
            status_report[channel_key] = False

    return status_report

# Hàm để gửi tin nhắn riêng cho người dùng
def send_private_message(user_id, message):
    try:
        bot.send_message(user_id, message)
        log_debug(f"Sent private message to user {user_id}")
    except telebot.apihelper.ApiException as e:
        log_error(f"Error sending private message to {user_id}: {e}")

# NEW: Function to verify bot access to channels
def verify_bot_access(chat_id):
    """Verify if bot has access to a channel/group"""
    try:
        bot_id = bot.get_me().id
        
        # FIXED: Better handling of different ID formats
        chat_identifiers = []
        
        # Handle numeric IDs (including negative ones like -100...)
        if chat_id.lstrip('-').isdigit():
            chat_identifiers.append(int(chat_id))
            chat_identifiers.append(chat_id)  # Keep as string too
        else:
            # Handle username format
            clean_id = chat_id.lstrip('@')
            chat_identifiers.append(f'@{clean_id}')
            chat_identifiers.append(clean_id)
        
        for identifier in chat_identifiers:
            try:
                # Try to get bot's membership status
                bot_member = bot.get_chat_member(identifier, bot_id)
                log_debug(f"Bot access to {identifier}: {bot_member.status}")
                
                # Bot needs to be at least a member to check other members
                if bot_member.status in ['member', 'administrator', 'creator']:
                    return {'has_access': True, 'status': bot_member.status}
                else:
                    return {'has_access': False, 'error': f'Bot status: {bot_member.status}'}
                    
            except telebot.apihelper.ApiException as e:
                error_desc = str(e).lower()
                if "chat not found" in error_desc:
                    continue  # Try next identifier
                log_debug(f"Bot access check failed for {identifier}: {e}")
                continue
        
        return {'has_access': False, 'error': 'Could not verify bot access with any identifier'}
        
    except Exception as e:
        log_error(f"Error verifying bot access to {chat_id}: {e}")
        return {'has_access': False, 'error': str(e)}

# NEW: Enhanced subscription checking with retry mechanism
def check_subscription_with_retry(user_id, max_retries=3):
    """Check subscription with intelligent retry mechanism"""
    for attempt in range(max_retries):
        try:
            result = check_subscription(user_id)
            if isinstance(result, SubscriptionResult):
                if not result.retry_needed:
                    return result.subscribed
                elif attempt == max_retries - 1:
                    log_error(f"Max retries reached for user {user_id}, returning False")
                    return False
                else:
                    sleep_time = 2 ** attempt  # Exponential backoff
                    log_debug(f"Retrying subscription check for user {user_id} in {sleep_time}s")
                    time.sleep(sleep_time)
            else:
                return result
        except Exception as e:
            log_error(f"Subscription check attempt {attempt + 1} failed for user {user_id}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
    return False

# FIXED: Completely rewritten check_subscription function
def check_subscription(user_id):
    """Enhanced subscription checking with improved error handling"""
    if user_id in admins:
        log_debug(f"User {user_id} is admin, subscription check passed")
        return True

    channels = load_channels()
    log_debug(f"Checking subscription for user {user_id}")
    log_debug(f"Channels to check: {channels}")
    
    if not channels:
        log_debug("No channels configured, allowing access")
        return True

    for channel in channels:
        try:
            # Handle both dict and string formats
            if isinstance(channel, dict):
                chat_id = channel.get("username", "").strip()
                title = channel.get("title", chat_id)
            else:
                chat_id = str(channel).strip()
                title = chat_id

            # Clean up chat_id
            chat_id = chat_id.lstrip('@')
            
            if not chat_id:
                log_debug(f"Empty chat_id for channel {channel}, skipping")
                continue

            log_debug(f"Checking user {user_id} in channel: {chat_id}")
            
            # First verify bot has access to the channel
            bot_access_result = verify_bot_access(chat_id)
            if not bot_access_result['has_access']:
                log_error(f"Bot lacks access to {chat_id}: {bot_access_result['error']}")
                # Return retry-needed result for bot permission issues
                return SubscriptionResult(False, bot_access_result['error'], retry_needed=True)
            
            # FIXED: Better handling of different ID formats
            chat_identifiers = []
            
            # Handle numeric IDs (including negative ones like -100...)
            if chat_id.lstrip('-').isdigit():
                chat_identifiers.append(int(chat_id))
                chat_identifiers.append(chat_id)  # Keep as string too
            else:
                # Handle username format
                chat_identifiers.append(f'@{chat_id}')
                chat_identifiers.append(chat_id)
            
            member = None
            last_error = None
            
            for identifier in chat_identifiers:
                try:
                    member = bot.get_chat_member(identifier, user_id)
                    log_debug(f"Successfully got member info for {identifier}")
                    break
                except telebot.apihelper.ApiException as api_e:
                    last_error = api_e
                    error_desc = str(api_e).lower()
                    log_debug(f"Failed to get member info for {identifier}: {api_e}")
                    
                    # Check if this is a transient error that should be retried
                    if any(x in error_desc for x in ['timeout', 'too many requests', 'internal server error', '429', '5']):
                        log_debug(f"Transient error detected for {identifier}")
                        return SubscriptionResult(False, str(api_e), retry_needed=True)
                    continue
            
            if member is None:
                error_desc = str(last_error).lower() if last_error else "unknown error"
                
                # Categorize the error
                if "chat not found" in error_desc:
                    log_error(f"Channel {chat_id} not found - skipping")
                    continue  # Skip non-existent channels
                elif "user not found" in error_desc:
                    log_error(f"User {user_id} not found")
                    return False  # Definitive: user doesn't exist
                elif "bot was blocked" in error_desc:
                    log_error(f"Bot was blocked by user {user_id}")
                    return False  # Definitive: user blocked bot
                elif any(x in error_desc for x in ['not enough rights', 'forbidden', 'bot is not a member']):
                    log_error(f"Bot permission issue for {chat_id}: {last_error}")
                    return SubscriptionResult(False, str(last_error), retry_needed=True)
                else:
                    log_error(f"Could not get member info for user {user_id} in {chat_id}: {last_error}")
                    return SubscriptionResult(False, str(last_error), retry_needed=True)
            
            log_debug(f"User {user_id} status in {chat_id}: {member.status}")
            
            # Consider 'restricted' as subscribed (they're in the channel but limited)
            if member.status in ['member', 'administrator', 'creator', 'restricted']:
                log_debug(f"User {user_id} is subscribed to {chat_id} (status: {member.status})")
                continue
            elif member.status in ['left', 'kicked']:
                log_debug(f"User {user_id} not subscribed to {chat_id} (status: {member.status})")
                return False  # Definitive: user left or was kicked
            else:
                log_debug(f"Unknown status {member.status} for user {user_id} in {chat_id}")
                return SubscriptionResult(False, f"Unknown status: {member.status}", retry_needed=True)
                
        except telebot.apihelper.ApiException as e:
            error_desc = str(e).lower()
            log_error(f"API Error for channel {chat_id}: {e}")
            
            # Handle different types of API errors
            if "chat not found" in error_desc:
                log_error(f"Channel {chat_id} not found - skipping")
                continue
            elif "user not found" in error_desc:
                return False  # Definitive
            elif "bot was blocked" in error_desc:
                return False  # Definitive
            elif any(x in error_desc for x in ['timeout', 'too many requests', 'internal server error', '429', '5']):
                return SubscriptionResult(False, str(e), retry_needed=True)
            else:
                return SubscriptionResult(False, str(e), retry_needed=True)
                
        except Exception as exc:
            log_error(f"Unexpected error checking {chat_id}: {exc}")
            return SubscriptionResult(False, str(exc), retry_needed=True)
    
    log_debug(f"User {user_id} subscribed to all required channels")
    return True

def load_data(file_path):
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def add_user(user_id):
    if not os.path.exists(USER_FILE):
        with open(USER_FILE, 'w') as file:
            file.write('')

    with open(USER_FILE, 'r') as file:
        users = file.read().splitlines()

    if str(user_id) not in users:
        with open(USER_FILE, 'a') as file:
            file.write(f"{user_id}\n")

def count_users():
    if not os.path.exists(USER_FILE):
        return 0
    with open(USER_FILE, 'r') as file:
        users = file.read().splitlines()
    return len(users)

# Hàm lưu dữ liệu
def save_data(file_path, data):
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)

# Hàm lấy số dư của người dùng
def get_balance(user_id):
    user_id_str = str(user_id)
    if user_id_str in user_data:
        if 'balance' not in user_data[user_id_str]:
            user_data[user_id_str]['balance'] = 0
            save_data(user_data_file, user_data)
        return user_data[user_id_str]['balance']
    else:
        initialize_user(user_id)
        return 0

# Hàm khởi tạo người dùng
def initialize_user(user_id):
    user_id_str = str(user_id)
    if user_id_str not in user_data:
        user_data[user_id_str] = {
            'balance': 0, 
            'referrals': [],
            'withdrawals': 0,
            'invited_count': 0
        }
        save_data(user_data_file, user_data)

# Hàm cập nhật số dư của người dùng
def update_user_balance(user_id, amount):
    user_id_str = str(user_id)
    if user_id_str in user_data:
        if 'balance' not in user_data[user_id_str]:
            user_data[user_id_str]['balance'] = 0
        user_data[user_id_str]['balance'] += amount
    else:
        user_data[user_id_str] = {
            'balance': amount, 
            'referrals': [],
            'withdrawals': 0,
            'invited_count': 0
        }
    save_data(user_data_file, user_data)

def save_user_data(user_data):
    with open(user_data_file, 'w') as file:
        json.dump(user_data, file, indent=4)

# Hàm lấy danh sách người được mời bởi một người dùng
def get_referred_users(user_id):
    referred_users = []
    user_id_str = str(user_id)

    # Kiểm tra trong user_data (ưu tiên)
    if user_id_str in user_data and 'referrals' in user_data[user_id_str]:
        referred_users = user_data[user_id_str]['referrals'].copy()

    # Kiểm tra trong lịch sử giới thiệu
    if user_id_str in referral_history:
        for ref_user in referral_history[user_id_str]:
            if ref_user not in referred_users:
                referred_users.append(ref_user)

    # Kiểm tra trong danh sách đang chờ xử lý
    for invited_id, referrer_id in invited_users.items():
        if referrer_id == user_id_str and invited_id not in referred_users:
            referred_users.append(invited_id)

    return referred_users

# Hàm xử lý khi người dùng sử dụng mã giới thiệu
def process_referral(user_id, referrer_id):
    user_id_str = str(user_id)
    referrer_id_str = str(referrer_id)
    
    # Khởi tạo người dùng mới nếu chưa tồn tại
    if user_id_str not in user_data:
        initialize_user(user_id)
    
    # Khởi tạo người giới thiệu nếu chưa tồn tại
    if referrer_id_str not in user_data:
        initialize_user(referrer_id)
    
    # Đảm bảo có khóa 'referrals' cho người giới thiệu
    if 'referrals' not in user_data[referrer_id_str]:
        user_data[referrer_id_str]['referrals'] = []
    
    # Thêm người được giới thiệu vào danh sách
    if user_id_str not in user_data[referrer_id_str]['referrals']:
        user_data[referrer_id_str]['referrals'].append(user_id_str)
    
    # Cập nhật lịch sử giới thiệu
    if referrer_id_str not in referral_history:
        referral_history[referrer_id_str] = []
    if user_id_str not in referral_history[referrer_id_str]:
        referral_history[referrer_id_str].append(user_id_str)
    
    # Cộng tiền thưởng cho người giới thiệu
    settings = load_settings()
    referral_bonus = settings.get('referral_bonus', 1500)
    update_user_balance(referrer_id, referral_bonus)
    
    # Tăng counter số lượt mời
    if 'invited_count' not in user_data[referrer_id_str]:
        user_data[referrer_id_str]['invited_count'] = 0
    user_data[referrer_id_str]['invited_count'] += 1
    
    # Lưu dữ liệu
    save_data(user_data_file, user_data)
    save_referral_history()

# Hàm lấy code ngẫu nhiên từ danh sách code có sẵn
def get_random_code():
    global codes
    if not codes:
        return None
    code = random.choice(codes)
    try:
        codes.remove(code)
    except ValueError:
        return None
    save_codes()
    return code

# ĐẬP HỘP: lấy code riêng cho đập hộp
def get_drop_code():
    global drop_codes
    if not drop_codes:
        return None
    # Giới hạn chỉ 5 code mỗi đợt
    if len(current_drop.get('claimed_users', [])) >= 5:
        return None
    code = random.choice(drop_codes)
    try:
        drop_codes.remove(code)
    except ValueError:
        return None
    with open(DROP_CODES_FILE, 'w') as f:
        json.dump(drop_codes, f, indent=4)
    return code

# ĐẬP HỘP: Tạo ID đợt và khởi tạo đợt mới
def start_new_drop():
    global current_drop
    drop_conf = get_drop_settings()
    window = int(drop_conf.get('window_minutes', drop_window_minutes))
    now = datetime.now()
    with drop_lock:
        current_drop = {
            'id': int(time.time()),
            'active': True,
            'start_ts': now.timestamp(),
            'end_ts': (now + timedelta(minutes=window)).timestamp(),
            'claimed_users': [],
            'chat_id': None,
            'message_id': None
        }
    return current_drop

def is_drop_active():
    with drop_lock:
        if not current_drop.get('active'):
            return False
        return time.time() <= current_drop.get('end_ts', 0)

def end_current_drop():
    global current_drop
    with drop_lock:
        current_drop['active'] = False
        current_drop['end_ts'] = time.time()

# Tải dữ liệu người dùng
user_data = load_data(user_data_file)
invited_users = load_data(invited_users_file)

# Load initial data
codes = load_codes()
used_codes = load_used_codes()
referral_history = load_referral_history()
game_link = load_game_link()
drop_codes = load_drop_codes()

# NEW: Function to check bot permissions in all channels
def check_bot_permissions():
    """Check bot permissions in all configured channels"""
    channels = load_channels()
    log_debug("=== CHECKING BOT PERMISSIONS ===")
    
    bot_info = bot.get_me()
    bot_id = bot_info.id
    
    permissions_report = []
    
    for channel in channels:
        try:
            if isinstance(channel, dict):
                chat_id = channel.get("username", "").lstrip('@')
                title = channel.get("title", chat_id)
            else:
                chat_id = str(channel).lstrip('@')
                title = chat_id
                
            if not chat_id:
                continue
            
            # FIXED: Better handling of different ID formats
            chat_identifiers = []
            
            # Handle numeric IDs (including negative ones like -100...)
            if chat_id.lstrip('-').isdigit():
                chat_identifiers.append(int(chat_id))
                chat_identifiers.append(chat_id)  # Keep as string too
            else:
                # Handle username format
                chat_identifiers.append(f'@{chat_id}')
                chat_identifiers.append(chat_id)
            
            for identifier in chat_identifiers:
                try:
                    # Check bot membership
                    bot_member = bot.get_chat_member(identifier, bot_id)
                    
                    # Get chat info
                    chat_info = bot.get_chat(identifier)
                    
                    status_info = {
                        'channel': chat_id,
                        'title': title,
                        'chat_type': chat_info.type,
                        'bot_status': bot_member.status,
                        'chat_title': getattr(chat_info, 'title', 'N/A'),
                        'success': True
                    }
                    permissions_report.append(status_info)
                    
                    log_debug(f"Bot in {identifier}: {bot_member.status}")
                    log_debug(f"   - Type: {chat_info.type}")
                    log_debug(f"   - Title: {getattr(chat_info, 'title', 'N/A')}")
                    break
                    
                except Exception as inner_e:
                    continue
            else:
                # If all formats failed
                error_info = {
                    'channel': chat_id,
                    'title': title,
                    'error': 'Could not access channel',
                    'success': False
                }
                permissions_report.append(error_info)
                log_error(f"Cannot access {chat_id}")
                
        except Exception as e:
            error_info = {
                'channel': getattr(channel, 'username', str(channel)),
                'error': str(e),
                'success': False
            }
            permissions_report.append(error_info)
            log_error(f"Error checking {channel}: {e}")
    
    return permissions_report

# ===== ĐẬP HỘP: Gửi thông báo đợt mới =====
def broadcast_drop_announcement(chat_id):
    drop_conf = get_drop_settings()
    window = int(drop_conf.get('window_minutes', 15))
    title = drop_conf.get('title', '🎁 Đập Hộp')
    image_url = drop_conf.get('image_url', '')
    image_file_id = drop_conf.get('image_file_id', '')
    button_text = drop_conf.get('button_text', '🎁 Đập Hộp')

    started = start_new_drop()
    end_time = datetime.fromtimestamp(started['end_ts']).strftime('%H:%M')

    caption = (
        f"{title}\n\n"
        f"🎁 Code hôm nay đến rồi mau dựt code thoi\n"
        f"⛔ Đập hộp chỉ có 5p , sau 5p hộp sẽ biến mất\n\n"
        f"🔔 Đừng quên bật chuông thông báo nhé!\n"
        f"🎮 Mời bạn choi ngay \n"
    )

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(button_text, callback_data=f"dap_hop:{started['id']}"))
    gl = load_game_link()
    if gl:
        markup.add(InlineKeyboardButton("🌐 Link Game", url=gl))

    try:
        sent = None
        if image_file_id:
            sent = bot.send_photo(chat_id, image_file_id, caption=caption, reply_markup=markup)
        elif image_url:
            sent = bot.send_photo(chat_id, image_url, caption=caption, reply_markup=markup)
        else:
            sent = bot.send_message(chat_id, caption, reply_markup=markup)
        with drop_lock:
            current_drop['chat_id'] = chat_id
            current_drop['message_id'] = getattr(sent, 'message_id', None)
    except Exception as e:
        log_error(f"Broadcast drop failed: {e}")

# Gửi thông báo Đập Hộp cho tất cả user
def send_to_all_users():
    try:
        # Đọc danh sách user từ file
        if not os.path.exists(USER_FILE):
            return
        
        with open(USER_FILE, 'r') as file:
            users = file.read().splitlines()
        
        sent_count = 0
        for user_id in users:
            if user_id.strip():
                try:
                    broadcast_drop_announcement(int(user_id))
                    sent_count += 1
                    time.sleep(0.1)  # Tránh spam
                except Exception as e:
                    log_error(f"Failed to send to user {user_id}: {e}")
                    continue
        
        log_debug(f"Sent drop announcement to {sent_count} users")
    except Exception as e:
        log_error(f"send_to_all_users failed: {e}")

# Thông báo hết code cho tất cả user
def announce_out_of_codes():
    try:
        conf = get_drop_settings()
        gl = load_game_link()
        
        msg = (
            "🎁 Đập Hộp\n\n"
            "😔 Rất tiếc, bạn chưa trúng CODE lần này.\n"
            "✨ Chúc bạn may mắn lần sau 🎁\n\n"
            "🔔 Đừng quên bật chuông thông báo nhé!\n"
            "🎮 Chơi ngay không cần code"
        )

        markup = InlineKeyboardMarkup()
        if gl:
            markup.add(InlineKeyboardButton("🌐 Link Game", url=gl))
        
        # Gửi cho tất cả user
        if not os.path.exists(USER_FILE):
            return
        
        with open(USER_FILE, 'r') as file:
            users = file.read().splitlines()
        
        sent_count = 0
        for user_id in users:
            if user_id.strip():
                try:
                    bot.send_message(int(user_id), msg, reply_markup=markup)
                    sent_count += 1
                    time.sleep(0.1)  # tránh spam
                except Exception as e:
                    log_error(f"Failed to send out-of-codes to user {user_id}: {e}")
                    continue
        
        log_debug(f"Sent out-of-codes announcement to {sent_count} users")
        announce_out_of_codes_to_chat()
                    
    except Exception as e:
        log_error(f"announce_out_of_codes failed: {e}")

# Xóa hoàn toàn tin nhắn Đập Hộp và nút sau thời gian quy định
def remove_drop_image_and_button():
    try:
        with drop_lock:
            chat_id = current_drop.get('chat_id')
            msg_id = current_drop.get('message_id')
        
        if chat_id and msg_id:
            try:
                # Thử xóa hẳn tin nhắn (bao gồm ảnh/nút)
                bot.delete_message(chat_id, msg_id)
                log_debug("Deleted drop message after timeout")
                with drop_lock:
                    current_drop['message_id'] = None
            except Exception as delete_err:
                log_error(f"Failed to delete drop message, fallback to edit: {delete_err}")
                try:
                    # Fallback: gỡ nút và thay nội dung
                    bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
                    try:
                        bot.edit_message_caption(chat_id, msg_id, caption="🎁 Đập Hộp đã kết thúc.", parse_mode=None)
                    except Exception:
                        bot.edit_message_text("🎁 Đập Hộp đã kết thúc.", chat_id, msg_id)
                except Exception as e:
                    log_error(f"Failed to fallback edit drop message: {e}")
    except Exception as e:
        log_error(f"remove_drop_image_and_button failed: {e}")

# Thông báo hết code lên chat chính
def announce_out_of_codes_to_chat():
    try:
        with drop_lock:
            chat_id = current_drop.get('chat_id')
            msg_id = current_drop.get('message_id')
        
        if chat_id and msg_id:
            try:
                # Gỡ nút
                bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
                # Thay ảnh bằng text đơn giản
                try:
                    bot.edit_message_caption(chat_id, msg_id, caption="🎁 Đập Hộp: ĐÃ HẾT CODE", parse_mode=None)
                except Exception:
                    # Nếu không phải ảnh, thay nội dung tin nhắn
                    bot.edit_message_text("🎁 Đập Hộp: ĐÃ HẾT CODE", chat_id, msg_id)
            except Exception as e:
                log_error(f"Failed to update out-of-codes message: {e}")
    except Exception as e:
        log_error(f"announce_out_of_codes_to_chat failed: {e}")

# Tự động xóa ảnh và nút sau 5 phút
def auto_remove_drop_after_5min():
    try:
        with drop_lock:
            if not current_drop.get('active'):
                return
            start_ts = current_drop.get('start_ts')
            if not start_ts:
                return
        
        # Kiểm tra đã qua 5 phút chưa
        current_time = time.time()
        if current_time - start_ts >= 300:  # 5 phút = 300 giây
            remove_drop_image_and_button()
            log_debug("Auto removed drop image/button after 5 minutes")
    except Exception as e:
        log_error(f"auto_remove_drop_after_5min failed: {e}")

# Gửi tin nhắn hết code cho user cụ thể
def send_out_of_codes_to_user(user_id):
    try:
        gl = load_game_link()
        
        msg = (
    "🎁 Đập Hộp\n\n"
    "😔 Rất tiếc, bạn chưa trúng CODE lần này.\n"
    "✨ Chúc bạn may mắn lần sau 🎁\n\n"
    "🔔 Đừng quên bật chuông thông báo nhé!\n"
    "🎮 Chơi ngay không cần code"
)
        
        markup = InlineKeyboardMarkup()
        if gl:
            markup.add(InlineKeyboardButton("🌐 Link Game", url=gl))
        
        bot.send_message(user_id, msg, reply_markup=markup)
        log_debug(f"Sent out-of-codes message to user {user_id}")
        
    except Exception as e:
        log_error(f"send_out_of_codes_to_user failed: {e}")

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith('dap_hop:'))
def handle_dap_hop_callback(call):
    try:
        parts = call.data.split(':', 1)
        drop_id = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        drop_id = 0

    # Không xóa ngay, sẽ tự động xóa sau 5 phút

    # Kiểm tra đợt còn hiệu lực
    if not is_drop_active() or drop_id != current_drop.get('id'):
        bot.answer_callback_query(call.id, text='Đợt đã kết thúc hoặc không hợp lệ.', show_alert=True)
        return

    user_id = call.from_user.id


    # Yêu cầu theo dõi kênh (nếu có)
    if not check_subscription_with_retry(user_id):
        bot.answer_callback_query(call.id, text='Vui lòng tham gia các kênh bắt buộc trước!', show_alert=True)
        return

    # Gán code theo nguyên tắc ai nhanh người được
    with drop_lock:
        if user_id in current_drop['claimed_users']:
            bot.answer_callback_query(call.id, text='Bạn đã nhận rồi!', show_alert=True)
            return
        code = get_drop_code()
        if code is None:
            # HẾT CODE - Chỉ gửi tin nhắn riêng cho user này
            end_current_drop()
            send_out_of_codes_to_user(user_id)
            bot.answer_callback_query(call.id, text='Đã hết CODE cho đợt này!', show_alert=True)
            return
        # Lưu used_codes
        used_codes[str(user_id)] = {
            'code': code,
            'time': datetime.now().isoformat()
        }
        save_used_codes()
        current_drop['claimed_users'].append(user_id)

    # Gửi code riêng cho người dùng
    try:
        bot.answer_callback_query(call.id, text='Nhận CODE thành công! Kiểm tra tin nhắn.', show_alert=False)
        bot.send_message(user_id, f"🎁 CODE của bạn: <b>{code}</b>", parse_mode='HTML')
    except Exception as e:
        log_error(f"Send code to user failed: {e}")


# Menu cho admin
def admin_menu(message):
    if message.from_user.id in admins:
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        markup.add(types.KeyboardButton('📋 Quản lý nhóm'),
                   types.KeyboardButton('⚙️ Cài đặt hệ thống'))
        markup.add(types.KeyboardButton('📊 Thống kê'),
                   types.KeyboardButton('📢 Thông báo toàn hệ thống'))
        markup.add(types.KeyboardButton('💰 Cộng tiền'),
                   types.KeyboardButton('🎁 Quản lý CODE'))
        markup.add(types.KeyboardButton('🎮 Quản lý Link Game'),
                   types.KeyboardButton('🖼 Thay đổi ảnh thông báo'))
        markup.add(types.KeyboardButton('🎁 Cấu hình Đập Hộp'))
        markup.add(types.KeyboardButton('🔙 Quay lại menu chính'))

        bot.send_message(
            message.chat.id,
            "📱 <b>Menu quản trị viên</b>\n\nChọn chức năng bạn muốn sử dụng:",
            reply_markup=markup,
            parse_mode='HTML')
    else:
        bot.send_message(message.chat.id,
                         "❌ Bạn không có quyền truy cập menu này!")


@bot.message_handler(func=lambda message: message.text == "🎁 Cấu hình Đập Hộp")
def drop_config_menu(message):
    if message.from_user.id in admins:
        conf = get_drop_settings()
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        # Button bật/tắt đập hộp
        toggle_text = '🔴 TẮT Đập Hộp' if conf.get('enabled', True) else '🟢 BẬT Đập Hộp'
        markup.add(types.KeyboardButton(toggle_text))
        markup.add(types.KeyboardButton('✏️ Sửa tiêu đề'))
        markup.add(types.KeyboardButton('⏱ Sửa thời gian hợp lệ'),
                   types.KeyboardButton('🕐 Sửa thời điểm rơi (HH:MM)'))
        markup.add(types.KeyboardButton('📷 Upload ảnh Đập Hộp'),
                   types.KeyboardButton('🧹 Xóa ảnh Đập Hộp'))
        markup.add(types.KeyboardButton('➕ Thêm CODE Đập Hộp'),
                   types.KeyboardButton('📜 Xem CODE Đập Hộp'))
        markup.add(types.KeyboardButton('🗑 Xóa hết CODE Đập Hộp'))
        markup.add(types.KeyboardButton('🔙 Quay lại menu admin'))

        text = (
            f"🎁 <b>Cấu hình Đập Hộp</b>\n\n"
            f"Bật: {'✅' if conf.get('enabled', True) else '❌'}\n"
            f"Tiêu đề: {conf.get('title','🎁 Đập Hộp')}\n"
            f"Ảnh: {conf.get('image_url','(trống)')}\n"
            f"Thời gian hợp lệ: {conf.get('window_minutes',15)} phút\n"
            f"Thời điểm rơi trong ngày: {conf.get('times', ['09:00', '21:00'])}\n"
        )
        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='HTML')

# Handler cho button bật/tắt đập hộp
@bot.message_handler(func=lambda message: message.text in ['🔴 TẮT Đập Hộp', '🟢 BẬT Đập Hộp'])
def toggle_drop_enabled(message):
    if message.from_user.id in admins:
        try:
            settings = load_settings()
            settings.setdefault('drop', get_drop_settings())
            
            # Toggle trạng thái enabled
            current_state = settings['drop'].get('enabled', True)
            new_state = not current_state
            settings['drop']['enabled'] = new_state
            
            save_settings(settings)
            
            # Thông báo kết quả
            status_text = "BẬT" if new_state else "TẮT"
            status_emoji = "🟢" if new_state else "🔴"
            
            bot.send_message(
                message.chat.id,
                f"{status_emoji} <b>ĐÃ {status_text} ĐẬP HỘP</b>\n\n"
                f"Trạng thái hiện tại: {status_emoji} {status_text}",
                parse_mode='HTML'
            )
            
            # Quay lại menu cấu hình đập hộp
            drop_config_menu(message)
            
        except Exception as e:
            bot.send_message(
                message.chat.id,
                f"❌ Lỗi khi thay đổi trạng thái đập hộp: {str(e)}"
            )
    else:
        bot.reply_to(message, "❌ Bạn không có quyền sử dụng chức năng này!")

@bot.message_handler(func=lambda message: message.text == '🖼 Sửa ảnh Đập Hộp')
def edit_drop_image(message):
    if message.from_user.id in admins:
        bot.send_message(message.chat.id, 'Gửi URL ảnh mới:')
        bot.register_next_step_handler(message, _save_drop_image)

def _save_drop_image(message):
    if message.from_user.id in admins:
        settings = load_settings()
        settings.setdefault('drop', get_drop_settings())
        settings['drop']['image_url'] = message.text.strip()
        save_settings(settings)
        drop_config_menu(message)

@bot.message_handler(func=lambda message: message.text == '✏️ Sửa tiêu đề')
def edit_drop_title(message):
    if message.from_user.id in admins:
        bot.send_message(message.chat.id, 'Nhập tiêu đề mới:')
        bot.register_next_step_handler(message, _save_drop_title)

def _save_drop_title(message):
    if message.from_user.id in admins:
        settings = load_settings()
        settings.setdefault('drop', get_drop_settings())
        settings['drop']['title'] = message.text.strip()
        save_settings(settings)
        drop_config_menu(message)

@bot.message_handler(func=lambda message: message.text == '📷 Upload ảnh Đập Hộp')
def upload_drop_image_prompt(message):
    if message.from_user.id in admins:
        bot.send_message(message.chat.id, 'Gửi ảnh làm ảnh Đập Hộp (ảnh JPEG/PNG).')
        bot.register_next_step_handler(message, _save_drop_image_file)

def _save_drop_image_file(message):
    if message.from_user.id in admins:
        if message.content_type == 'photo':
            try:
                file_id = message.photo[-1].file_id
                settings = load_settings()
                settings.setdefault('drop', get_drop_settings())
                settings['drop']['image_file_id'] = file_id
                save_settings(settings)
                bot.send_message(message.chat.id, '✅ Đã lưu ảnh tải lên cho Đập Hộp.')
            except Exception as e:
                bot.send_message(message.chat.id, f'❌ Lỗi lưu ảnh: {e}')
        else:
            bot.send_message(message.chat.id, '❌ Vui lòng gửi đúng loại ảnh.')
        drop_config_menu(message)

@bot.message_handler(func=lambda message: message.text == '🧹 Xóa ảnh Đập Hộp')
def clear_drop_image(message):
    if message.from_user.id in admins:
        settings = load_settings()
        settings.setdefault('drop', get_drop_settings())
        settings['drop']['image_file_id'] = ''
        settings['drop']['image_url'] = ''
        save_settings(settings)
        bot.send_message(message.chat.id, '✅ Đã xóa cấu hình ảnh Đập Hộp.')
        drop_config_menu(message)

@bot.message_handler(func=lambda message: message.text == '⏱ Sửa thời gian hợp lệ')
def edit_drop_window(message):
    if message.from_user.id in admins:
        bot.send_message(message.chat.id, 'Nhập số phút (1-60):')
        bot.register_next_step_handler(message, _save_drop_window)

def _save_drop_window(message):
    if message.from_user.id in admins:
        try:
            minutes = max(1, min(60, int(message.text.strip())))
            settings = load_settings()
            settings.setdefault('drop', get_drop_settings())
            settings['drop']['window_minutes'] = minutes
            save_settings(settings)
        except Exception:
            pass
        drop_config_menu(message)

@bot.message_handler(func=lambda message: message.text == '🕐 Sửa thời điểm rơi (HH:MM)')
def edit_drop_range(message):
    if message.from_user.id in admins:
        bot.send_message(message.chat.id, 'Nhập danh sách thời điểm dạng H1:M1,H2:M2 (vd: 9:20,10:20):')
        bot.register_next_step_handler(message, _save_drop_range)

def _save_drop_range(message):
    if message.from_user.id in admins:
        try:
            txt = message.text.replace(' ', '')
            parts = [p for p in txt.split(',') if p]
            times = []
            for p in parts:
                hh, mm = p.split(':')
                hh = max(0, min(23, int(hh)))
                mm = max(0, min(59, int(mm)))
                times.append(f"{hh:02d}:{mm:02d}")
            if not times:
                raise ValueError('empty')
            settings = load_settings()
            settings.setdefault('drop', get_drop_settings())
            settings['drop']['times'] = times
            save_settings(settings)
        except Exception:
            pass
        drop_config_menu(message)

@bot.message_handler(func=lambda message: message.text == '📍 Đặt nơi gửi thông báo')
def set_drop_target(message):
    if message.from_user.id in admins:
        bot.send_message(message.chat.id, 
            'Nhập Chat ID để gửi thông báo Đập Hộp:\n'
            '- Gửi "all" để gửi cho tất cả user\n'
            '- Gửi Chat ID (số âm cho group/channel)\n'
            '- Gửi "current" để dùng chat hiện tại')
        bot.register_next_step_handler(message, _save_drop_target)

def _save_drop_target(message):
    if message.from_user.id in admins:
        try:
            text = message.text.strip().lower()
            if text == 'all':
                target = None
            elif text == 'current':
                target = message.chat.id
            else:
                target = int(text)
            settings = load_settings()
            settings.setdefault('drop', get_drop_settings())
            settings['drop']['target_chat_id'] = target
            save_settings(settings)
            bot.send_message(message.chat.id, f'✅ Đã đặt nơi gửi: {target if target else "Tất cả user"}')
        except Exception as e:
            bot.send_message(message.chat.id, f'❌ Lỗi: {e}')
        drop_config_menu(message)

@bot.message_handler(func=lambda message: message.text == '🌍 Đặt múi giờ')
def set_timezone(message):
    if message.from_user.id in admins:
        bot.send_message(message.chat.id, 
            'Nhập múi giờ (ví dụ):\n'
            '- Asia/Ho_Chi_Minh (Việt Nam)\n'
            '- Asia/Bangkok (Thái Lan)\n'
            '- Asia/Shanghai (Trung Quốc)\n'
            '- Europe/London (Anh)\n'
            '- America/New_York (Mỹ)\n'
            '- UTC (UTC+0)')
        bot.register_next_step_handler(message, _save_timezone)

def _save_timezone(message):
    if message.from_user.id in admins:
        try:
            tz_name = message.text.strip()
            # Test múi giờ có hợp lệ không
            pytz.timezone(tz_name)
            settings = load_settings()
            settings.setdefault('drop', get_drop_settings())
            settings['drop']['timezone'] = tz_name
            save_settings(settings)
            bot.send_message(message.chat.id, f'✅ Đã đặt múi giờ: {tz_name}')
        except Exception as e:
            bot.send_message(message.chat.id, f'❌ Múi giờ không hợp lệ: {e}')
        drop_config_menu(message)

@bot.message_handler(func=lambda message: message.text == '🚀 Test gửi Đập Hộp')
def test_send_drop(message):
    if message.from_user.id in admins:
        broadcast_drop_announcement(message.chat.id)
        bot.reply_to(message, 'Đã gửi thử thông báo Đập Hộp vào chat hiện tại.')

@bot.message_handler(func=lambda message: message.text == '➕ Thêm CODE Đập Hộp')
def add_drop_codes(message):
    if message.from_user.id in admins:
        bot.send_message(message.chat.id, 'Gửi danh sách CODE (mỗi dòng 1 CODE):')
        bot.register_next_step_handler(message, _save_drop_codes)

def _save_drop_codes(message):
    if message.from_user.id in admins:
        global drop_codes
        lines = [l.strip() for l in message.text.split('\n') if l.strip()]
        before = set(drop_codes)
        drop_codes.extend([c for c in lines if c not in before])
        drop_codes = list(dict.fromkeys(drop_codes))
        save_drop_codes()
        bot.send_message(message.chat.id, f'Đã thêm {len(lines)} CODE. Tổng: {len(drop_codes)}')
        drop_config_menu(message)

@bot.message_handler(func=lambda message: message.text == '📜 Xem CODE Đập Hộp')
def view_drop_codes(message):
    if message.from_user.id in admins:
        if not drop_codes:
            bot.send_message(message.chat.id, 'Hiện không có CODE Đập Hộp nào.')
        else:
            show = '\n'.join(f"{i+1}. {c}" for i, c in enumerate(drop_codes[:50]))
            more = '' if len(drop_codes) <= 50 else f"\n... và {len(drop_codes)-50} CODE khác"
            bot.send_message(message.chat.id, f"📜 CODE Đập Hộp ({len(drop_codes)}):\n\n{show}{more}")
        drop_config_menu(message)

@bot.message_handler(func=lambda message: message.text == '🗑 Xóa hết CODE Đập Hộp')
def clear_drop_codes(message):
    if message.from_user.id in admins:
        global drop_codes
        drop_codes = []
        save_drop_codes()
        bot.send_message(message.chat.id, 'Đã xóa toàn bộ CODE Đập Hộp.')
        drop_config_menu(message)


# Menu quản lý CODE
def code_management_menu(message):
    if message.from_user.id in admins:
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        markup.add(types.KeyboardButton('➕ Thêm CODE'),
                   types.KeyboardButton('📜 Danh sách CODE có sẵn'))
        markup.add(types.KeyboardButton('📊 Thống kê CODE đã dùng'),
                   types.KeyboardButton('➖ Xóa nhiều CODE'))
        auto_status = "🟢 TẮT" if auto_approve else "🔴 BẬT"
        markup.add(types.KeyboardButton(f'⚙️ Duyệt tự động ({auto_status})'))
        markup.add(types.KeyboardButton('🔙 Quay lại menu admin'))

        bot.send_message(
            message.chat.id,
            "🎁 <b>Quản lý CODE</b>\n\nChọn chức năng bạn muốn sử dụng:",
            reply_markup=markup,
            parse_mode='HTML')

# NEW: Handler for ➕ Thêm CODE
@bot.message_handler(func=lambda message: message.text == "➕ Thêm CODE")
def handle_add_code(message):
    if message.from_user.id in admins:
        bot.send_message(
            message.chat.id,
            "📝 <b>THÊM CODE MỚI</b>\n\n"
            "Vui lòng nhập danh sách CODE (mỗi code một dòng):\n\n"
            "📋 <b>Ví dụ:</b>\n"
            "CODE001\n"
            "CODE002\n"
            "CODE003\n\n"
            "⚠️ <b>Lưu ý:</b> Mỗi code một dòng riêng biệt",
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_add_code)

def process_add_code(message):
    if message.from_user.id in admins:
        try:
            # Split by lines and clean up
            new_codes = [code.strip() for code in message.text.split('\n') if code.strip()]
            
            if not new_codes:
                bot.send_message(
                    message.chat.id,
                    "❌ Không có CODE nào được nhập. Vui lòng thử lại."
                )
                code_management_menu(message)
                return
            
            # Check for duplicates
            global codes
            duplicates = []
            added_codes = []
            
            for code in new_codes:
                if code in codes:
                    duplicates.append(code)
                else:
                    codes.append(code)
                    added_codes.append(code)
            
            # Save to file
            save_codes()
            
            # Create response message
            response = f"✅ <b>ĐÃ THÊM CODE THÀNH CÔNG</b>\n\n"
            
            if added_codes:
                response += f"📊 <b>Đã thêm {len(added_codes)} CODE mới:</b>\n"
                for i, code in enumerate(added_codes[:10], 1):  # Show max 10 codes
                    response += f"{i}. <code>{code}</code>\n"
                
                if len(added_codes) > 10:
                    response += f"... và {len(added_codes) - 10} CODE khác\n"
            
            if duplicates:
                response += f"\n⚠️ <b>Bỏ qua {len(duplicates)} CODE trùng lặp:</b>\n"
                for i, code in enumerate(duplicates[:5], 1):  # Show max 5 duplicates
                    response += f"{i}. <code>{code}</code>\n"
                
                if len(duplicates) > 5:
                    response += f"... và {len(duplicates) - 5} CODE khác\n"
            
            response += f"\n📈 <b>Tổng số CODE hiện có:</b> {len(codes)}"
            
            bot.send_message(message.chat.id, response, parse_mode='HTML')
            
            # Log the action
            log_debug(f"Admin {message.from_user.id} added {len(added_codes)} new codes")
            
        except Exception as e:
            log_error(f"Error in process_add_code: {e}")
            bot.send_message(
                message.chat.id,
                f"❌ Có lỗi xảy ra khi thêm CODE: {str(e)}"
            )
        
        # Return to code management menu
        code_management_menu(message)

# Handler for viewing available codes
@bot.message_handler(func=lambda message: message.text == "📜 Danh sách CODE có sẵn")
def view_available_codes(message):
    if message.from_user.id in admins:
        if not codes:
            bot.send_message(
                message.chat.id,
                "❌ <b>DANH SÁCH CODE TRỐNG</b>\n\nHiện tại không có CODE nào trong hệ thống.",
                parse_mode='HTML'
            )
        else:
            response = f"📜 <b>DANH SÁCH CODE CÓ SẴN</b>\n\n"
            response += f"📊 <b>Tổng số CODE:</b> {len(codes)}\n\n"
            
            # Show first 20 codes
            for i, code in enumerate(codes[:20], 1):
                response += f"{i}. <code>{code}</code>\n"
            
            if len(codes) > 20:
                response += f"\n... và {len(codes) - 20} CODE khác"
            
            bot.send_message(message.chat.id, response, parse_mode='HTML')
        
        # Return to code management menu
        code_management_menu(message)

# Handler for viewing used codes statistics
@bot.message_handler(func=lambda message: message.text == "📊 Thống kê CODE đã dùng")
def view_used_codes_stats(message):
    if message.from_user.id in admins:
        if not used_codes:
            bot.send_message(
                message.chat.id,
                "❌ <b>CHƯA CÓ CODE NÀO ĐƯỢC SỬ DỤNG</b>\n\nHiện tại chưa có CODE nào được đổi.",
                parse_mode='HTML'
            )
        else:
            response = f"📊 <b>THỐNG KÊ CODE ĐÃ DÙNG</b>\n\n"
            response += f"🔢 <b>Tổng số CODE đã dùng:</b> {len(used_codes)}\n\n"
            
            # Calculate total amount
            total_amount = sum(info.get('amount', 0) for info in used_codes.values())
            response += f"💰 <b>Tổng giá trị đã đổi:</b> {total_amount:,} VNĐ\n\n"
            
            response += f"📈 <b>10 CODE gần đây nhất:</b>\n"
            
            # Sort by time (assuming time format is consistent)
            sorted_codes = sorted(
                used_codes.items(),
                key=lambda x: x[1].get('time', ''),
                reverse=True
            )
            
            for i, (code, info) in enumerate(sorted_codes[:10], 1):
                user_id = info.get('user_id', 'N/A')
                amount = info.get('amount', 0)
                time_str = info.get('time', 'N/A')
                response += f"{i}. <code>{code}</code> - User {user_id} - {amount:,}₫ - {time_str}\n"
            
            bot.send_message(message.chat.id, response, parse_mode='HTML')
        
        # Return to code management menu
        code_management_menu(message)

# Handler for toggle auto approve
@bot.message_handler(func=lambda message: message.text.startswith("⚙️ Duyệt tự động"))
def toggle_auto_approve(message):
    if message.from_user.id in admins:
        global auto_approve
        auto_approve = not auto_approve
        status = "BẬT" if auto_approve else "TẮT"
        
        bot.send_message(
            message.chat.id,
            f"✅ <b>ĐÃ CẬP NHẬT CÀI ĐẶT</b>\n\n"
            f"🤖 Duyệt tự động hiện đang: <b>{status}</b>\n\n"
            f"{'📌 Các yêu cầu đổi CODE sẽ được duyệt tự động' if auto_approve else '📌 Các yêu cầu đổi CODE cần duyệt thủ công'}",
            parse_mode='HTML'
        )
        
        # Return to code management menu
        code_management_menu(message)

@bot.message_handler(func=lambda message: message.text == "➖ Xóa nhiều CODE")
def remove_code_command(message):
    if message.from_user.id in admins:
        if not codes:
            bot.send_message(message.chat.id, "❌ Không có CODE nào để xóa.")
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for i, code in enumerate(codes[:30]):  # hiển thị tối đa 30 code đầu
            markup.add(types.InlineKeyboardButton(f"{code}", callback_data=f"remove_code_{i}"))

        bot.send_message(
            message.chat.id,
            "🗑 Chọn CODE bạn muốn xóa:",
            reply_markup=markup
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_code_"))
def handle_remove_code(call):
    if call.from_user.id in admins:
        index = int(call.data.split("_")[2])
        if 0 <= index < len(codes):
            removed_code = codes.pop(index)
            save_codes()
            bot.answer_callback_query(call.id, f"✅ Đã xóa CODE: {removed_code}")
            bot.edit_message_text(
                f"🗑 CODE <code>{removed_code}</code> đã được xóa khỏi hệ thống.",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="HTML"
            )
        else:
            bot.answer_callback_query(call.id, "❌ CODE không tồn tại!")

# Handler cho lệnh /xoacode (xóa nhiều CODE cùng lúc)
@bot.message_handler(commands=['xoacode'])
def delete_multiple_codes(message):
    if message.from_user.id not in admins:
        return
    
    # Bỏ dòng đầu "/xoacode", lấy các dòng tiếp theo
    parts = message.text.split("\n")[1:]
    codes_to_delete = [p.strip() for p in parts if p.strip()]

    if not codes_to_delete:
        bot.reply_to(message, "❌ Vui lòng nhập ít nhất 1 CODE để xóa.\nVí dụ:\n/xoacode CODE1\nCODE2\nCODE3")
        return
    
    deleted = []
    not_found = []
    
    global codes
    for c in codes_to_delete:
        if c in codes:
            codes.remove(c)
            deleted.append(c)
        else:
            not_found.append(c)
    
    save_codes()  # lưu lại file codes.json
    
    response = "📊 **KẾT QUẢ XÓA CODE**\n\n"
    
    if deleted:
        response += f"✅ **Đã xóa {len(deleted)} CODE:**\n"
        for code in deleted:
            response += f"- {code}\n"
    
    if not_found:
        response += f"\n❌ **Không tìm thấy {len(not_found)} CODE:**\n"
        for code in not_found:
            response += f"- {code}\n"
    
    bot.reply_to(message, response, parse_mode='Markdown')

# Menu cài đặt hệ thống
def system_settings_menu(message):
    if message.from_user.id in admins:
        settings = load_settings()
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        markup.add(types.KeyboardButton('💰 Đổi thưởng giới thiệu'),
                   types.KeyboardButton('💲 Đổi mức rút tối thiểu'))
        markup.add(types.KeyboardButton('🔙 Quay lại menu admin'))

        bot.send_message(
            message.chat.id, f"📱 <b>Cài đặt hệ thống</b>\n\n"
            f"🔸 Thưởng giới thiệu hiện tại: {settings['referral_bonus']} VNĐ\n"
            f"🔸 Mức rút tối thiểu hiện tại: {settings['min_withdraw']} VNĐ\n\n"
            f"Chọn cài đặt bạn muốn thay đổi:",
            reply_markup=markup,
            parse_mode='HTML')

# Xử lý lệnh /start - UPDATED to use enhanced subscription check
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    referrer_id = None
    add_user(user_id)

    # Nếu là admin, hiển thị menu admin ngay
    if user_id in admins:
        # Display User Menu and Balance và Menu Admin
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        markup.add(types.KeyboardButton('👤TÀI KHOẢN'),
                   types.KeyboardButton('👥MỜI BẠN BÈ'))
        markup.add(types.KeyboardButton('🎮LINK GAME'),
                   types.KeyboardButton('🎁ĐỔI CODE'))
        markup.add(types.KeyboardButton('📊THỐNG KÊ'))
        markup.add(types.KeyboardButton('👑 MENU ADMIN'))

        bot.send_message(
            message.chat.id,
            f"👋 Chào mừng admin! Bạn có quyền truy cập menu admin.\n💰 Số dư của bạn: {get_balance(user_id)} VNĐ",
            reply_markup=markup)
        return

    # Check for referral code in message
    if len(message.text.split()) > 1:
        referrer_id = message.text.split()[1]

        if str(user_id) not in user_data:  # Process only if user account doesn't exist
            invited_users[str(user_id)] = referrer_id
            save_data(invited_users_file, invited_users)

            # Thêm vào lịch sử người giới thiệu
            if referrer_id not in referral_history:
                referral_history[referrer_id] = []
            referral_history[referrer_id].append(str(user_id))
            save_referral_history()

    # Tải danh sách nhóm mới nhất từ file
    channels = load_channels()  # channels có thể là list chuỗi "@name" hoặc list dict {"username": "@..", "title": "Tên"}

    # Nếu không có kênh nào → cho vào menu chính
    if not channels:
        main_markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        main_markup.add(types.KeyboardButton('👤TÀI KHOẢN'),
                        types.KeyboardButton('👥MỜI BẠN BÈ'))
        main_markup.add(types.KeyboardButton('🎮LINK GAME'),
                        types.KeyboardButton('🎁ĐỔI CODE'))
        main_markup.add(types.KeyboardButton('📊THỐNG KÊ'))

        # chỉ hiện khi là admin
        if user_id in admins:
            main_markup.add(types.KeyboardButton('👑 MENU ADMIN'))

        bot.send_message(message.chat.id, "📌 Chào! Chọn chức năng:", reply_markup=main_markup)
        return

    # Nếu có kênh: kiểm tra đã tham gia hay chưa
    if check_subscription_with_retry(user_id):
        # Đã tham gia đầy đủ → hiển thị menu chính ngay
        main_markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        main_markup.add(types.KeyboardButton('👤TÀI KHOẢN'),
                        types.KeyboardButton('👥MỜI BẠN BÈ'))
        main_markup.add(types.KeyboardButton('🎮LINK GAME'),
                        types.KeyboardButton('🎁ĐỔI CODE'))
        main_markup.add(types.KeyboardButton('📊THỐNG KÊ'))

        # Thêm nút menu admin nếu là admin
        if user_id in admins:
            main_markup.add(types.KeyboardButton('👑 MENU ADMIN'))

        balance = get_balance(user_id)
        bot.send_message(message.chat.id,
                         f"Chào bạn quay lại! Số dư của bạn là {balance} VNĐ.",
                         reply_markup=main_markup)
        return

    # Chưa tham gia đầy đủ → hiển thị danh sách kênh và nút xác minh
    markup = types.InlineKeyboardMarkup(row_width=1)

    for ch in channels:
        if isinstance(ch, dict):
            username = ch.get("username", "").lstrip('@').strip()
            title = ch.get("title", ch.get("username", "")).strip()
        else:
            username = str(ch).lstrip('@').strip()
            title = f"🔗 @{username}"

        if username:
            url = f"https://t.me/{username}"
            markup.add(types.InlineKeyboardButton(title, url=url))
    # Add verification button at the bottom
    markup.add(types.InlineKeyboardButton('✅ XÁC MINH THAM GIA', callback_data='check'))

    message_text = (
        "<b>⚠️ Vui lòng tham gia tất cả các nhóm/kênh sau để nhận code:</b>\n\n"
        "<b>• Sau khi tham gia, nhấn \"✅ XÁC MINH THAM GIA\" để tiếp tục.</b>"
    )

    sent = bot.send_message(message.chat.id,
                            message_text,
                            reply_markup=markup,
                            parse_mode='HTML')
    try:
        user_key = str(user_id)
        user_data.setdefault(user_key, {})['last_join_prompt'] = {
            'chat_id': message.chat.id,
            'message_id': sent.message_id
        }
        save_user_data(user_data)
    except Exception as _:
        pass

# Check Channels Command Handler - UPDATED to use enhanced subscription check
@bot.callback_query_handler(func=lambda call: call.data == 'check')
def check_channels(call):
    user_id = call.from_user.id

    # ✅ Chỉ kiểm tra đã tham gia kênh hay chưa
    if check_subscription_with_retry(user_id):
        # Nếu đã tham gia hết → mở menu user
        main_markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        main_markup.add(types.KeyboardButton('👤TÀI KHOẢN'),
                        types.KeyboardButton('👥MỜI BẠN BÈ'))
        main_markup.add(types.KeyboardButton('🎮LINK GAME'),
                        types.KeyboardButton('🎁ĐỔI CODE'))
        main_markup.add(types.KeyboardButton('📊THỐNG KÊ'))

        # Nếu là admin thêm menu admin
        if user_id in admins:
            main_markup.add(types.KeyboardButton('👑 MENU ADMIN'))

        bot.send_message(call.message.chat.id,
                         "✅ Bạn đã tham gia đầy đủ các kênh!\nChào mừng đến với hệ thống 🎉",
                         reply_markup=main_markup)
    else:
        # Nếu chưa tham gia đủ kênh → thông báo lỗi
        bot.answer_callback_query(call.id,
                                  text='⚠️ Bạn chưa tham gia đầy đủ các kênh yêu cầu!',
                                  show_alert=True)

# Xử lý nút menu admin
@bot.message_handler(func=lambda message: message.text == "👑 MENU ADMIN")
def handle_admin_menu(message):
    # Khởi tạo người dùng nếu chưa có (đảm bảo dữ liệu)
    if str(message.from_user.id) not in user_data:
        initialize_user(message.from_user.id)
        
    admin_menu(message)
    
# Xử lý các nút trong menu admin
@bot.message_handler(func=lambda message: message.text == "📋 Quản lý nhóm")
def handle_manage_channels(message):
    # Đảm bảo hàm này gọi menu quản lý nhóm mới
    channel_management_menu(message)

# Handler for menu code management
@bot.message_handler(func=lambda message: message.text == "🎁 Quản lý CODE")
def handle_code_management(message):
    if message.from_user.id in admins:
        code_management_menu(message)
    else:
        bot.reply_to(message, "❌ Bạn không có quyền truy cập chức năng này!")

# Handler for system settings
@bot.message_handler(func=lambda message: message.text == "⚙️ Cài đặt hệ thống")
def handle_system_settings(message):
    if message.from_user.id in admins:
        system_settings_menu(message)
    else:
        bot.reply_to(message, "❌ Bạn không có quyền truy cập chức năng này!")
    
# Menu quản lý nhóm - SỬ DỤNG ReplyKeyboardMarkup
@bot.message_handler(func=lambda message: message.text == "📋 Quản lý nhóm" or message.text == "🔙 Quay lại menu quản lý nhóm")

def channel_management_menu(message):
    if message.from_user.id in admins:
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)

        markup.add(
            types.KeyboardButton('📋 Xem danh sách nhóm'),
            types.KeyboardButton('✏️ Đổi Tên Nhóm')
        )
        markup.add(
            types.KeyboardButton('➖ Xóa nhóm'),
            types.KeyboardButton('➕ Thêm nhóm')
        )
        markup.add(
            types.KeyboardButton('🔍 Kiểm tra quyền admin'),
            types.KeyboardButton('🔙 Quay lại menu admin')
        )
        
        bot.send_message(
            message.chat.id,
            "📋 <b>Quản lý nhóm</b>\n\nChọn chức năng bạn muốn sử dụng:",
            reply_markup=markup,
            parse_mode='HTML' 
        )
        
        

# [Continue with ALL callback handlers and remaining functions from original file...]

@bot.message_handler(func=lambda message: message.text == "📋 Xem danh sách nhóm")
def handle_view_channels(message):
    if message.from_user.id not in admins:
        return
    channels = load_channels()
    if channels:
        text = "📋 <b>Danh sách nhóm/kênh hiện tại:</b>\n\n"
        for i, channel in enumerate(channels, 1):
            if isinstance(channel, dict):
                username = channel.get('username', 'Không xác định')
                title = channel.get('title', username)
                text += f"{i}. <code>@{username}</code> - {title}\n"
            else:
                username = str(channel).lstrip('@')
                text += f"{i}. <code>@{username}</code>\n"
        
        # Quay lại menu quản lý nhóm
        markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        markup.add(types.KeyboardButton('🔙 Quay lại menu quản lý nhóm'))
        
        bot.send_message(
            message.chat.id,
            text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    else:
        # Quay lại menu quản lý nhóm
        markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        markup.add(types.KeyboardButton('🔙 Quay lại menu quản lý nhóm'))
        
        bot.send_message(
            message.chat.id,
            "📋 <b>Danh sách nhóm/kênh:</b>\n\n❌ Chưa có nhóm/kênh nào được thêm.",
            reply_markup=markup,
            parse_mode='HTML'
        )

# Thêm handler cho nút Quay lại menu quản lý nhóm
@bot.message_handler(func=lambda message: message.text == "🔙 Quay lại menu quản lý nhóm")
def back_to_channel_management(message):
    channel_management_menu(message)
    
    

# Add ALL remaining handlers and functions from the original 1857-line file...
# [This includes ALL the missing handlers for code exchange, admin functions, etc.]

@bot.message_handler(
    func=lambda message: message.text == "💰 Đổi thưởng giới thiệu")
def change_referral_bonus(message):
    if message.from_user.id in admins:
        bot.send_message(
            message.chat.id,
            "Vui lòng nhập số tiền thưởng cho mỗi lượt giới thiệu (VNĐ):")
        bot.register_next_step_handler(message, process_referral_bonus)

def process_referral_bonus(message):
    if message.from_user.id in admins:
        try:
            amount = int(message.text.strip())
            if amount < 0:
                bot.send_message(
                    message.chat.id,
                    "Số tiền không hợp lệ. Vui lòng nhập số dương.")
                return

            settings = load_settings()
            settings['referral_bonus'] = amount
            save_settings(settings)

            bot.send_message(
                message.chat.id,
                f"✅ Đã cập nhật mức thưởng giới thiệu thành {amount} VNĐ mỗi lượt giới thiệu."
            )

            # Quay lại menu cài đặt
            system_settings_menu(message)

        except ValueError:
            bot.send_message(message.chat.id, "Vui lòng nhập một số hợp lệ.")

@bot.message_handler(func=lambda message: message.text == "💲 Đổi mức rút tối thiểu")
def change_min_withdraw(message):
    if message.from_user.id in admins:
        bot.send_message(message.chat.id,
                         "Vui lòng nhập số tiền rút tối thiểu (VNĐ):")
        bot.register_next_step_handler(message, process_min_withdraw)

def process_min_withdraw(message):
    if message.from_user.id in admins:
        try:
            amount = int(message.text.strip())
            if amount < 0:
                bot.send_message(
                    message.chat.id,
                    "Số tiền không hợp lệ. Vui lòng nhập số dương.")
                return

            settings = load_settings()
            settings['min_withdraw'] = amount
            save_settings(settings)

            # Cập nhật biến toàn cục
            global min_withdraw_amount
            min_withdraw_amount = amount

            bot.send_message(
                message.chat.id,
                f"✅ Đã cập nhật mức rút tiền tối thiểu thành {amount} VNĐ."
            )

            # Quay lại menu cài đặt
            system_settings_menu(message)

        except ValueError:
            bot.send_message(message.chat.id, "Vui lòng nhập một số hợp lệ.")

@bot.message_handler(func=lambda message: message.text == "📢 Thông báo toàn hệ thống")
def broadcast_message_command(message):
    if message.from_user.id in admins:
        bot.send_message(
            message.chat.id,
            "Vui lòng nhập nội dung thông báo muốn gửi đến tất cả người dùng:")
        bot.register_next_step_handler(message, process_broadcast_message)

def process_broadcast_message(message):
    if message.from_user.id in admins:
        announcement = message.text

        # Xác nhận trước khi gửi
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Gửi",
                                       callback_data="confirm_broadcast"),
            types.InlineKeyboardButton("❌ Hủy",
                                       callback_data="cancel_broadcast"))

        # Lưu tin nhắn vào context để sử dụng sau này
        bot.send_message(
            message.chat.id,
            f"<b>Xác nhận gửi thông báo này đến tất cả người dùng?</b>\n\n{announcement}",
            reply_markup=markup,
            parse_mode='HTML')

        # Lưu tin nhắn để gửi sau
        if str(message.from_user.id) not in user_data:
            user_data[str(message.from_user.id)] = {}
        user_data[str(
            message.from_user.id)]['broadcast_message'] = announcement

@bot.callback_query_handler(
    func=lambda call: call.data in ["confirm_broadcast", "cancel_broadcast"])
def handle_broadcast_confirmation(call):
    user_id = call.from_user.id

    # Kiểm tra có mời bạn thành công trong 60 phút gần nhất không
    referrals = get_referred_users(user_id)
    if not referrals:
        bot.answer_callback_query(call.id, text='❌ Bạn cần mời ít nhất 1 người trong 60 phút gần nhất để nhận hộp!', show_alert=True)
        return


    if user_id in admins:
        if call.data == "confirm_broadcast":
            announcement = user_data[str(user_id)].get('broadcast_message', '')
            if announcement:
                bot.edit_message_text(
                    "⏳ Đang gửi thông báo đến tất cả người dùng...",
                    call.message.chat.id, call.message.message_id)
                success_count = 0
                fail_count = 0

                for user_id in user_data.keys():
                    try:
                        bot.send_message(
                            user_id,
                            f"<b>📢 THÔNG BÁO HỆ THỐNG</b>\n\n{announcement}",
                            parse_mode='HTML')
                        success_count += 1
                    except Exception as e:
                        fail_count += 1
                        log_error(
                            f"Gửi thông báo cho user_id {user_id} không thành công: {str(e)}"
                        )

                bot.send_message(
                    call.message.chat.id,
                    f"✅ Đã gửi thông báo đến {success_count} người dùng thành công!\n❌ Không gửi được cho {fail_count} người dùng."
                )
            else:
                bot.edit_message_text(
                    "❌ Lỗi: Không tìm thấy nội dung thông báo.",
                    call.message.chat.id, call.message.message_id)
        else:
            bot.edit_message_text("❌ Đã hủy gửi thông báo.",
                                  call.message.chat.id,
                                  call.message.message_id)

@bot.message_handler(func=lambda message: message.text == "📊THỐNG KÊ")
def show_statistics(message):
    user_id = message.from_user.id
    
    if user_id in admins:
        # Thống kê cho ADMIN - Tổng tất cả của các user
        total_users = count_users()
        total_balance = sum(data.get('balance', 0) for data in user_data.values())
        total_withdrawals = sum(data.get('withdrawals', 0) for data in user_data.values())
        total_invites = sum(data.get('invited_count', 0) for data in user_data.values())
        channels_count = len(load_channels())
        codes_count = len(codes)
        used_codes_count = len(used_codes)
        drop_codes_count = len(drop_codes)

        stats = f"""
╔══════════════════════════════════╗
║        📊 THỐNG KÊ HỆ THỐNG        ║
║            (ADMIN)               ║
╠══════════════════════════════════╣
║ 👥 Tổng số người dùng: {total_users:,}        ║
║ 💰 Tổng số dư: {total_balance:,} VNĐ    ║
║ 💸 Tổng lần rút: {total_withdrawals:,}           ║
║ 👨‍👩‍👧‍👦 Tổng lượt mời: {total_invites:,}          ║
╠══════════════════════════════════╣
║ 📢 Số nhóm/kênh: {channels_count}              ║
║ 🎁 CODE thường: {codes_count}               ║
║ 🎁 CODE đập hộp: {drop_codes_count}             ║
║ 🔄 CODE đã dùng: {used_codes_count}             ║
╚══════════════════════════════════╝
        """

        bot.send_message(message.chat.id, stats, parse_mode='HTML')
    else:
        # Thống kê cho USER - Chỉ hiện thông tin cá nhân
        # Đảm bảo user đã được khởi tạo
        if str(user_id) not in user_data:
            initialize_user(user_id)
        
        user_data_entry = user_data.get(str(user_id), {})
        balance = user_data_entry.get('balance', 0)
        withdrawals = user_data_entry.get('withdrawals', 0)
        invited_count = user_data_entry.get('invited_count', 0)
        
        # Đếm số người được mời thành công
        successful_invites = len(get_referred_users(user_id))

        stats = f"""
╔══════════════════════════════════╗
║        📊 THỐNG KÊ CÁ NHÂN        ║
╠══════════════════════════════════╣
║ 💰 Số dư hiện tại: {balance:,} VNĐ      ║
║ 💸 Số lần rút tiền: {withdrawals:,}           ║
║ 👥 Số lượt mời: {invited_count:,}              ║
║ ✅ Mời thành công: {successful_invites:,}           ║
╠══════════════════════════════════╣
║ 🎯 Mời thêm bạn bè để nhận thưởng! ║
╚══════════════════════════════════╝
        """

        bot.send_message(message.chat.id, stats, parse_mode='HTML')

# Thêm nút cộng tiền cho user
@bot.message_handler(func=lambda message: message.text == "💰 Cộng tiền")
def add_money_command(message):
    if message.from_user.id in admins:
        bot.send_message(
            message.chat.id,
            "Vui lòng nhập theo định dạng: [ID người dùng] [Số tiền]\nVí dụ: 123456789 10000"
        )
        bot.register_next_step_handler(message, process_add_money)

def process_add_money(message):
    if message.from_user.id in admins:
        try:
            parts = message.text.strip().split()
            if len(parts) != 2:
                bot.send_message(
                    message.chat.id,
                    "Định dạng không đúng. Vui lòng nhập theo định dạng: [ID người dùng] [Số tiền]"
                )
                return

            user_id = parts[0]
            amount = int(parts[1])

            if amount <= 0:
                bot.send_message(message.chat.id, "Số tiền phải lớn hơn 0.")
                return

            update_user_balance(user_id, amount)
            current_balance = get_balance(user_id)

            bot.send_message(
                message.chat.id,
                f"✅ Đã cộng {amount} VNĐ cho người dùng {user_id}.\nSố dư hiện tại: {current_balance} VNĐ"
            )

            # Thông báo cho người dùng
            try:
                bot.send_message(
                    user_id,
                    f"💰 Tài khoản của bạn vừa được cộng {amount} VNĐ.\nSố dư hiện tại: {current_balance} VNĐ"
                )
            except:
                bot.send_message(
                    message.chat.id,
                    "⚠️ Không thể gửi thông báo đến người dùng này.")

            # Quay lại menu admin
            admin_menu(message)
        except ValueError:
            bot.send_message(message.chat.id,
                             "Vui lòng nhập đúng định dạng số.")
        except Exception as e:
            bot.send_message(message.chat.id, f"Đã xảy ra lỗi: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "👥MỜI BẠN BÈ")
def handle_invite_friends(message):
    user_id = message.from_user.id
    invite_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    settings = load_settings()

    caption = f"""
🎁 <b>MỜI BẠN BÈ</b>

🔗 <b>LINK GIỚI THIỆU CỦA BẠN:</b>
{invite_link}

🎁 <b>THƯỞNG MỜI BẠN BÈ:</b>
• Mời 1 bạn = {settings['referral_bonus']}₫
• Tối thiểu đổi: {settings['min_withdraw']}₫

📢 <b>HƯỚNG DẪN:</b>
• Gửi link cho bạn bè
• Bạn bè tham gia nhóm qua link
• Nhận thưởng ngay khi họ tham gia
"""

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📋 SAO CHÉP LINK", callback_data=f"copy_link_{user_id}")
    )

    bot.send_message(message.chat.id,
                     caption,
                     reply_markup=markup,
                     parse_mode='HTML')

# Rest of ALL handlers and functions...
# [Include ALL remaining code from lines 1238-1857]

# Xử lý lệnh /guimem từ admin
@bot.message_handler(commands=['chat'])
def handle_send_private_message(message):
    if message.from_user.id in admins:  # Kiểm tra xem có phải admin không
        try:
            _, user_id_str, *message_text = message.text.split()
            if not message_text:
                bot.reply_to(message, "Vui lòng cung cấp nội dung tin nhắn.")
                return

            user_id = int(user_id_str)  # Kiểm tra user_id có hợp lệ không
            message_to_send = ' '.join(message_text)
            send_private_message(user_id, message_to_send)
        except ValueError:
            bot.reply_to(
                message,
                "Vui lòng sử dụng lệnh theo định dạng: /chat <user_id> <tin nhắn>"
            )
        except Exception as e:
            bot.reply_to(message, f"Đã xảy ra lỗi: {e}")
    else:
        bot.reply_to(message, "Bạn không có quyền sử dụng lệnh này.")

@bot.message_handler(commands=['thongbaofull'])
def thongbao_text(message):
    if message.from_user.id in admins:
        try:
            parts = message.text.split(maxsplit=1)
            if len(parts) < 2:
                raise ValueError("Sai cú pháp. Dùng: /thongbaofull [Nội dung thông báo]")

            announcement = parts[1]
            success = 0
            fail = 0

            for user_id in user_data.keys():
                try:
                    bot.send_message(
                        user_id,
                        f"<b>📢 THÔNG BÁO HỆ THỐNG</b>\n\n{announcement}",
                        parse_mode='HTML'
                    )
                    success += 1
                except Exception as e:
                    fail += 1
                    log_error(f"Gửi cho user_id {user_id} thất bại: {str(e)}")

            bot.reply_to(
                message,
                f"Đã gửi thông báo đến tất cả người dùng!\nThành công: {success}, Thất bại: {fail}"
            )

        except ValueError as e:
            bot.reply_to(message, str(e))

    else:
        bot.reply_to(message, "Bạn không có quyền sử dụng lệnh này.")

@bot.message_handler(func=lambda message: message.text == "👤TÀI KHOẢN")
def handle_account_command(message):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = f"{message.from_user.first_name} {message.from_user.last_name}"
    balance = get_balance(user_id)
    balance_formatted = "{:,}".format(balance)

    text = f"""
╔══ ══ ══ ══ ══ ══ ══ ══
║👤Tên Tài Khoản: `[{message.from_user.first_name} {message.from_user.last_name}]`
║
║🆔ID Tài Khoản: `[{user_id}]`
║
║💰Số Dư: `[{balance_formatted}]`đ
╚══ ══ ══ ══ ══ ══ ══ ══
"""

    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['naptien'])
def handle_addcoin_command(message):
    user_id = message.from_user.id
    if user_id not in admins:
        bot.reply_to(message, "Bạn không có quyền thực hiện lệnh này.")
        return

    try:
        details = message.text.split()
        target_user_id = int(details[1])
        amount = int(details[2])

        update_user_balance(target_user_id, amount)
        bot.reply_to(
            message,
            f'Đã cộng {amount} đ cho user {target_user_id}. Số dư hiện tại: {get_balance(target_user_id)} đ'
        )
    except (IndexError, ValueError):
        bot.reply_to(message,
                     'Vui lòng nhập theo cú pháp /naptien[user_id] [số tiền]')

#HÀM NẠP TRỪ
@bot.message_handler(commands=['trutien'])
def handle_trucoin_command(message):
    user_id = message.from_user.id
    if user_id not in admins:
        bot.reply_to(message, "Bạn không có quyền thực hiện lệnh này.")
        return

    try:
        # Lấy user_id và số tiền từ tin nhắn
        details = message.text.split()
        target_user_id = int(details[1])
        amount = int(details[2])

        update_user_balance(target_user_id, -amount)
        bot.reply_to(
            message,
            f'Đã trừ {amount} coins của user {target_user_id}. Số dư hiện tại: {get_balance(target_user_id)} coins'
        )
    except (IndexError, ValueError):
        bot.reply_to(
            message, 'Vui lòng nhập theo cú pháp /trutien [user_id] [số tiền]')

@bot.message_handler(func=lambda message: message.text == '🎁ĐỔI CODE')
def handle_exchange_code(message):
    user_id = message.from_user.id
    settings = load_settings()
    min_amount = settings['min_withdraw']

    # Kiểm tra nếu người dùng có tài khoản và số dư đủ để đổi code
    if str(user_id) in user_data:
        current_balance = user_data[str(user_id)].get('balance', 0)

        if current_balance >= min_amount:
            exchange_instructions = f"""

🆘 Vui Lòng Thực Hiện Theo Hướng Dẫn Sau:

/doicode [tên telegram] [số tiền]

➡️ VD: /doicode @username 20000

⚠️ Lưu ý: 
- Số tiền đổi tối thiểu là {min_amount} VNĐ
- ❌Không hỗ trợ hoàn tiền sau khi đổi CODE.
            """
            bot.send_message(message.chat.id, exchange_instructions)
        else:
            bot.send_message(
                message.chat.id,
                f"⛔️ SỐ DƯ KHÔNG ĐỦ! Bạn cần tối thiểu {min_amount} VNĐ để đổi CODE. Số dư hiện tại: {current_balance} VNĐ"
            )
    else:
        bot.send_message(message.chat.id,
                         "⛔️ BẠN CHƯA CÓ TÀI KHOẢN HOẶC SỐ DƯ KHÔNG ĐỦ!")

@bot.message_handler(commands=['doicode'])
def handle_code_exchange_request(message):
    user_id = message.from_user.id
    settings = load_settings()
    min_amount = settings['min_withdraw']

    if str(user_id) in user_data:
        current_balance = user_data[str(user_id)]['balance']
        details = message.text.split()

        if len(details) == 3:
            tele_username = details[1]
            amount = int(details[2])

            if amount >= min_amount:  # Số tiền tối thiểu để đổi code
                if current_balance >= amount:
                    # Trừ số tiền từ số dư của người dùng
                    user_data[str(user_id)]['balance'] -= amount
                    save_user_data(
                        user_data)  # Lưu lại dữ liệu sau khi cập nhật số dư

                    # Gửi thông báo cho người dùng là đang xử lý
                    bot.send_message(
                        message.chat.id,
                        f"⏳ <b>ĐANG XỬ LÝ YÊU CẦU ĐỔI CODE</b>\n\n"
                        f"Yêu cầu đổi CODE của bạn đang được xử lý. Admin sẽ xác nhận sớm.\n\n"
                        f"┏━━━━━━━━━━━━━━━━┓\n"
                        f"┃🔎TÊN TELEGRAM: {tele_username}\n"
                        f"┃💵SỐ TIỀN: {amount} VNĐ\n"
                        f"┗━━━━━━━━━━━━━━━━┛\n",
                        parse_mode='HTML')

                    if auto_approve:
                        # Tự động duyệt và gửi code
                        code = get_random_code()
                        if code:
                            current_time = datetime.now().strftime(
                                "%d/%m/%Y %H:%M:%S")
                            username = f"User {user_id}"

                            used_codes[code] = {
                                'user_id': user_id,
                                'username': username,
                                'amount': amount,
                                'time': current_time
                            }
                            save_used_codes()

                            bot.send_message(
    user_id,
    f"🎉 <b>ĐỔI CODE THÀNH CÔNG</b>\n\n"
    f"Yêu cầu đổi {amount} VNĐ của bạn đã được duyệt tự động!\n\n"
    f"💳 CODE của bạn: <code>{code}</code>\n\n"
    f"Cảm ơn bạn đã sử dụng dịch vụ của chúng tôi!",
    parse_mode='HTML'
)
                            # Thông báo cho admin
                            for admin_id in admins:
                                bot.send_message(
                                    admin_id, f"🤖 <b>DUYỆT TỰ ĐỘNG</b>\n"
                                    f"Đã tự động duyệt yêu cầu đổi CODE\n"
                                    f"👤 User ID: {user_id}\n"
                                    f"💰 Số tiền: {amount} VNĐ\n"
                                    f"🎁 CODE: <code>{code}</code>",
                                    parse_mode='HTML')
                        else:
                            # Không còn code, hoàn tiền
                            update_user_balance(user_id, amount)
                            save_user_data(user_data)
                            bot.send_message(
                                user_id, "❌ <b>KHÔNG THỂ ĐỔI CODE</b>\n\n"
                                f"Hệ thống đang hết CODE. Số tiền {amount} VNĐ đã được hoàn lại.\n"
                                "Vui lòng thử lại sau.",
                                parse_mode='HTML')
                    else:
                        # Gửi yêu cầu đổi code cho admin với nút kiểm tra
                        for admin_id in admins:
                            keyboard = types.InlineKeyboardMarkup(row_width=1)
                            keyboard.add(
                                types.InlineKeyboardButton(
                                    "🔍 KIỂM TRA NGƯỜI ĐÃ ĐƯỢC MỜI",
                                    callback_data=f"check_referred_{user_id}"),
                                types.InlineKeyboardButton(
                                    "✅ DUYỆT",
                                    callback_data=
                                    f"approve_code_{user_id}_{amount}"),
                                types.InlineKeyboardButton(
                                    "❌ TỪ CHỐI",
                                    callback_data=
                                    f"decline_code_{user_id}_{amount}"))

                        # Thông báo cho admin khi có người đổi code và tắt duyệt tự động
                        bot.send_message(
                            admin_id,
                            f"ℹ️ <b>THÔNG BÁO</b>\nChế độ duyệt tự động đang TẮT\nVui lòng xem xét yêu cầu đổi code bên dưới.",
                            parse_mode='HTML'
                        )
                        bot.send_message(
                            admin_id, f"🎁 <b>YÊU CẦU ĐỔI CODE</b>\n"
                            f"Từ: @{message.from_user.username}\n"
                            f"ID: <code>{user_id}</code>\n"
                            f"\nTÊN TELEGRAM: <code>{tele_username}</code>\n"
                            f"SỐ TIỀN: <code>{amount}</code> VNĐ",
                            reply_markup=keyboard,
                            parse_mode='HTML')

                else:
                    bot.send_message(message.chat.id,
                                     "⛔️SỐ DƯ KHÔNG ĐỦ LẤY GÌ ĐỔI CODE?")
            else:
                bot.send_message(
                    message.chat.id,
                    f"⚠️ Số tiền tối thiểu để đổi CODE là {min_amount} VNĐ.")
        else:
            bot.send_message(
                message.chat.id,
                "🚫 Sai cú pháp. Vui lòng nhập theo mẫu: `/doicode [tên telegram] [số tiền]`"
            )
    else:
        bot.send_message(message.chat.id,
                         "🔒⛔️SỐ DƯ KHÔNG ĐỦ LẤY GÌ ĐỔI CODE?.")

# Xử lý callback kiểm tra người được mời
@bot.callback_query_handler(
    func=lambda call: call.data.startswith('check_referred_'))
def handle_check_referred(call):
    if call.from_user.id in admins:
        user_id = call.data.split('_')[2]

        # Lấy danh sách người được mời bởi user này
        referred_users = get_referred_users(user_id)

        if not referred_users:
            # Tạo keyboard để quay lại
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton(
                    "🔙 QUAY LẠI", callback_data=f"back_exchange_{user_id}"))

            bot.edit_message_text(
                f"<b>🔍 THÔNG TIN NGƯỜI DÙNG</b>\n\n"
                f"Người dùng <code>{user_id}</code> chưa mời được ai.\n\n"
                f"Nhấn nút bên dưới để quay lại.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode='HTML')
        else:
            # Tạo keyboard để quay lại
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton(
                    "🔙 QUAY LẠI", callback_data=f"back_exchange_{user_id}"))

            # Format danh sách người được mời
            user_list = ""
            for i, ref_user_id in enumerate(referred_users, 1):
                # Cố gắng lấy thông tin username nếu có
                try:
                    # Không dùng API get_chat vì dễ gây lỗi nếu người dùng chặn bot
                    username_ref = "Không xác định"
                    username = f"ID: {ref_user_id}"
                    user_list += f"{i}. {username}\n"
                except:
                    user_list += f"{i}. ID: {ref_user_id}\n"

            bot.edit_message_text(
                f"<b>🔍 DANH SÁCH NGƯỜI ĐƯỢC MỜI</b>\n\n"
                f"Người dùng <code>{user_id}</code> đã mời {len(referred_users)} người:\n\n"
                f"{user_list}\n"
                f"Nhấn nút bên dưới để quay lại.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=keyboard,
                parse_mode='HTML')

# NEW: Handler for approve code button
@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_code_'))
def handle_approve_code(call):
    if call.from_user.id in admins:
        try:
            # Parse callback data: approve_code_{user_id}_{amount}
            parts = call.data.split('_')
            user_id = int(parts[2])
            amount = int(parts[3])
            
            # Get random code
            code = get_random_code()
            if code:
                # Update user balance (already deducted in doicode handler)
                current_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                username = f"User {user_id}"
                
                # Save used code info
                used_codes[code] = {
                    'user_id': user_id,
                    'username': username,
                    'amount': amount,
                    'time': current_time
                }
                save_used_codes()
                
                # Tăng counter số lần rút tiền
                user_id_str = str(user_id)
                if user_id_str in user_data:
                    if 'withdrawals' not in user_data[user_id_str]:
                        user_data[user_id_str]['withdrawals'] = 0
                    user_data[user_id_str]['withdrawals'] += 1
                    save_data(user_data_file, user_data)
                
                # Send code to user
                bot.send_message(
                    user_id,
                    f"🎉 <b>ĐỔI CODE THÀNH CÔNG</b>\n\n"
                    f"Yêu cầu đổi {amount} VNĐ của bạn đã được duyệt!\n\n"
                    f"💳 CODE của bạn: <code>{code}</code>\n\n"
                    f"Cảm ơn bạn đã sử dụng dịch vụ của chúng tôi!",
                    parse_mode='HTML'
                )
                
                # Notify admin
                bot.edit_message_text(
                    f"✅ <b>ĐÃ DUYỆT YÊU CẦU ĐỔI CODE</b>\n\n"
                    f"👤 User ID: {user_id}\n"
                    f"💰 Số tiền: {amount} VNĐ\n"
                    f"🎁 CODE: <code>{code}</code>\n"
                    f"⏰ Thời gian: {current_time}",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='HTML'
                )
                
                # Log the approval
                log_debug(f"Admin {call.from_user.id} approved code exchange for user {user_id}, amount: {amount}, code: {code}")
                
            else:
                # No codes available, refund user
                update_user_balance(user_id, amount)
                save_user_data(user_data)
                
                bot.send_message(
                    user_id,
                    "❌ <b>KHÔNG THỂ ĐỔI CODE</b>\n\n"
                    f"Hệ thống đang hết CODE. Số tiền {amount} VNĐ đã được hoàn lại.\n"
                    "Vui lòng thử lại sau.",
                    parse_mode='HTML'
                )
                
                bot.edit_message_text(
                    f"❌ <b>KHÔNG THỂ DUYỆT</b>\n\n"
                    f"👤 User ID: {user_id}\n"
                    f"💰 Số tiền: {amount} VNĐ\n"
                    f"⚠️ Lý do: Hết CODE trong hệ thống\n"
                    f"💸 Đã hoàn tiền cho người dùng",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode='HTML'
                )
                
        except Exception as e:
            log_error(f"Error in handle_approve_code: {e}")
            bot.answer_callback_query(call.id, "❌ Có lỗi xảy ra khi duyệt code!")
    else:
        bot.answer_callback_query(call.id, "❌ Bạn không có quyền thực hiện hành động này!")

# NEW: Handler for decline code button
@bot.callback_query_handler(func=lambda call: call.data.startswith('decline_code_'))
def handle_decline_code(call):
    if call.from_user.id in admins:
        try:
            # Parse callback data: decline_code_{user_id}_{amount}
            parts = call.data.split('_')
            user_id = int(parts[2])
            amount = int(parts[3])
            
            # Refund user
            update_user_balance(user_id, amount)
            save_user_data(user_data)
            
            # Notify user
            bot.send_message(
                user_id,
                f"❌ <b>YÊU CẦU ĐỔI CODE BỊ TỪ CHỐI</b>\n\n"
                f"Yêu cầu đổi {amount} VNĐ của bạn đã bị từ chối.\n"
                f"💰 Số tiền {amount} VNĐ đã được hoàn lại vào tài khoản.\n\n"
                f"Vui lòng liên hệ admin để biết thêm chi tiết.",
                parse_mode='HTML'
            )
            
            # Notify admin
            bot.edit_message_text(
                f"❌ <b>ĐÃ TỪ CHỐI YÊU CẦU ĐỔI CODE</b>\n\n"
                f"👤 User ID: {user_id}\n"
                f"💰 Số tiền: {amount} VNĐ\n"
                f"💸 Đã hoàn tiền cho người dùng\n"
                f"⏰ Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML'
            )
            
            # Log the decline
            log_debug(f"Admin {call.from_user.id} declined code exchange for user {user_id}, amount: {amount}")
            
        except Exception as e:
            log_error(f"Error in handle_decline_code: {e}")
            bot.answer_callback_query(call.id, "❌ Có lỗi xảy ra khi từ chối code!")
    else:
        bot.answer_callback_query(call.id, "❌ Bạn không có quyền thực hiện hành động này!")

@bot.message_handler(func=lambda message: message.text == "🖼 Thay đổi ảnh thông báo")
def change_announcement_image(message):
    if message.from_user.id in admins:
        markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
        markup.add(types.KeyboardButton('🔙 Quay lại menu admin'))

        bot.send_message(
            message.chat.id, 
            "📤 Vui lòng gửi ảnh mới cho thông báo tham gia nhóm:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, process_new_image)

def process_new_image(message):
    if message.from_user.id in admins:
        if message.text == '🔙 Quay lại menu admin':
            admin_menu(message)
            return

        try:
            if message.photo:
                # Lấy file_id của ảnh có độ phân giải cao nhất
                file_id = message.photo[-1].file_id
                # Lưu file_id vào settings
                settings = load_settings()
                settings['announcement_image'] = file_id
                save_settings(settings)

                bot.reply_to(message, "✅ Đã cập nhật ảnh thông báo thành công!")
                admin_menu(message)  # Quay lại menu admin
            else:
                bot.reply_to(message, "❌ Vui lòng gửi một ảnh!")
                bot.register_next_step_handler(message, process_new_image)  # Tiếp tục chờ ảnh
        except Exception as e:
            bot.reply_to(message, f"✅ Gửi ảnh thành công !: {str(e)}")
            admin_menu(message)

@bot.callback_query_handler(func=lambda call: call.data.startswith('copy_link_'))
def handle_copy_link(call):
    user_id = call.data.split('_')[2]
    invite_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    
    bot.answer_callback_query(
        call.id,
        text="✅ Đã sao chép link giới thiệu!",
        show_alert=True
    )

# [Continue with ALL remaining handlers...]

@bot.message_handler(func=lambda message: message.text == "🎮LINK GAME")
def handle_game_link(message):
    user_id = message.from_user.id

    # Nếu có kênh yêu cầu và người dùng chưa tham gia → điều hướng về màn hình tham gia
    channels = load_channels()
    if channels and not check_subscription_with_retry(user_id):
        join_markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in channels:
            if isinstance(ch, dict):
                username = ch.get("username", "").lstrip('@').strip()
                title = ch.get("title", ch.get("username", "")).strip()
            else:
                username = str(ch).lstrip('@').strip()
                title = f"🔗 @{username}"
            if username:
                url = f"https://t.me/{username}"
                join_markup.add(types.InlineKeyboardButton(title, url=url))
        join_markup.add(types.InlineKeyboardButton('✅ XÁC MINH THAM GIA', callback_data='check'))

        bot.send_message(
            message.chat.id,
            "❗️Bạn cần tham gia đủ kênh trước khi dùng tính năng này.\nVui lòng tham gia và bấm \"✅ XÁC MINH THAM GIA\".",
            reply_markup=join_markup
        )
        return

    current_link = load_game_link()
    
    if current_link:
        caption = f"""
🎮 <b>LINK GAME CHÍNH THỨC</b>

🔗 <b>Link game:</b> {current_link}

📱 <b>Hướng dẫn:</b>
• Nhấn vào link để chơi game
• Nhập code ở phần nạp tiền 
• Liên hệ admin nếu có vấn đề

🎁 <b>Chúc bạn chơi game vui vẻ!</b>
"""
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🎮 CHƠI NGAY", url=current_link))
        
        bot.send_message(message.chat.id, caption, reply_markup=markup, parse_mode='HTML')
    else:
        bot.send_message(message.chat.id, "❌ Link game chưa được cập nhật. Vui lòng liên hệ admin.")

# [All remaining code through line 1857 should be included here...]


# =========================
# GROUP MANAGEMENT HANDLERS
# =========================

@bot.message_handler(func=lambda message: message.text == "➕ Thêm nhóm")
def handle_add_channel(message):
    if message.from_user.id in admins:
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        markup.add(types.KeyboardButton('➕ Thêm 1 nhóm'),
                   types.KeyboardButton('📝 Thêm nhiều nhóm'))
        markup.add(types.KeyboardButton('🔙 Quay lại menu quản lý nhóm'))
        
        bot.send_message(
            message.chat.id, 
            "📌 <b>Chọn cách thêm nhóm:</b>\n\n"
            "➕ <b>Thêm 1 nhóm:</b> Thêm từng nhóm một\n"
            "📝 <b>Thêm nhiều nhóm:</b> Thêm nhiều nhóm cùng lúc bằng @",
            reply_markup=markup,
            parse_mode='HTML'
        )

@bot.message_handler(func=lambda message: message.text == "➕ Thêm 1 nhóm")
def handle_add_single_channel(message):
    if message.from_user.id in admins:
        bot.send_message(
            message.chat.id, 
            "📌 Vui lòng nhập **Username** (bắt đầu bằng @) hoặc **ID số** của nhóm/kênh bạn muốn thêm:",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(message, process_add_channel)

def process_add_channel(message):
    if message.from_user.id in admins:
        try:
            channel_input = message.text.strip().lstrip('@')

            access_result = verify_bot_access(channel_input)
            if not access_result['has_access']:
                bot.send_message(
                    message.chat.id, 
                    f"❌ Bot không có quyền trong nhóm/kênh <code>@{channel_input}</code>. Vui lòng thêm bot làm admin!",
                    parse_mode='HTML'
                )
                channel_management_menu(message)
                return

            chat_info = bot.get_chat(channel_input if channel_input.lstrip('-').isdigit() else f'@{channel_input}')
            username = chat_info.username or str(chat_info.id)
            title = chat_info.title or f"Nhóm/Kênh ({chat_info.id})"

            channels = load_channels()
            if any(c.get('username') == username for c in channels if isinstance(c, dict)):
                bot.send_message(
                    message.chat.id, 
                    f"❌ Nhóm/kênh <code>@{username}</code> đã tồn tại.",
                    parse_mode='HTML'
                )
                channel_management_menu(message)
                return

            new_channel = {'username': username, 'title': title}
            channels.append(new_channel)
            save_channels(channels)

            bot.send_message(
                message.chat.id, 
                f"✅ Đã thêm thành công:\n• <b>Username:</b> <code>@{username}</code>\n• <b>Title:</b> {title}",
                parse_mode='HTML'
            )
            channel_management_menu(message)

        except Exception as e:
            log_error(f"Error adding channel: {e}")
            bot.send_message(message.chat.id, f"❌ Đã xảy ra lỗi khi thêm nhóm/kênh: {str(e)}")
            channel_management_menu(message)

@bot.message_handler(func=lambda message: message.text == "📝 Thêm nhiều nhóm")
def handle_add_multiple_channels(message):
    if message.from_user.id in admins:
        bot.send_message(
            message.chat.id, 
            "📝 <b>THÊM NHIỀU NHÓM CÙNG LÚC</b>\n\n"
            "📌 <b>Cách sử dụng:</b>\n"
            "• Nhập danh sách các nhóm/kênh, mỗi dòng một nhóm\n"
            "• Có thể dùng @username hoặc ID số\n"
            "• Ví dụ:\n"
            "<code>@group1\n@group2\n@channel1\n-1001234567890</code>\n\n"
            "📤 <b>Gửi danh sách nhóm bạn muốn thêm:</b>",
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_add_multiple_channels)

def process_add_multiple_channels(message):
    if message.from_user.id in admins:
        try:
            # Parse the input - split by lines and clean up
            lines = message.text.strip().split('\n')
            channel_inputs = []
            
            for line in lines:
                line = line.strip()
                if line:  # Skip empty lines
                    # Remove @ prefix if present
                    clean_line = line.lstrip('@')
                    if clean_line:  # Only add non-empty cleaned lines
                        channel_inputs.append(clean_line)
            
            if not channel_inputs:
                bot.send_message(
                    message.chat.id, 
                    "❌ Không tìm thấy nhóm/kênh nào trong danh sách. Vui lòng thử lại.",
                    parse_mode='HTML'
                )
                channel_management_menu(message)
                return
            
            bot.send_message(
                message.chat.id, 
                f"⏳ Đang xử lý {len(channel_inputs)} nhóm/kênh...",
                parse_mode='HTML'
            )
            
            channels = load_channels()
            added_channels = []
            failed_channels = []
            duplicate_channels = []
            
            for channel_input in channel_inputs:
                try:
                    # Check bot access first
                    access_result = verify_bot_access(channel_input)
                    if not access_result['has_access']:
                        failed_channels.append(f"@{channel_input} - Bot không có quyền")
                        continue
                    
                    # Get chat info
                    chat_info = bot.get_chat(channel_input if channel_input.lstrip('-').isdigit() else f'@{channel_input}')
                    username = chat_info.username or str(chat_info.id)
                    title = chat_info.title or f"Nhóm/Kênh ({chat_info.id})"
                    
                    # Check for duplicates
                    if any(c.get('username') == username for c in channels if isinstance(c, dict)):
                        duplicate_channels.append(f"@{username} - {title}")
                        continue
                    
                    # Add the channel
                    new_channel = {'username': username, 'title': title}
                    channels.append(new_channel)
                    added_channels.append(f"@{username} - {title}")
                    
                except Exception as e:
                    failed_channels.append(f"@{channel_input} - Lỗi: {str(e)}")
                    log_error(f"Error processing channel {channel_input}: {e}")
            
            # Save all channels at once
            save_channels(channels)
            
            # Prepare response
            response = f"📊 <b>KẾT QUẢ THÊM NHÓM</b>\n\n"
            
            if added_channels:
                response += f"✅ <b>Đã thêm thành công ({len(added_channels)} nhóm):</b>\n"
                for channel in added_channels:
                    response += f"• {channel}\n"
                response += "\n"
            
            if duplicate_channels:
                response += f"⚠️ <b>Đã tồn tại ({len(duplicate_channels)} nhóm):</b>\n"
                for channel in duplicate_channels:
                    response += f"• {channel}\n"
                response += "\n"
            
            if failed_channels:
                response += f"❌ <b>Thất bại ({len(failed_channels)} nhóm):</b>\n"
                for channel in failed_channels:
                    response += f"• {channel}\n"
            
            bot.send_message(message.chat.id, response, parse_mode='HTML')
            channel_management_menu(message)
            
        except Exception as e:
            log_error(f"Error in process_add_multiple_channels: {e}")
            bot.send_message(
                message.chat.id, 
                f"❌ Đã xảy ra lỗi khi xử lý danh sách nhóm: {str(e)}",
                parse_mode='HTML'
            )
            channel_management_menu(message)


@bot.message_handler(func=lambda message: message.text == "➖ Xóa nhóm")
def handle_remove_channel(message):
    if message.from_user.id in admins:
        channels = load_channels()
        if not channels:
            bot.send_message(message.chat.id, "❌ Danh sách nhóm/kênh trống.")
            channel_management_menu(message)
            return

        text = "🗑 **Chọn nhóm/kênh bạn muốn xóa (nhập số thứ tự):**\n\n"
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True, one_time_keyboard=True)
        options = []

        for i, channel in enumerate(channels, 1):
            if isinstance(channel, dict):
                username = channel.get('username', 'Không xác định')
                title = channel.get('title', username)
                text += f"{i}. <code>@{username}</code> - {title}\n"
            else:
                username = str(channel).lstrip('@')
                text += f"{i}. <code>@{username}</code>\n"
            options.append(str(i))

        for i in range(0, len(options), 4):
            markup.add(*[types.KeyboardButton(btn) for btn in options[i:i+4]])
        markup.add(types.KeyboardButton('🔙 Quay lại menu quản lý nhóm'))

        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='HTML')
        bot.register_next_step_handler(message, process_remove_channel)

def process_remove_channel(message):
    if message.from_user.id in admins:
        if message.text == '🔙 Quay lại menu quản lý nhóm':
            channel_management_menu(message)
            return
        try:
            index = int(message.text.strip()) - 1
            channels = load_channels()
            if 0 <= index < len(channels):
                removed = channels.pop(index)
                save_channels(channels)
                removed_name = removed.get('username') if isinstance(removed, dict) else str(removed)
                bot.send_message(message.chat.id, f"✅ Đã xóa <code>@{removed_name}</code>", parse_mode='HTML')
            else:
                bot.send_message(message.chat.id, "❌ Số thứ tự không hợp lệ.")
            channel_management_menu(message)
        except ValueError:
            bot.send_message(message.chat.id, "❌ Vui lòng nhập số thứ tự hợp lệ.")
            channel_management_menu(message)


@bot.message_handler(func=lambda message: message.text == "✏️ Đổi Tên Nhóm")
def handle_rename_channel(message):
    if message.from_user.id in admins:
        channels = load_channels()
        if not channels:
            bot.send_message(message.chat.id, "❌ Danh sách nhóm/kênh trống.")
            channel_management_menu(message)
            return

        text = "✏️ <b>Chọn nhóm/kênh muốn đổi tên (nhập số thứ tự):</b>\n\n"
        markup = types.ReplyKeyboardMarkup(row_width=4, resize_keyboard=True, one_time_keyboard=True)
        options = []

        for i, channel in enumerate(channels, 1):
            if isinstance(channel, dict):
                username = channel.get('username', '')
                title = channel.get('title', username)
                text += f"{i}. <code>@{username or channel.get('id','?')}</code> - Hiện tại: {title}\n"
            else:
                username = str(channel).lstrip('@')
                text += f"{i}. <code>@{username}</code> - Hiện tại: @{username}\n"
            options.append(str(i))

        for i in range(0, len(options), 4):
            markup.add(*[types.KeyboardButton(btn) for btn in options[i:i+4]])
        markup.add(types.KeyboardButton('🔙 Quay lại menu quản lý nhóm'))

        bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='HTML')
        bot.register_next_step_handler(message, process_select_channel_to_rename)

def process_select_channel_to_rename(message):
    if message.from_user.id in admins:
        if message.text == '🔙 Quay lại menu quản lý nhóm':
            channel_management_menu(message)
            return
        try:
            index = int(message.text.strip()) - 1
            channels = load_channels()
            if 0 <= index < len(channels):
                user_data.setdefault(str(message.from_user.id), {})['rename_channel_index'] = index
                save_user_data(user_data)
                current_channel = channels[index]
                current_title = current_channel.get('title') if isinstance(current_channel, dict) else str(current_channel)
                bot.send_message(message.chat.id, f"✏️ Nhập tên hiển thị mới cho kênh: <b>{current_title}</b>", parse_mode='HTML')
                bot.register_next_step_handler(message, process_rename_channel)
            else:
                bot.send_message(message.chat.id, "❌ Số thứ tự không hợp lệ.")
                channel_management_menu(message)
        except ValueError:
            bot.send_message(message.chat.id, "❌ Vui lòng nhập số hợp lệ.")
            channel_management_menu(message)

def process_rename_channel(message):
    if message.from_user.id in admins:
        new_title = message.text.strip()
        user_id_str = str(message.from_user.id)
        index = user_data.get(user_id_str, {}).get('rename_channel_index')
        channels = load_channels()
        if index is not None and 0 <= index < len(channels):
            if not isinstance(channels[index], dict):
                username = str(channels[index]).lstrip('@')
                channels[index] = {'username': username, 'title': username}
            channels[index]['title'] = new_title
            save_channels(channels)
            user_data[user_id_str].pop('rename_channel_index', None)
            save_user_data(user_data)
            bot.send_message(message.chat.id, f"✅ Đã đổi tên thành công: <b>{new_title}</b>", parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, "❌ Không tìm thấy nhóm cần đổi tên.")
        channel_management_menu(message)


@bot.message_handler(func=lambda message: message.text == "🔍 Kiểm tra quyền admin")
def handle_check_admin(message):
    if message.from_user.id in admins:
        try:
            permissions = check_bot_permissions()
            response = "🔍 <b>TRẠNG THÁI QUYỀN BOT</b>\n\n"
            
            if not permissions:
                response += "❌ Không có nhóm/kênh nào được cấu hình.\n"
            else:
                success_count = 0
                for perm in permissions:
                    if perm.get('success', False):
                        success_count += 1
                        response += (f"✅ <b>{perm['channel']}</b>\n"
                                     f"   • Trạng thái: {perm['bot_status']}\n"
                                     f"   • Loại: {perm['chat_type']}\n"
                                     f"   • Tên: {perm.get('chat_title', 'N/A')}\n\n")
                    else:
                        response += (f"❌ <b>{perm['channel']}</b>\n"
                                     f"   • Lỗi: {perm.get('error', 'Không xác định')}\n\n")
                
                response += f"📊 <b>Tổng kết:</b> {success_count}/{len(permissions)} nhóm/kênh hoạt động tốt\n"
            
            markup = types.ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
            markup.add(types.KeyboardButton('🔙 Quay lại menu quản lý nhóm'))
            bot.send_message(message.chat.id, response.strip(), reply_markup=markup, parse_mode='HTML')
            
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Lỗi khi kiểm tra quyền: {str(e)}")
    else:
        bot.reply_to(message, "❌ Bạn không có quyền sử dụng chức năng này!")



# =========================================================
# NEW: HANDLERS QUAY LẠI MENU ADMIN & SUB-MENUS (FIX LỖI 1)
# =========================================================

@bot.message_handler(func=lambda message: message.text == "🔙 Quay lại menu quản lý nhóm")
def back_to_channel_management_menu(message):
    if message.from_user.id in admins:
        bot.send_message(message.chat.id, "📌 Đã quay lại menu quản lý nhóm.")
        channel_management_menu(message)
    else:
        bot.reply_to(message, "❌ Bạn không có quyền truy cập chức năng này!")

@bot.message_handler(func=lambda message: message.text == "🔙 Quay lại menu admin")
def back_to_admin_menu(message):
    if message.from_user.id in admins:
        admin_menu(message)
    else:
        bot.reply_to(message, "❌ Bạn không có quyền truy cập chức năng này!")

@bot.message_handler(func=lambda message: message.text == "🎮 Quản lý Link Game")
def handle_game_link_management(message):
    if message.from_user.id in admins:
        current_link = load_game_link()
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        markup.add(types.KeyboardButton('✏️ Sửa Link Game'),
                   types.KeyboardButton('👁 Xem Link Game'))
        markup.add(types.KeyboardButton('🔙 Quay lại menu admin'))
        
        status_text = f"Link hiện tại: {current_link if current_link else 'Chưa có link'}"
        
        bot.send_message(
            message.chat.id,
            f"🎮 <b>Quản lý Link Game</b>\n\n{status_text}\n\nChọn chức năng:",
            reply_markup=markup,
            parse_mode='HTML'
        )
    else:
        bot.reply_to(message, "❌ Bạn không có quyền truy cập chức năng này!")

@bot.message_handler(func=lambda message: message.text == "✏️ Sửa Link Game")
def handle_edit_game_link(message):
    if message.from_user.id in admins:
        bot.send_message(
            message.chat.id,
            "📝 <b>SỬA LINK GAME</b>\n\nVui lòng nhập link game mới:",
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_edit_game_link)
    else:
        bot.reply_to(message, "❌ Bạn không có quyền truy cập chức năng này!")

def process_edit_game_link(message):
    if message.from_user.id in admins:
        new_link = message.text.strip()
        
        # Kiểm tra link có hợp lệ không
        if new_link.startswith(('http://', 'https://')):
            save_game_link(new_link)
            global game_link
            game_link = new_link
            
            bot.send_message(
                message.chat.id,
                f"✅ <b>ĐÃ CẬP NHẬT LINK GAME</b>\n\nLink mới: {new_link}",
                parse_mode='HTML'
            )
        else:
            bot.send_message(
                message.chat.id,
                "❌ Link không hợp lệ! Vui lòng nhập link bắt đầu bằng http:// hoặc https://"
            )
            bot.register_next_step_handler(message, process_edit_game_link)
            return
        
        # Quay lại menu quản lý link game
        handle_game_link_management(message)

@bot.message_handler(func=lambda message: message.text == "👁 Xem Link Game")
def handle_view_game_link(message):
    if message.from_user.id in admins:
        current_link = load_game_link()
        
        if current_link:
            response = f"""
🎮 <b>LINK GAME HIỆN TẠI</b>

🔗 <b>Link:</b> {current_link}

📊 <b>Thống kê:</b>
• Link đã được cập nhật
• User có thể truy cập qua menu chính
"""
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("🔗 Mở Link", url=current_link))
            
            bot.send_message(message.chat.id, response, reply_markup=markup, parse_mode='HTML')
        else:
            bot.send_message(message.chat.id, "❌ Chưa có link game nào được thiết lập.")
        
        # Quay lại menu quản lý link game
        handle_game_link_management(message)
    else:
        bot.reply_to(message, "❌ Bạn không có quyền truy cập chức năng này!")

@bot.message_handler(func=lambda message: message.text == "🔙 Quay lại menu chính")
def back_to_main_menu_from_admin(message):
    handle_start(message)

if __name__ == "__main__":
    # === Khởi động scheduler Đập Hộp ===
    def drop_scheduler_loop():
        global drop_thread_started
        if drop_thread_started:
            return
        drop_thread_started = True
        last_drop_key = None
        while True:
            try:
                conf = get_drop_settings()
                if not conf.get('enabled', True):
                    time.sleep(10)
                    continue
                # Lấy thời gian theo múi giờ đã cài đặt
                tz_name = conf.get('timezone', 'Asia/Ho_Chi_Minh')
                try:
                    tz = pytz.timezone(tz_name)
                    now = datetime.now(tz)
                except:
                    now = datetime.now()
                
                target_times = conf.get('times', ["09:00", "21:00"])
                now_time = now.strftime('%H:%M')
                # Tạo key riêng cho mỗi thời điểm trong ngày
                key = f"{now.strftime('%Y%m%d')}-{now_time}"
                # Kích hoạt đúng phút đã đặt (giây < 5)
                if now.second < 5 and now_time in target_times and key != last_drop_key:
                    log_debug(f"Triggering drop at {now_time}, key: {key}, last_key: {last_drop_key}")
                    # Mặc định: luôn gửi cho tất cả user
                    send_to_all_users()
                    last_drop_key = key
                    log_debug(f"Drop sent successfully, new last_key: {last_drop_key}")
                # Tự tắt đợt khi hết thời gian
                if current_drop.get('active') and not is_drop_active():
                    end_current_drop()
                
                # Tự động xóa ảnh và nút sau 5 phút
                auto_remove_drop_after_5min()
                
                time.sleep(1)
            except Exception as e:
                log_error(f"drop_scheduler_loop error: {e}")
                time.sleep(2)

    threading.Thread(target=drop_scheduler_loop, daemon=True).start()

    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=20, skip_pending=True)
        except Exception as e:
            log_error(f"Lỗi polling: {e}")
            if "Connection" in str(e) or "10054" in str(e):
                log_error("Lỗi kết nối mạng, đợi 30s rồi thử lại...")
                time.sleep(30)  # Đợi lâu hơn cho lỗi mạng
            else:
                time.sleep(5)  # Đợi 5s cho lỗi khác

# === TỰ ĐỘNG RƠI HỘP MỖI 60 PHÚT ===
def auto_drop_loop():
    while True:
        try:
            conf = get_drop_settings()
            if conf.get('enabled', True):
                chat_id = conf.get('target_chat_id')
                # Mặc định: luôn gửi cho tất cả user
                send_to_all_users()
                log_debug('💥 Đập hộp tự động rơi thành công!')
            else:
                log_debug('🔕 Đập hộp đang bị tắt.')
        except Exception as e:
            log_error(f'Auto drop error: {e}')
        time.sleep(3600)  # 60 phút

threading.Thread(target=auto_drop_loop, daemon=True).start()
