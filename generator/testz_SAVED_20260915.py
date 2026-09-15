#!/usr/bin/env python3

import os
import sys
import json
import time
import random
import string
import threading
import base64
import codecs
import re
import hmac
import hashlib
import signal
import socket
import shutil
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

socket.setdefaulttimeout(2.5)

_orig_getaddrinfo = socket.getaddrinfo
_dns_cache = {}
_dns_lock = threading.Lock()

def _cached_getaddrinfo(host, port, *args, **kwargs):
    key = (host, port)
    try:
        with _dns_lock:
            return _dns_cache[key]
    except KeyError:
        pass
    res = _orig_getaddrinfo(host, port, *args, **kwargs)
    with _dns_lock:
        _dns_cache[key] = res
    return res

socket.getaddrinfo = _cached_getaddrinfo

OPTIMIZATION = {
    'max_workers': 120,
    # FIX: 0.2s membunuh respons valid yang datang 300-800ms (RTT mobile
    # ke garena). read-timeout adaptif dipakai nyata di semua POST sekarang.
    # FIX delay Potato: 8000 workers + 20k pool di hp = thrash/OOM/FD habis -> delay. turun ke 120/200.
    'timeout': 2.0,
    'retries': 0,
    'no_delay': True,
    'pool_connections': 200,
    'pool_maxsize': 200,
}

class AdaptiveTimeout:
    # FIX delay Potato2: floor 1.5 = bunuh TLS mobile 1-2s (spurious timeout -> fail -> sleep -> delay).
    # base 2.5, decay lambat 0.98, naik cepat 1.3 tiap 4 fail.
    def __init__(self, base=2.5, lo=2.2, hi=5.0):
        self.value = base
        self.lo = lo
        self.hi = hi
        self.lock = threading.Lock()
        self.fails = 0

    def on_fail(self):
        with self.lock:
            self.fails += 1
            if self.fails >= 4:
                self.value = min(self.hi, self.value * 1.3)
                self.fails = 0

    def on_ok(self):
        with self.lock:
            self.fails = 0
            self.value = max(self.lo, self.value * 0.98)

    def get(self):
        with self.lock:
            return round(self.value, 2)

REQ = AdaptiveTimeout()

class VoidTheme:
    PRIMARY   = "\033[38;2;110;80;200m"
    SECONDARY = "\033[38;2;150;120;220m"
    ACCENT    = "\033[38;2;90;200;230m"
    WARNING   = "\033[38;2;255;180;100m"
    ERROR     = "\033[38;2;255;100;120m"
    INFO      = "\033[38;2;120;180;255m"
    SUCCESS   = "\033[38;2;100;220;170m"
    DARK      = "\033[38;2;15;10;30m"
    LIGHT     = "\033[38;2;255;255;255m"
    GRAY      = "\033[38;2;160;160;180m"
    DIM_GRAY  = "\033[38;2;80;80;100m"
    CYAN      = ACCENT
    PURPLE    = PRIMARY
    PINK      = "\033[38;2;235;120;200m"
    GOLD      = "\033[38;2;255;215;0m"
    RST       = "\033[0m"
    BOLD      = "\033[1m"
    DIM       = "\033[2m"
    INPUT     = "\033[38;2;255;215;0m"
    COUPLE    = "\033[38;2;255;105;180m"
    DARK_PURPLE = "\033[38;5;57m"
    X         = "\033[0m"
D = VoidTheme()

REGION_LANG = {
    "ME": "ar", "IND": "hi", "ID": "id", "VN": "vi",
    "TH": "th", "BD": "bn", "PK": "ur", "TW": "zh",
    "CIS": "ru", "SAC": "es", "BR": "pt"
}
HEX_KEY = bytes.fromhex("32656534343831396539623435393838343531343130363762323831363231383734643064356437616639643866376530306331653534373135623764316533")
_HIDDEN = "ZUYxTCP"

# ===================== KARAKTER SET =====================
VN_CHARS = [
    'a','à','á','ả','ã','ạ','ă','ằ','ắ','ẳ','ẵ','ặ','â','ầ','ấ','ẩ','ẫ','ậ',
    'b','c','d','đ','e','è','é','ẻ','ẽ','ẹ','ê','ề','ế','ể','ễ','ệ',
    'g','h','i','ì','í','ỉ','ĩ','ị','k','l','m','n',
    'o','ò','ó','ỏ','õ','ọ','ô','ồ','ố','ổ','ỗ','ộ','ơ','ờ','ớ','ở','ỡ','ợ',
    'p','q','r','s','t','u','ù','ú','ủ','ũ','ụ','ư','ừ','ứ','ử','ữ','ự',
    'v','x','y','ỳ','ý','ỷ','ỹ','ỵ',
    'A','À','Á','Ả','Ã','Ạ','Ă','Ằ','Ắ','Ẳ','Ẵ','Ặ','Â','Ầ','Ấ','Ẩ','Ẫ','Ậ',
    'B','C','D','Đ','E','È','É','Ẻ','Ẽ','Ẹ','Ê','Ề','Ế','Ể','Ễ','Ệ',
    'G','H','I','Ì','Í','Ỉ','Ĩ','Ị','K','L','M','N',
    'O','Ò','Ó','Ỏ','Õ','Ọ','Ô','Ồ','Ố','Ổ','Ỗ','Ộ','Ơ','Ờ','Ớ','Ở','Ỡ','Ợ',
    'P','Q','R','S','T','U','Ù','Ú','Ủ','Ũ','Ụ','Ư','Ừ','Ứ','Ử','Ữ','Ự',
    'V','X','Y','Ỳ','Ý','Ỷ','Ỹ','Ỵ'
]
CAMBO_CHARS = [
    'ក','ខ','គ','ឃ','ង','ច','ឆ','ជ','ឈ','ញ','ដ','ឋ','ឌ','ឍ','ណ','ត',
    'ថ','ទ','ធ','ន','ប','ផ','ព','ភ','ម','យ','រ','ល','វ','ឝ','ឞ','ស',
    'ហ','ឡ','អ','ឣ','ឤ','ឥ','ឦ','ឧ','ឨ','ឩ','ឪ','ឫ','ឬ','ឭ','ឮ','ឯ',
    'ឰ','ឱ','ឲ','ឳ','កា','ខា','គា','ឃា','ងា','ចា','ឆា','ជា','ឈា','ញា',
    'ដា','ឋា','ឌា','ឍា','ណា','តា','ថា','ទា','ធា','នា','បា','ផា','ពា',
    'ភា','មា','យា','រា','លា','វា','សា','ហា','ឡា','អា'
]
THAI_CHARS = [
    'ก','ข','ฃ','ค','ฅ','ฆ','ง','จ','ฉ','ช','ซ','ฌ','ญ','ฎ','ฏ','ฐ','ฑ','ฒ',
    'ณ','ด','ต','ถ','ท','ธ','น','บ','ป','ผ','ฝ','พ','ฟ','ภ','ม','ย','ร','ฤ',
    'ล','ว','ศ','ษ','ส','ห','ฬ','อ','ฮ',
    'ะ','ั','า','ำ','ิ','ี','ึ','ื','ุ','ู','เ','แ','โ','ใ','ไ','ๅ','ๆ','็',
    '่','้','๊','๋','์','ํ','ฺ','฿','ฯ','๏','๚','๛'
]
JEPANG_CHARS = [
    'あ','い','う','え','お','か','き','く','け','こ','さ','し','す','せ','そ',
    'た','ち','つ','て','と','な','に','ぬ','ね','の','は','ひ','ふ','へ','ほ',
    'ま','み','む','め','も','や','ゆ','よ','ら','り','る','れ','ろ','わ','を','ん',
    'ぁ','ぃ','ぅ','ぇ','ぉ','っ','ゃ','ゅ','ょ',
    'ア','イ','ウ','エ','オ','カ','キ','ク','ケ','コ','サ','シ','ス','セ','ソ',
    'タ','チ','ツ','テ','ト','ナ','ニ','ヌ','ネ','ノ','ハ','ヒ','フ','ヘ','ホ',
    'マ','ミ','ム','メ','モ','ヤ','ユ','ヨ','ラ','リ','ル','レ','ロ','ワ','ヲ','ン',
    'ァ','ィ','ゥ','ェ','ォ','ッ','ャ','ュ','ョ'
]
MANDARIN_CHARS = [
    '的','一','是','了','我','不','人','在','他','有','这','个','上','们','来',
    '到','时','大','地','为','子','中','你','说','生','国','年','着','就','那',
    '和','要','她','出','也','得','里','后','自','以','会','家','可','下','而',
    '过','天','去','能','对','小','多','然','于','心','学','么','之','都','好',
    '看','起','发','当','没','成','只','如','事','把','还','用','第','样','道',
    '想','作','种','开','手','爱','情','王','龙','虎','凤','皇','帝','君','子',
    '文','武','神','仙','魔','鬼','妖','灵','圣','贤','义','勇','忠','诚','信'
]
ALL_CHARS = VN_CHARS + CAMBO_CHARS + THAI_CHARS + JEPANG_CHARS + MANDARIN_CHARS

# ===== CONFIG + SUFFIX LANG (dari NYXORA V4) =====
CONFIG = {
    'suffix_lang': None,
}

LANGUAGE_CHAR_SETS = {
    'jp': 'あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん火水木金土月日花愛竜',
    'kh': 'កខគឃងចឆជឈញដឋឌឍណតថទធនបផពភមយរលវសហឡអ',
    'th': 'กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรฤลฦวศษสหฬอฮ',
    'cn': '一丁七万丈三上下不与丐丑专且丕世丘丙业丛东丝丞丟两严並丧丨丩个丫中丰串锕临丽举乃久乂么义之乌乍乎乏乐乒乓乔'
}

def get_language_char(lang):
    """Ambil random character dari language set (NYXORA V4)"""
    if lang == 'random':
        all_chars = ''.join(LANGUAGE_CHAR_SETS.values())
        return random.choice(all_chars)
    elif lang in LANGUAGE_CHAR_SETS:
        return random.choice(LANGUAGE_CHAR_SETS[lang])
    return ''

BASE_STORAGE = "/storage/emulated/0/AfriezXGENV4"
os.makedirs(BASE_STORAGE, exist_ok=True)

RARITY_FOLDERS = {
    "COMMON": os.path.join(BASE_STORAGE, "COMMON"),
    "UNCOMMON": os.path.join(BASE_STORAGE, "UNCOMMON"),
    "EPIC": os.path.join(BASE_STORAGE, "EPIC"),
    "LEGENDARY": os.path.join(BASE_STORAGE, "LEGENDARY"),
    "MYTHIC": os.path.join(BASE_STORAGE, "MYTHIC"),
}
for folder in RARITY_FOLDERS.values():
    os.makedirs(folder, exist_ok=True)

RARITY_FILES = {
    rarity: os.path.join(folder, f"{rarity.lower()}.json")
    for rarity, folder in RARITY_FOLDERS.items()
}

HUNTER_FOLDER = os.path.join(BASE_STORAGE, "HUNTER")
os.makedirs(HUNTER_FOLDER, exist_ok=True)
HUNTER_FILE = os.path.join(HUNTER_FOLDER, "hunter.jsonl")

COUPLE_BASIC_FOLDER = os.path.join(BASE_STORAGE, "COUPLE_BASIC")
COUPLE_RARE_FOLDER = os.path.join(BASE_STORAGE, "COUPLE_RARE")
os.makedirs(COUPLE_BASIC_FOLDER, exist_ok=True)
os.makedirs(COUPLE_RARE_FOLDER, exist_ok=True)

FILE_LOCK = threading.Lock()
EXIT = False

# ===== IP POOL 50K =====
IP_POOL_SIZE = 50000
FAKE_DEVICE_COUNT = 100

def _make_valid_ip():
    while True:
        a = random.randint(1, 223)
        if a in (10, 127):
            continue
        b = random.randint(0, 255)
        if a == 172 and 16 <= b <= 31:
            continue
        c = random.randint(0, 255)
        if a == 192 and b == 168:
            continue
        d = random.randint(1, 254)
        return f"{a}.{b}.{c}.{d}"

DEVICE_ANDROID = {
    "SM-A325M": "13","SM-A525F": "13","SM-A525M": "13","SM-A725F": "13","SM-A226B": "12",
    "SM-A536B": "13","SM-A736B": "13","SM-A325F": "12","SM-A725M": "12","SM-A226L": "12",
    "SM-A536E": "13","SM-A736E": "13","SM-M325F": "12","SM-M525F": "13","SM-G990B": "13",
    "SM-G998B": "13","SM-G991B": "13","SM-G981B": "12","SM-A137F": "12","SM-A237F": "13",
    "SM-A337F": "13","SM-A537F": "13","SM-A737F": "13","SM-A125F": "11","SM-A225F": "12",
    "SM-A135F": "12","SM-A235F": "13","SM-A335F": "13","SM-A535F": "13","SM-A735F": "13",
    "Redmi Note 10": "12","Redmi Note 11": "13","Redmi Note 12": "13","Redmi Note 8": "11",
    "Redmi Note 9": "11","Redmi Note 10 Pro": "12","Redmi Note 11 Pro": "13","Redmi Note 12 Pro": "13",
    "Redmi 9": "11","Redmi 10": "12","Redmi 10A": "12","Redmi 9A": "11","Poco X3": "11",
    "Poco X3 Pro": "12","Poco F3": "12","Poco M3": "11","Poco M4 Pro": "12","Poco X4 Pro": "12",
    "Xiaomi Mi 10T": "12","Xiaomi 11T": "12","Xiaomi Mi 11": "12","Xiaomi 12": "13",
    "Xiaomi 12 Pro": "13","Xiaomi Mi 11 Lite": "12","Realme 8": "12","Realme GT": "12",
    "Realme 7": "11","Realme 9": "12","Realme GT Neo": "12","Realme 8 Pro": "12",
    "Realme 9 Pro": "12","Realme Narzo 50": "12","Realme C25": "11","OnePlus 9": "12","OnePlus Nord": "12",
}

REGIONS = ["HK","ID","SG","MY","PH","TH","VN"]

def generate_user_agents(count):
    ua_list = []
    devices = list(DEVICE_ANDROID.items())
    i = 0
    while len(ua_list) < count:
        device, android = devices[i % len(devices)]
        region = REGIONS[(i // len(devices)) % len(REGIONS)]
        version = "4.0.39" if android in ["11","12"] else "4.0.40"
        ua = f"GarenaMSDK/{version}({device};Android {android};en;{region};)"
        ua_list.append(ua)
        i += 1
    return ua_list

USER_AGENTS = generate_user_agents(FAKE_DEVICE_COUNT)

# ===== GLOBAL SESSION (NYXORA V4 STYLE) =====
session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(
    pool_connections=OPTIMIZATION['pool_connections'],
    pool_maxsize=OPTIMIZATION['pool_maxsize'],
    max_retries=0,
    pool_block=False,
)
session.mount('https://', _adapter)
session.mount('http://', _adapter)
session.headers.update({
    'Accept': 'application/json',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
})
session.verify = False

IP_POOL = [_make_valid_ip() for _ in range(IP_POOL_SIZE)]

class IPSpoofer:
    # FIX: rotasi identitas nyata — sebelumnya random.choice dari pool 50K IP
    # tiap request, TAPI UA dipilih per-request dari 100 device yang sama,
    # pola fingerprint stabil (kombinasi UA+IP berulang di ambang ~120 akun
    # membuat endpoint curiga -> throttling). sekarang: identitas per-thread
    # di-rotate tiap N attempt (default 120, ambang smart-rotate), AMA
    # berbeda tiap request dalam satu identitas.
    def __init__(self):
        self.ua_list = USER_AGENTS[:FAKE_DEVICE_COUNT]
        self.pool = IP_POOL
        self.rotate_every = 120
        self._tls = threading.local()

    def _slot(self):
        s = getattr(self._tls, 's', None)
        if s is None:
            s = {"ua": random.choice(self.ua_list), "ip": random.choice(self.pool), "n": 0}
            self._tls.s = s
        s["n"] += 1
        if s["n"] >= self.rotate_every:
            s["ua"] = random.choice(self.ua_list)
            s["ip"] = random.choice(self.pool)
            s["n"] = 0
        return s

    def get_ua_and_ip(self):
        s = self._slot()
        return s["ua"], s["ip"]

    def get_ip(self):
        return self._slot()["ip"]

ip_spoofer = IPSpoofer()

# ===== VERCEL 5x250 API REAL (POTATO deep-check2) =====
# 5 grup x 250 slot = 1250 URL: /api/r1/1..250 ... /api/r5/1..250 (+ legacy /api/g/1..250).
# Total fungsi 9 (gen bulk patterns g r1-r5) <= 12 deploy ijo. Tiap grup 1 dynamic file.
VERCEL_BASE = "https://genafriezx.vercel.app"
VERCEL_GROUPS = ("r1", "r2", "r3", "r4", "r5")
VERCEL_API_COUNT = 250
VERCEL_APIS = [f"{VERCEL_BASE}/api/{g}/{i}" for g in VERCEL_GROUPS for i in range(1, VERCEL_API_COUNT + 1)]
VERCEL_GEN_FALLBACK = f"{VERCEL_BASE}/gen"
# Circuit breaker: vercel mock (token kosong) = dead weight 4-8s per akun. lewati otomatis.
# KILLER FIX wooosh: vercel MATI total sampai backend balikin JWT real. tag [APIxx] tetap instan tanpa network.
VERCEL_ENABLED = False
_VCB = {"fails": 0, "skip_until": 0.0}
_API_IDX = {"n": 0}
_API_LOCK = threading.Lock()
_VSESSION = None
_VSESSION_LOCK = threading.Lock()

def _vhttp():
    global _VSESSION
    if _VSESSION is None:
        with _VSESSION_LOCK:
            if _VSESSION is None:
                import requests as _rq
                s = _rq.Session()
                # FIX delay: pool 20/20 dibagi 80 thread = 60 thread antri koneksi. naik ke 100/100.
                a = _rq.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=0, pool_block=False)
                s.mount("https://", a)
                s.verify = False
                _VSESSION = s
    return _VSESSION

def _next_api():
    # round-robin 5 grup x 250 slot = 1250. return (grup, slot) buat URL + tag [APIg-slot].
    with _API_LOCK:
        _API_IDX["n"] = (_API_IDX["n"] % (len(VERCEL_GROUPS) * VERCEL_API_COUNT)) + 1
        n = _API_IDX["n"] - 1
        gi = (n // VERCEL_API_COUNT) % len(VERCEL_GROUPS)
        slot = (n % VERCEL_API_COUNT) + 1
        return VERCEL_GROUPS[gi], slot

def fetch_via_vercel(region, name_prefix, password_prefix, is_ghost=False, timeout_get=(2.0, 3.0)):
    # WOOOSH MODE: vercel off -> tag instan 0ms, langsung fallback lokal ID JWT asli. nyalain lagi pas backend real.
    grp, slot = _next_api()
    tag = f"{grp}-{slot}"
    if not VERCEL_ENABLED:
        return None, tag
    now = time.time()
    if now < _VCB["skip_until"]:
        return None, tag
    try:
        r = _vhttp().get(f"{VERCEL_BASE}/api/{grp}/{slot}", params={"name": name_prefix[:20], "count": 1, "region": region, "password_prefix": password_prefix, "ghost": "true" if is_ghost else "false", "detect_rare": "true"}, timeout=timeout_get)
        if r and r.status_code == 200:
            accs = r.json().get("accounts") or []
            if accs:
                a = accs[0]
                uid = str(a.get("uid", ""))
                token = str(a.get("token", "") or a.get("jwt_token", ""))
                aid = str(a.get("account_id", "") or uid)
                if uid.isdigit() and 10 <= len(uid) <= 12 and aid.isdigit() and 10 <= len(aid) <= 12 and token and len(token) >= 20:
                    _VCB["fails"] = 0
                    return {"uid": uid, "password": a.get("password", ""), "account_id": aid, "name": a.get("nickname", name_prefix), "region": "GHOST" if is_ghost else region, "status": "success", "jwt_token": token, "is_ghost": is_ghost}, tag
        _VCB["fails"] += 1
        if _VCB["fails"] >= 20:
            _VCB["skip_until"] = now + 60.0
            _VCB["fails"] = 0
    except Exception:
        _VCB["fails"] += 1
        if _VCB["fails"] >= 20:
            _VCB["skip_until"] = time.time() + 60.0
            _VCB["fails"] = 0
    return None, tag

def generate_exponent():
    exp_digits = {'0':'⁰','1':'¹','2':'²','3':'³','4':'⁴','5':'⁵','6':'⁶','7':'⁷','8':'⁸','9':'⁹'}
    num = random.randint(1, 9999)
    return ''.join(exp_digits[d] for d in f"{num:04d}")

# ===================== GENERATOR FUNCTIONS (NYXORA V4 LITERAL) =====================

def generate_random_name(base):
    """Generate nama seperti NYXORA V4"""
    prefix = base.upper()
    rand1 = random.choice(string.ascii_uppercase)
    rand2 = random.choice(string.ascii_uppercase)
    rand_num = random.randint(100, 999)
    name = f"{prefix}{rand1}{rand2}{rand_num}"
    suffix_lang = CONFIG.get('suffix_lang', None)
    if suffix_lang:
        name += get_language_char(suffix_lang)
    return name

def generate_password(password_prefix):
    """NYXORA V4 style: PREFIX_hex16"""
    prefix = password_prefix.upper() if password_prefix else "AFZX"
    rand_part = "".join(random.choices("0123456789ABCDEF", k=16))
    return f"{prefix}_{rand_part}"

def encode_varint(n):
    if n < 0: return b''
    result = []
    while True:
        byte = n & 0x7F
        n >>= 7
        if n: byte |= 0x80
        result.append(byte)
        if not n: break
    return bytes(result)

def create_proto_field(field_num, value):
    if isinstance(value, dict):
        nested = create_proto_field(field_num, value)
        header = (field_num << 3) | 2
        return encode_varint(header) + encode_varint(len(nested)) + nested
    elif isinstance(value, int):
        header = (field_num << 3) | 0
        return encode_varint(header) + encode_varint(value)
    elif isinstance(value, (str, bytes)):
        encoded_val = value.encode() if isinstance(value, str) else value
        header = (field_num << 3) | 2
        return encode_varint(header) + encode_varint(len(encoded_val)) + encoded_val
    return b''

def build_proto(fields):
    return b''.join(create_proto_field(k, v) for k, v in fields.items())

def aes_encrypt(hex_data):
    data = bytes.fromhex(hex_data)
    aes_key = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
    iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    return cipher.encrypt(pad(data, AES.block_size))

def encrypt_api(plain_hex):
    plain = bytes.fromhex(plain_hex)
    aes_key = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
    iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    return cipher.encrypt(pad(plain, AES.block_size)).hex()

PASS_PREFIXES = ["AF", "AFZ", "AFZX", "AFZ"]

def create_account(region, account_name, password_prefix, is_ghost):
    """NYXORA V4 LITERAL — pakai HMAC signature"""
    if EXIT: return None
    try:
        ua = ip_spoofer.get_ua_and_ip()[0]
        fake_ip = ip_spoofer.get_ip()
        password = generate_password(password_prefix)
        url = "https://100067.connect.garena.com/api/v2/oauth/guest:register"
        payload = {"app_id": 100067, "client_type": 2, "password": password, "source": 2}
        body_json = json.dumps(payload, separators=(",", ":"))
        signature = hmac.new(HEX_KEY, body_json.encode("utf-8"), hashlib.sha256).hexdigest()
        headers = {
            "User-Agent": ua,
            "Connection": "Keep-Alive",
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "Authorization": f"Signature {signature}",
            "Content-Type": "application/json; charset=utf-8",
            "Host": "100067.connect.garena.com",
            "X-Forwarded-For": fake_ip,
            "X-Real-IP": fake_ip,
        }
        try:
            response = _post(url, _stage="register", headers=headers, data=body_json, timeout=(3.5, REQ.get()))
            if response and response.status_code == 200:
                res_json = response.json()
                if "data" in res_json and "uid" in res_json["data"]:
                    uid = res_json["data"]["uid"]
                    return get_token(uid, password, region, account_name, password_prefix, ua, fake_ip, is_ghost)
        except Exception:
            pass
        return None
    except Exception:
        return None

def get_token(uid, password, region, account_name, password_prefix, ua=None, fake_ip=None, is_ghost=False):
    """NYXORA V4 LITERAL"""
    if EXIT: return None
    try:
        if ua is None: ua = ip_spoofer.get_ua_and_ip()[0]
        if fake_ip is None: fake_ip = ip_spoofer.get_ip()
        url = "https://100067.connect.garena.com/oauth/guest/token/grant"
        headers = {
            "Accept-Encoding": "gzip",
            "Connection": "Keep-Alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "100067.connect.garena.com",
            "User-Agent": ua,
            "X-Forwarded-For": fake_ip,
            "X-Real-IP": fake_ip,
        }
        body = {
            "uid": uid,
            "password": password,
            "response_type": "token",
            "client_type": "2",
            "client_secret": HEX_KEY,
            "client_id": "100067"
        }
        response = _post(url, _stage="token", headers=headers, data=body, timeout=(3.5, REQ.get()))
        if response and response.status_code == 200:
            data = response.json()
            if 'open_id' in data and 'access_token' in data:
                open_id = data['open_id']
                access_token = data["access_token"]
                keystream = [0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30]
                encoded = ""
                for i in range(len(open_id)):
                    encoded += chr(ord(open_id[i]) ^ keystream[i % len(keystream)])
                field = codecs.decode(''.join(c if 32 <= ord(c) <= 126 else f'\\u{ord(c):04x}' for c in encoded), 'unicode_escape').encode('latin1')
                return major_register(access_token, open_id, field, uid, password, region, account_name, password_prefix, ua, fake_ip, is_ghost)
        return None
    except Exception:
        return None

def major_register(access_token, open_id, field, uid, password, region, account_name, password_prefix, ua=None, fake_ip=None, is_ghost=False):
    """NYXORA V4 LITERAL"""
    if EXIT: return None
    try:
        if ua is None: ua = ip_spoofer.get_ua_and_ip()[0]
        if fake_ip is None: fake_ip = ip_spoofer.get_ip()
        if is_ghost:
            url = "https://loginbp.ggblueshark.com/MajorRegister"
        else:
            if region.upper() in ["ME", "TH"]:
                url = "https://loginbp.common.ggbluefox.com/MajorRegister"
            else:
                url = "https://loginbp.ggblueshark.com/MajorRegister"
        name = generate_random_name(account_name)
        headers = {
            "Accept-Encoding": "gzip",
            "Authorization": "Bearer",
            "Connection": "Keep-Alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "ReleaseVersion": "OB54",
            "User-Agent": ua,
            "X-GA": "v1 1",
            "X-Unity-Version": "2021.3.15f1",
            "X-Forwarded-For": fake_ip,
            "X-Real-IP": fake_ip,
        }
        lang_code = "en" if is_ghost else REGION_LANG.get(region.upper(), "en")
        payload = {1: name, 2: access_token, 3: open_id, 5: 102000007, 6: 4, 7: 1, 13: 1, 14: field, 15: lang_code, 16: 1, 17: 1}
        payload_bytes = build_proto(payload)
        encrypted_payload = aes_encrypt(payload_bytes.hex())
        _post(url, _stage="mreg", headers=headers, data=encrypted_payload, timeout=(3.5, REQ.get()))
        login_result = major_login(uid, password, access_token, open_id, region, ua, fake_ip, is_ghost)
        account_id = login_result.get("account_id", "N/A")
        jwt_token = login_result.get("jwt_token", "")
        if account_id != "N/A":
            if jwt_token and region.upper() != "BR":
                try:
                    force_region_bind(region, jwt_token, is_ghost)
                except:
                    pass
            return {
                "uid": uid,
                "password": password,
                "name": name,
                "region": "GHOST" if is_ghost else region,
                "status": "success",
                "account_id": account_id,
                "jwt_token": jwt_token,
                "is_ghost": is_ghost
            }
        return None
    except Exception:
        return None

def major_login(uid, password, access_token, open_id, region, ua=None, fake_ip=None, is_ghost=False):
    """NYXORA V4 LITERAL — dengan regex fallback"""
    try:
        if ua is None: ua = ip_spoofer.get_ua_and_ip()[0]
        if fake_ip is None: fake_ip = ip_spoofer.get_ip()
        lang = "en" if is_ghost else REGION_LANG.get(region.upper(), "en")
        payload_parts = [
            b'\x1a\x132025-08-30 05:19:21"\tfree fire(\x01:\x081.114.13B2Android OS 9 / API-28 (PI/rel.cjw.20220518.114133)J\x08HandheldR\nATM MobilsZ\x04WIFI`\xb6\nh\xee\x05r\x03300z\x1fARMv7 VFPv3 NEON VMH | 2400 | 2\x80\x01\xc9\x0f\x8a\x01\x0fAdreno (TM) 640\x92\x01\rOpenGL ES 3.2\x9a\x01+Google|dfa4ab4b-9dc4-454e-8065-e70c733fa53f\xa2\x01\x0e105.235.139.91\xaa\x01\x02',
            lang.encode("ascii"),
            b'\xb2\x01 1d8ec0240ede109973f3321b9354b44d\xba\x01\x014\xc2\x01\x08Handheld\xca\x01\x10Asus ASUS_I005DA\xea\x01@afcfbf13334be42036e4f742c80b956344bed760ac91b3aff9b607a610ab4390\xf0\x01\x01\xca\x02\nATM Mobils\xd2\x02\x04WIFI\xca\x03 7428b253defc164018c604a1ebbfebdf\xe0\x03\xa8\x81\x02\xe8\x03\xf6\xe5\x01\xf0\x03\xaf\x13\xf8\x03\x84\x07\x80\x04\xe7\xf0\x01\x88\x04\xa8\x81\x02\x90\x04\xe7\xf0\x01\x98\x04\xa8\x81\x02\xc8\x04\x01\xd2\x04=/data/app/com.dts.freefireth-PdeDnOilCSFn37p1AH_FLg==/lib/arm\xe0\x04\x01\xea\x04_2087f61c19f57f2af4e7feff0b24d9d9|/data/app/com.dts.freefireth-PdeDnOilCSFn37p1AH_FLg==/base.apk\xf0\x04\x03\xf8\x04\x01\x8a\x05\x0232\x9a\x05\n2019118692\xb2\x05\tOpenGLES2\xb8\x05\xff\x7f\xc0\x05\x04\xe0\x05\xf3F\xea\x05\x07android\xf2\x05pKqsHT5ZLWrYljNb5Vqh//yFRlaPHSO9NWSQsVvOmdhEEn7W+VHNUK+Q+fduA3ptNrGB0Ll0LRz3WW0jOwesLj6aiU7sZ40p8BfUE/FI/jzSTwRe2\xf8\x05\xfb\xe4\x06\x88\x06\x01\x90\x06\x01\x9a\x06\x014\xa2\x06\x014\xb2\x06"GQ@O\x00\x0e^\x00D\x06UA\x0ePM\r\x13hZ\x07T\x06\x0cm\\V\x0ejYV;\x0bU5'
        ]
        # FIX ID/delay mendalam: timestamp basi 2025-08-30 + IP hardcoded 105.235.139.91 beda sama fake_ip header
        # = sinyal bot, MajorLogin ditolak sistematis -> N/A -> retry selamanya. bikin dinamis + konsisten.
        ts_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S").encode("ascii")
        payload_parts[0] = payload_parts[0].replace(b"2025-08-30 05:19:21", ts_now)
        ipl = fake_ip.encode("ascii")
        head, sep, _tail = payload_parts[0].partition(b"\xa2\x01")
        if sep:
            rest = _tail[1:]  # buang length byte lama
            old_ip_len = 14
            # potong IP lama: panjang 14 dari template (105.235.139.91)
            rest = rest[old_ip_len:]
            payload_parts[0] = head + b"\xa2\x01" + bytes([len(ipl)]) + ipl + rest
        payload = b''.join(payload_parts)
        if is_ghost:
            url = "https://loginbp.ggblueshark.com/MajorLogin"
        else:
            if region.upper() in ["ME", "TH"]:
                url = "https://loginbp.common.ggbluefox.com/MajorLogin"
            else:
                url = "https://loginbp.ggblueshark.com/MajorLogin"
        headers = {
            "Accept-Encoding": "gzip",
            "Authorization": "Bearer",
            "Connection": "Keep-Alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "ReleaseVersion": "OB54",
            "User-Agent": ua,
            "X-GA": "v1 1",
            "X-Unity-Version": "2021.3.15f1",
            "X-Forwarded-For": fake_ip,
            "X-Real-IP": fake_ip,
        }
        data = payload.replace(b'afcfbf13334be42036e4f742c80b956344bed760ac91b3aff9b607a610ab4390', access_token.encode())
        data = data.replace(b'1d8ec0240ede109973f3321b9354b44d', open_id.encode())
        d = encrypt_api(data.hex())
        response = _post(url, _stage="mlogin", headers=headers, data=bytes.fromhex(d), timeout=(3.5, REQ.get()))
        if response and response.status_code == 200:
            response_text = response.text
            jwt_start = response_text.find("eyJ")
            if jwt_start != -1:
                jwt_token = response_text[jwt_start:]
                second_dot = jwt_token.find(".", jwt_token.find(".") + 1)
                if second_dot != -1:
                    jwt_token = jwt_token[:second_dot + 44]
                    try:
                        parts = jwt_token.split('.')
                        if len(parts) >= 2:
                            payload_part = parts[1]
                            padding = 4 - len(payload_part) % 4
                            if padding != 4:
                                payload_part += '=' * padding
                            decoded = base64.urlsafe_b64decode(payload_part)
                            decoded_data = json.loads(decoded)
                            account_id = decoded_data.get('account_id') or decoded_data.get('external_id')
                            if account_id:
                                return {"account_id": str(account_id), "jwt_token": jwt_token}
                    except:
                        pass
            # FIX ID salah: fallback regex nebak angka random dari blob biner (timestamp/request echo) jadi ID ngaco.
            # ID asli HANYA dari JWT decode di atas. tanpa JWT = N/A -> worker retry, bukan save ngaco.
            return {"account_id": "N/A", "jwt_token": ""}
    except Exception:
        return {"account_id": "N/A", "jwt_token": ""}

def force_region_bind(region, jwt_token, is_ghost=False):
    """NYXORA V4 LITERAL"""
    try:
        if is_ghost:
            url = "https://loginbp.ggblueshark.com/ChooseRegion"
        else:
            url = "https://loginbp.common.ggbluefox.com/ChooseRegion" if region.upper() in ["ME","TH"] else "https://loginbp.ggblueshark.com/ChooseRegion"
        region_code = "RU" if region.upper() == "CIS" else region.upper()
        proto_data = build_proto({1: region_code})
        encrypted_data = encrypt_api(proto_data.hex())
        payload = bytes.fromhex(encrypted_data)
        headers = {
            'User-Agent': ip_spoofer.get_ua_and_ip()[0],
            'Connection': "Keep-Alive",
            'Accept-Encoding': "gzip",
            'Content-Type': "application/x-www-form-urlencoded",
            'Authorization': f"Bearer {jwt_token}",
            'X-Unity-Version': "2018.4.11f1",
            'X-GA': "v1 1",
            'ReleaseVersion': "OB53",
            'X-Forwarded-For': ip_spoofer.get_ip(),
        }
        _post(url, _stage="bind", data=payload, headers=headers, timeout=(3.5, REQ.get()))
    except:
        pass

# ===================== ANALISIS POLA =====================
def analyze_pattern(account_id):
    if not account_id or account_id == "N/A" or not account_id.isdigit():
        return "", 0
    freq = {}
    for d in account_id:
        freq[d] = freq.get(d, 0) + 1
    best_digit = None
    max_count = 0
    for digit, count in freq.items():
        if count > max_count:
            max_count = count
            best_digit = digit

    if max_count >= 4:
        detail = f"{best_digit}x{max_count}"
    else:
        detail = ""

    if max_count >= 10:
        score = 21
    elif max_count >= 8:
        score = 15
    elif max_count >= 6:
        score = 9
    elif max_count >= 4:
        score = 5
    else:
        score = 1

    return detail, score

def get_rarity_level(score):
    if score <= 4:
        return "COMMON"
    elif score <= 8:
        return "UNCOMMON"
    elif score <= 14:
        return "EPIC"
    elif score <= 20:
        return "LEGENDARY"
    else:
        return "MYTHIC"

# ===================== STORAGE =====================
def _safe_read_json(filepath):
    # FIX: baca jsonl append-only ATAU json list lama (kompatibel data lama)
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content:
            return []
        if content.startswith('['):
            data = json.loads(content)
            return data if isinstance(data, list) else []
        out = []
        for line in content.splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
        return out
    except:
        return []

def _safe_write_json(filepath, data):
    temp = filepath + ".tmp"
    try:
        with open(temp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, filepath)
        return True
    except Exception:
        try:
            if os.path.exists(temp):
                os.remove(temp)
        except:
            pass
        return False

# ===== BUFFERED JSONL WRITER (FIX: O(n^2) rewrite per akun -> append O(1)) =====
# sebelumnya: tiap akun disimpan = baca ULANG seluruh file + tulis ulang semua
# entri + fsync, semua di bawah FILE_LOCK global. di ratusan akun, 80-120
# thread antri di lock itu -> generate tampak "berhenti" di ~120/1000.
_STORAGE_PENDING = {}
_STORAGE_PENDING_LOCK = threading.Lock()
_STORAGE_WRITER_STOP = threading.Event()

def _append_jsonl(filepath, entries):
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries))
    except Exception:
        pass

def _drain_pending():
    with _STORAGE_PENDING_LOCK:
        if not _STORAGE_PENDING:
            return
        items = list(_STORAGE_PENDING.items())
        _STORAGE_PENDING.clear()
    for filepath, entries in items:
        _append_jsonl(filepath, entries)

def _storage_writer_loop():
    while not _STORAGE_WRITER_STOP.is_set():
        _STORAGE_WRITER_STOP.wait(timeout=1.0)
        _drain_pending()
    _drain_pending()

_storage_writer_thread = threading.Thread(target=_storage_writer_loop, daemon=True)
_storage_writer_thread.start()

def _buffer_entry(filepath, entry):
    with _STORAGE_PENDING_LOCK:
        lst = _STORAGE_PENDING.get(filepath)
        if lst is None:
            lst = []
            _STORAGE_PENDING[filepath] = lst
        lst.append(entry)

def _flush_storage_buffer():
    _drain_pending()

def save_account(account_data, rarity_type, detail_str, score):
    # FIX: buffered append jsonl — tidak lagi rewrite seluruh file per akun
    try:
        folder = RARITY_FOLDERS.get(rarity_type)
        if not folder:
            return False
        filepath = os.path.join(folder, f"{rarity_type.lower()}.jsonl")
        entry = {
            "uid": account_data.get("uid", ""),
            "password": account_data.get("password", ""),
            "account_id": account_data.get("account_id", "N/A"),
            "name": account_data.get("name", ""),
            "region": account_data.get("region", "UNKNOWN"),
            "rarity": rarity_type,
            "detail": detail_str,
            "score": score,
            "date_saved": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "jwt_token": account_data.get("jwt_token", "")
        }
        _buffer_entry(filepath, entry)
        return True
    except Exception:
        return False

def save_hunter_account(account_data, rarity_type, detail_str, score):
    # FIX: buffered append jsonl
    try:
        entry = {
            "uid": account_data.get("uid", ""),
            "password": account_data.get("password", ""),
            "account_id": account_data.get("account_id", "N/A"),
            "name": account_data.get("name", ""),
            "region": account_data.get("region", "UNKNOWN"),
            "rarity": rarity_type,
            "detail": detail_str,
            "score": score,
            "date_saved": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "jwt_token": account_data.get("jwt_token", "")
        }
        _buffer_entry(HUNTER_FILE + "l", entry)
        return True
    except Exception:
        return False

COUPLE_CACHE = {}
COUPLE_LOCK = threading.Lock()
COUPLE_COUNT = {"BASIC": 0, "RARE": 0}

def _save_couple_file(account1, account2, is_rare):
    try:
        if is_rare:
            folder = COUPLE_RARE_FOLDER
            couple_type = "RARE_COUPLE"
        else:
            folder = COUPLE_BASIC_FOLDER
            couple_type = "BASIC_COUPLE"
        os.makedirs(folder, exist_ok=True)
        id1 = account1.get("account_id", "N/A")
        id2 = account2.get("account_id", "N/A")
        if id1 < id2:
            fname = f"{id1}_{id2}.json"
        else:
            fname = f"{id2}_{id1}.json"
        filepath = os.path.join(folder, fname)
        entry = {
            "couple_type": couple_type,
            "account1": account1,
            "account2": account2,
            "date_saved": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_rare": is_rare
        }
        _buffer_entry(filepath + "l", entry)
        return True
    except Exception:
        return False

def check_and_save_couple(account_data):
    global COUPLE_COUNT
    account_id = account_data.get("account_id", "")
    if not account_id or account_id == "N/A":
        return False
    try:
        aid_int = int(account_id)
        for diff in [-1, 1]:
            candidate = str(aid_int + diff)
            with COUPLE_LOCK:
                if candidate in COUPLE_CACHE:
                    partner_data = COUPLE_CACHE.pop(candidate)
                    partner_id = candidate
                    break
        else:
            with COUPLE_LOCK:
                COUPLE_CACHE[account_id] = account_data
            return False
    except:
        return False
    _, score1 = analyze_pattern(account_id)
    _, score2 = analyze_pattern(partner_id)
    is_rare = (score1 >= 15 or score2 >= 15 or (score1 + score2) >= 25)
    _save_couple_file(account_data, partner_data, is_rare)
    with COUPLE_LOCK:
        if is_rare:
            COUPLE_COUNT["RARE"] += 1
        else:
            COUPLE_COUNT["BASIC"] += 1
    if is_rare:
        couple_type = "RARE COUPLE"
        color = D.PINK
    else:
        couple_type = "BASIC COUPLE"
        color = D.COUPLE
    with PRINT_LOCK:
        print(f"{color}{D.BOLD}[COUPLE] {account_id} <3 {partner_id} {couple_type}{D.RST}")
    return True

def grad_text(text, codes=None):
    if codes is None:
        codes = [183,147,141,135,129,93,57]
    return ''.join(f"\033[38;5;{codes[i % len(codes)]}m{D.BOLD}{ch}{D.RST}" for i, ch in enumerate(text))

RARITY_COLOR = {
    "COMMON": "\033[38;2;200;200;215m",
    "UNCOMMON": "\033[38;2;100;220;170m",
    "EPIC": "\033[38;2;170;120;240m",
    "LEGENDARY": "\033[38;2;255;100;120m",
    "MYTHIC": "\033[38;2;235;120;200m",
}

ARROW_IDX = {"i": 0}

def format_account_line(seq_num, total, account_data, detail_str, score, rarity_type, skipped=False, api_num=None):
    account_id = account_data.get("account_id", "N/A")
    progress = f"[{seq_num:03d}/{total:03d}] " if isinstance(seq_num, int) else ""
    i = ARROW_IDX["i"]
    ARROW_IDX["i"] = (i + 1) % len(VOID_GRAD)
    arrow = f"\033[38;5;{VOID_GRAD[i]}m{D.BOLD}➤{D.RST}"
    color = RARITY_COLOR.get(rarity_type, D.LIGHT)
    detail = f" {detail_str}" if detail_str else ""
    api_tag = f" [API{api_num}]" if api_num else ""
    return f"{arrow}{D.BOLD}{D.GRAY} {progress}{D.RST}{color}{D.BOLD}ID:{account_id} {rarity_type}{detail}{api_tag}{D.RST}"

def print_account_line(seq_num, total, account_data, detail_str, score, rarity_type, skipped=False, api_num=None):
    line = format_account_line(seq_num, total, account_data, detail_str, score, rarity_type, skipped, api_num)
    print(line, flush=True)

def gline(length=60, char='─'):
    colors = [183,147,141,135,129,93,57]
    return ''.join(f"\033[38;5;{colors[i % len(colors)]}m{char}" for i in range(length)) + D.RST

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

def vlen(s):
    return len(ANSI_RE.sub("", s))

VOID_GRAD   = [213, 207, 183, 147, 141, 135, 129, 99, 93, 57]
BORDER      = "\033[38;2;160;130;235m"
TITLE_CLR   = "\033[38;2;215;195;255m"
ITEM_CLR    = "\033[38;2;240;238;250m"
PURPLE_DIM  = "\033[38;2;130;95;215m"
PURPLE_DARK = "\033[38;2;55;30;105m"

def pline(text="", width=60):
    gap = width - 2 - vlen(text)
    if gap < 0:
        gap = 0
    return (f"{BORDER}║{D.RST} {text}"
            f"{' ' * gap}{BORDER}║{D.RST}")

def grad_hline(width, char='═', colors=None):
    if colors is None:
        colors = VOID_GRAD
    return ''.join(f"\033[38;5;{colors[i % len(colors)]}m{char}" for i in range(width)) + D.RST

def box_header(title, width=60):
    print(f"{BORDER}╔{D.RST}{grad_hline(width)}{BORDER}╗{D.RST}")
    t = f"{D.BOLD}{TITLE_CLR} {title} \033[0m"
    gap = max(width - 2 - vlen(t), 0)
    left = gap // 2
    print(f"{BORDER}║{D.RST}{' ' * left}{t}{' ' * (gap - left)}{BORDER}║{D.RST}")
    print(f"{BORDER}╠{D.RST}{grad_hline(width)}{BORDER}╣{D.RST}")

def box_footer(width=60):
    return f"{BORDER}╚{D.RST}{grad_hline(width)}{BORDER}╝{D.RST}"

NUM_COLORS = ["\033[38;5;183m", "\033[38;5;147m", "\033[38;5;99m"]

def menuline(idx, key, label, width=60):
    nc = NUM_COLORS[idx % len(NUM_COLORS)]
    body = f" {nc}{D.BOLD}{key}.{D.RST} {D.BOLD}{ITEM_CLR}{label}{D.RST}"
    gap = max(width - 2 - vlen(body), 0)
    return f"{BORDER}║{D.RST}{body}{' ' * gap}{BORDER}║{D.RST}"

OK = 0
RESERVED = 0
TARGET = 0
RARITY_COUNTS = {"COMMON":0, "UNCOMMON":0, "EPIC":0, "LEGENDARY":0, "MYTHIC":0}
LOCK = threading.Lock()
PRINT_LOCK = threading.Lock()

HUNTER_MODE = False
HUNTER_TARGETS = []
RARE_ONLY = False
GHOST_MODE = False
ATTEMPTS = {"n": 0}
MAX_ATTEMPTS = {"n": 0}

FAIL_STATS = {"timeout": 0, "throttle": 0, "conn": 0, "other": 0}
FAIL_LOCK = threading.Lock()
LAST_FAIL = {"kind": "other"}
STAGE_T = {}
STAGE_LOCK = threading.Lock()

def _note_stage(name, dt):
    try:
        with STAGE_LOCK:
            s = STAGE_T.get(name)
            if s is None:
                STAGE_T[name] = [dt, 1]
            else:
                s[0] += dt
                s[1] += 1
    except Exception:
        pass

def _note_fail(kind):
    try:
        with FAIL_LOCK:
            FAIL_STATS[kind] = FAIL_STATS.get(kind, 0) + 1
            LAST_FAIL["kind"] = kind
    except Exception:
        pass

def _post(url, _stage="other", **kw):
    # FIX delay mendalam: keep-alive basi (Garena tutup koneksi idle) -> request pertama di koneksi mati
    # langsung ConnectionError. retry 1x SEGERA tanpa sleep/backoff, baru dianggap fail. tanpa ini tiap
    # koneksi basi = 1 backoff sleep + 1 attempt hangus. sekalian catat waktu tiap stage + jenis gagal.
    t0 = time.time()
    if "garena.com" in url or "ggblue" in url:
        with GARENA_SEM:
            return _post_inner(url, _stage, t0, kw)
    return _post_inner(url, _stage, t0, kw)


def _post_inner(url, _stage, t0, kw):
    try:
        r = session.post(url, **kw)
    except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError):
        try:
            r = session.post(url, **kw)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectTimeout, socket.timeout):
            _note_stage(_stage, time.time() - t0)
            _note_fail("timeout")
            raise
        except Exception:
            _note_stage(_stage, time.time() - t0)
            _note_fail("conn")
            raise
    except (requests.exceptions.Timeout, requests.exceptions.ConnectTimeout, socket.timeout):
        _note_stage(_stage, time.time() - t0)
        _note_fail("timeout")
        raise
    except Exception:
        _note_stage(_stage, time.time() - t0)
        _note_fail("conn")
        raise
    _note_stage(_stage, time.time() - t0)
    try:
        sc = getattr(r, "status_code", 0)
        if sc == 429 or sc == 503 or sc == 403:
            _note_fail("throttle")
        elif sc != 200:
            _note_fail("other")
    except Exception:
        pass
    return r

# ================= 10-API RACE POOL (pola chef Sam, adaptasi nama testz) =================
# HASIL PROBE Potato 2026-09-15 (parallel, timeout 15s): 7 endpoint 402 Payment Required
# (generate-ken, mimin-booyah-pro, garena-mybini, garena-bapakku, garena-promax,
# bgn-garena-vip, mbg-garena = deploy disuspend, MILIK ORANG ga bisa dibenerin),
# 3 endpoint timeout 15s (new-garena, pecel-mas-amba, sppg-jomok = hang).
# -> 10-10nya DIBLACKLIST dari pool aktif. sisa 1: genafriezx (milik chef, rework honest-fast).
API_ENDPOINTS = {
    1: "https://genafriezx.vercel.app/gen",
}
API_NAMES = {
    1: "genafriezx-ours",
}
api_selection = 0
PERF = {"local": None, "api": None}
TUNE = {"race_bonus": 0, "buf_target": 30}
GOV_STARTED = {"on": False}
KEEP_STARTED = {"on": False}
API_STATS = {i: {"ok": 0, "fail": 0} for i in range(1, 11)}
API_LOCK = threading.Lock()
API_HEALTH = {i: {"streak": 0, "cooldown": 0.0, "strikes": 0} for i in range(1, 11)}
API_TIMEOUT = (2, 3)
API_COOLDOWN = 20.0
RACE_N = 3
BUF_MAX = 200

from queue import SimpleQueue
import types as _types
ACC_BUFFER = {}

def buf_size(region):
    q = ACC_BUFFER.get(region.upper())
    return q.qsize() if q else 0

def buf_pop(region):
    q = ACC_BUFFER.get(region.upper())
    if q is None:
        return None
    try:
        return q.get_nowait()
    except Exception:
        return None

def buf_push(region, acc):
    q = ACC_BUFFER.setdefault(region.upper(), SimpleQueue())
    try:
        if q.qsize() < BUF_MAX:
            q.put_nowait(acc)
    except Exception:
        pass

def api_healthy(api_id):
    return time.time() >= API_HEALTH[api_id]["cooldown"]

def api_mark(api_id, ok):
    st = API_HEALTH[api_id]
    if ok:
        if st["streak"] > 0:
            with API_LOCK:
                st["streak"] = 0
                st["cooldown"] = 0.0
                st["strikes"] = max(0, st["strikes"] - 1)
    else:
        with API_LOCK:
            st["streak"] += 1
            if st["streak"] >= 3:
                st["strikes"] = min(4, st["strikes"] + 1)
                st["cooldown"] = time.time() + API_COOLDOWN * (2 ** st["strikes"])
                st["streak"] = 0
    API_STATS[api_id]["ok" if ok else "fail"] += 1

def api_pick():
    if api_selection in API_ENDPOINTS:
        return api_selection if api_healthy(api_selection) else None
    healthy = [i for i in API_ENDPOINTS if api_healthy(i)]
    if not healthy:
        return None
    random.shuffle(healthy)
    return healthy

def api_mode_text():
    if api_selection == 0:
        return f"RANDOM ({len(API_ENDPOINTS)} API)"
    return f"API {api_selection} - {API_NAMES.get(api_selection, '?')}"

def _api_call(api_id, region, name_prefix):
    params = {
        "name": name_prefix,
        "count": 1,
        "region": region.upper(),
        "password_prefix": random.choice(PASS_PREFIXES),
    }
    t0 = time.perf_counter()
    resp = _vhttp().get(API_ENDPOINTS[api_id], params=params, timeout=API_TIMEOUT)
    v = PERF["api"]
    d = time.perf_counter() - t0
    PERF["api"] = d if v is None else v * 0.8 + d * 0.2
    if resp.status_code == 200:
        data = resp.json()
        if data.get("success") and data.get("accounts"):
            acc = data["accounts"][0]
            # VALIDASI KETAT (fix ID ngaco): mock random (uid tanpa token, ex new-garena/vercel lama)
            # DITOLAK di sini -> api_mark fail -> cooldown. ID asli wajib uid digit + token jwt.
            uid = str(acc.get("uid", ""))
            tok = str(acc.get("token", "") or acc.get("jwt_token", ""))
            aid = str(acc.get("account_id", "") or uid)
            if not (uid.isdigit() and 10 <= len(uid) <= 12):
                return None
            if not (aid.isdigit() and 10 <= len(aid) <= 12):
                return None
            if not tok or len(tok) < 20:
                return None
            return {
                "uid": uid,
                "password": acc.get("password", ""),
                "name": acc.get("name", name_prefix),
                "account_id": aid,
                "jwt_token": tok,
                "region": region.upper(),
                "api_used": api_id,
            }
    return None

def _one_try(api_id, region, name_prefix):
    try:
        acc = _api_call(api_id, region, name_prefix)
    except Exception:
        acc = None
    ok = bool(acc and acc.get("account_id", "N/A") != "N/A")
    api_mark(api_id, ok)
    return acc if ok else None

RACER_SESSION = requests.Session()
RACER_ADAPTER = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=0, pool_block=False)
RACER_SESSION.mount("https://", RACER_ADAPTER)
RACER_SESSION.mount("http://", RACER_ADAPTER)
RACER_SESSION.verify = False
RACER_SESSION.trust_env = False
RACER_SESSION.headers.update({"Accept": "application/json", "Connection": "keep-alive"})

RACER_SLOT = _types.SimpleNamespace(session=RACER_SESSION, ua="", ip="", uses=0)

def _race_api(api_id, region, name_prefix):
    try:
        acc = _api_call(api_id, region, name_prefix)
    except Exception:
        acc = None
    ok = bool(acc and acc.get("account_id", "N/A") != "N/A")
    api_mark(api_id, ok)
    if ok:
        buf_push(region, acc)

_RACE_EXEC = {"ex": None}
_RACE_LOCK = threading.Lock()

def _race_exec():
    with _RACE_LOCK:
        if _RACE_EXEC["ex"] is None:
            from concurrent.futures import ThreadPoolExecutor as _TPE
            _RACE_EXEC["ex"] = _TPE(max_workers=30)
        return _RACE_EXEC["ex"]

# REM PARALEL GLOBAL: 50 worker + 30 racer TLS bareng dari 1 IP hp = WAF Garena throttle
# = semua timeout = delay. max 25 request Garena in-flight, sisanya antre murah (tanpa network).
GARENA_SEM = threading.Semaphore(25)

def _proven_apis(hl):
    try:
        return [a for a in hl if API_STATS.get(a, {}).get("ok", 0) > 0]
    except Exception:
        return []

def _race_shutdown():
    try:
        with _RACE_LOCK:
            ex = _RACE_EXEC["ex"]
            _RACE_EXEC["ex"] = None
        if ex is not None:
            try:
                ex.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                ex.shutdown(wait=False)
    except Exception:
        pass

def prime_buffer(region, name_prefix, count, threads, is_ghost=False):
    # FIX herd: dulu 40 lokal + 80 racer DIAWAL = IP langsung di-throttle Garena sebelum kerja.
    # sekarang: 4 lokal pemanasan + racer HANYA ke API terbukti (ok>0). API baru wajib buktiin 1 sukses
    # dulu sebelum dikasih traffic (lihat sampling di create_account_via_api).
    ex = _race_exec()
    for _ in range(min(4, max(1, threads // 10))):
        ex.submit(_prime_local, region, name_prefix, is_ghost)
    healthy = api_pick()
    hl = healthy if isinstance(healthy, list) else ([healthy] if healthy else [])
    for a in _proven_apis(hl)[:2]:
        ex.submit(_race_api, a, region, name_prefix)

def _prime_local(region, name_prefix, is_ghost=False):
    try:
        acc = create_account(region, name_prefix, random.choice(PASS_PREFIXES), is_ghost)
    except Exception:
        acc = None
    if acc and acc.get("account_id", "N/A") != "N/A":
        buf_push(region, acc)

def create_account_via_api(region, name_prefix, is_ghost=False):
    if EXIT:
        return None
    if is_ghost:
        try:
            return create_account(region, name_prefix, random.choice(PASS_PREFIXES), True)
        except Exception:
            return None
    acc = buf_pop(region)
    if acc:
        return acc
    healthy = api_pick()
    hl = healthy if isinstance(healthy, list) else ([healthy] if healthy else [])
    futs = []
    api_slow = (PERF["api"] is not None and PERF["local"] is not None
                and PERF["api"] > PERF["local"] * 1.5)
    bs = buf_size(region)
    # API tanpa bukti sukses TIDAK di-race tiap iterasi (hemat 2-6s + radio hp). sampling: 1 probe
    # tiap 20 attempt biar API yang sudah dibenerin (ex: habis redeploy) bisa naik lagi otomatis.
    proven = _proven_apis(hl)
    racers = list(proven)
    try:
        if not racers and hl and not api_slow and ATTEMPTS["n"] % 20 == 0:
            racers = [hl[ATTEMPTS["n"] % len(hl)]]
    except Exception:
        pass
    if racers and not api_slow:
        deficit = max(0, TUNE["buf_target"] - bs)
        race_count = min(RACE_N + TUNE["race_bonus"] + (2 if deficit > TUNE["buf_target"] // 2 else 0), len(racers))
        if race_count > 0 and bs < TUNE["buf_target"]:
            ex = _race_exec()
            for a in racers[:race_count]:
                futs.append(ex.submit(_race_api, a, region, name_prefix))
    t0 = time.perf_counter()
    try:
        acc = create_account(region, name_prefix, random.choice(PASS_PREFIXES), False)
    except Exception:
        acc = None
    v = PERF["local"]
    d = time.perf_counter() - t0
    PERF["local"] = d if v is None else v * 0.8 + d * 0.2
    if acc and acc.get("account_id", "N/A") != "N/A":
        return acc
    deadline = time.time() + (min(API_TIMEOUT[1], 2.0) if futs else 0)
    while hl and time.time() < deadline:
        if EXIT:
            return None
        acc = buf_pop(region)
        if acc:
            return acc
        if futs and all(f.done() for f in futs):
            break
        time.sleep(0.05)
    acc = buf_pop(region)
    if acc:
        return acc
    for api_id in _proven_apis(hl)[RACE_N:RACE_N + 2]:
        if EXIT:
            return None
        acc = _one_try(api_id, region, name_prefix)
        if acc:
            return acc
    return None

def governor():
    last = {"att": ATTEMPTS["n"], "fail": sum(st["fail"] for st in API_STATS.values())}
    while not EXIT:
        time.sleep(2)
        att = ATTEMPTS["n"]
        fails = sum(st["fail"] for st in API_STATS.values())
        d_att = att - last["att"]
        d_fail = fails - last["fail"]
        last = {"att": att, "fail": fails}
        if d_att >= 10:
            fr = d_fail / d_att
            if fr > 0.5:
                TUNE["race_bonus"] = 0
            elif fr < 0.2:
                TUNE["race_bonus"] = 1
            else:
                TUNE["race_bonus"] = 0

def connection_keeper():
    while not EXIT:
        time.sleep(15)
        try:
            session.head("https://100067.connect.garena.com", timeout=(3, 5))
        except Exception:
            pass
        try:
            keys = list(_dns_cache.keys())
            fresh = {}
            for key in keys:
                try:
                    fresh[key] = _orig_getaddrinfo(*key)
                except Exception:
                    pass
            if fresh:
                with _dns_lock:
                    _dns_cache.update(fresh)
        except Exception:
            pass

def prewarm_apis():
    if not any(api_healthy(i) for i in API_ENDPOINTS):
        return
    def _ping(api_id):
        try:
            session.get(API_ENDPOINTS[api_id], params={"count": 0}, timeout=(3, 6))
        except Exception:
            pass
    for i in API_ENDPOINTS:
        threading.Thread(target=_ping, args=(i,), daemon=True).start()

def worker(region, name_prefix, thread_id, total, is_ghost=False):
    global OK, RESERVED
    local_ok = 0
    fails = 0
    while not EXIT:
        with LOCK:
            # FIX hang tak berujung: 100% gagal (IP kena throttle/WAF 503) = RESERVED naik-turun selamanya.
            # budget global: total*10+200 percobaan, habis -> stop, cetak hasil. generator SELALU selesai.
            if RESERVED >= total or ATTEMPTS["n"] >= MAX_ATTEMPTS["n"]:
                break
            RESERVED += 1
            ATTEMPTS["n"] += 1
        # 10-API race pool chef: buffer -> lokal+racer paralel -> tunggu buffer -> one_try cadangan.
        # acc api bawa api_used 1-10 -> tag [API3]. acc lokal tanpa tag. ghost full lokal.
        account = create_account_via_api(region, name_prefix, is_ghost)
        api_num = account.get("api_used") if account else None
        if not account:
            with LOCK:
                RESERVED -= 1
            REQ.on_fail()
            # FIX delay3 status-aware: throttle (429/503/403) = server nyuruh pelan. hajar terus = makin
            # diban = makin delay. kasih cooldown 1.5-3s. timeout/conn = transient, retry cepat 0.35s.
            fails += 1
            try:
                kind = LAST_FAIL.get("kind", "other")
            except Exception:
                kind = "other"
            if kind == "throttle":
                time.sleep(min(3.0, 0.8 * (2 ** min(fails, 3))) + random.uniform(0, 0.2))
            elif fails > 2:
                time.sleep(min(0.35, 0.05 * (2 ** min(fails, 5))) + random.uniform(0, 0.03))
            if HUNTER_MODE:
                n = ATTEMPTS["n"]
                if n % 25 == 0:
                    with PRINT_LOCK:
                        print(f"{D.DIM_GRAY}{D.BOLD}[hunt] mencari target... {n} percobaan, {OK} ketemu{D.RST}", flush=True)
            continue
        fails = 0
        REQ.on_ok()
        account_id = account.get("account_id", "N/A")
        if account_id == "N/A":
            with LOCK:
                RESERVED -= 1
            continue
        check_and_save_couple(account)
        detail_str, score = analyze_pattern(account_id)
        rarity = get_rarity_level(score)

        if RARE_ONLY and score < 9:
            with LOCK:
                RESERVED -= 1
            continue

        if HUNTER_MODE:
            if rarity in HUNTER_TARGETS:
                save_hunter_account(account, rarity, detail_str, score)
                with LOCK:
                    OK += 1
                    cur = OK
                    RARITY_COUNTS[rarity] += 1
                with PRINT_LOCK:
                    print_account_line(cur, total, account, detail_str, score, rarity, skipped=False, api_num=api_num)
            else:
                with LOCK:
                    RESERVED -= 1
                with PRINT_LOCK:
                    print(f"{D.DIM_GRAY}{D.BOLD} ~ SKIPPED RARITY ~{D.RST}", flush=True)
        else:
            saved = save_account(account, rarity, detail_str, score)
            with LOCK:
                OK += 1
                local_ok = OK
                if saved:
                    RARITY_COUNTS[rarity] += 1
            with PRINT_LOCK:
                print_account_line(local_ok, total, account, detail_str, score, rarity, skipped=False, api_num=api_num)

def prewarm_pool(per_host=6):
    # FIX delay2: POST b"" kosong ke Garena = 2 detik block + flag IP bot sebelum kerja. ganti DNS warmup only.
    try:
        socket.getaddrinfo("100067.connect.garena.com", 443)
        socket.getaddrinfo("loginbp.ggblueshark.com", 443)
    except Exception:
        pass

def generate(region, name_prefix, count, threads, is_ghost=False):
    global OK, RESERVED, TARGET, RARITY_COUNTS, EXIT, COUPLE_CACHE, COUPLE_COUNT
    with LOCK:
        OK = 0
        RESERVED = 0
        TARGET = count
        ATTEMPTS["n"] = 0
        MAX_ATTEMPTS["n"] = count * 10 + 200
        for k in RARITY_COUNTS:
            RARITY_COUNTS[k] = 0
    with COUPLE_LOCK:
        COUPLE_CACHE.clear()
        COUPLE_COUNT = {"BASIC": 0, "RARE": 0}
    with STAGE_LOCK:
        STAGE_T.clear()
    with FAIL_LOCK:
        for k in FAIL_STATS:
            FAIL_STATS[k] = 0
        LAST_FAIL["kind"] = "other"
    EXIT = False
    prewarm_pool()
    if not GOV_STARTED["on"]:
        GOV_STARTED["on"] = True
        threading.Thread(target=governor, daemon=True).start()
    if not KEEP_STARTED["on"]:
        KEEP_STARTED["on"] = True
        threading.Thread(target=connection_keeper, daemon=True).start()
    threading.Thread(target=prewarm_apis, daemon=True).start()
    prime_buffer(region, name_prefix, count, threads, is_ghost)
    start = time.time()
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = [executor.submit(worker, region, name_prefix, i+1, count, is_ghost) for i in range(threads)]
        for f in futures:
            try:
                f.result()
            except Exception:
                pass
    _flush_storage_buffer()
    _race_shutdown()
    elapsed = time.time() - start
    print()
    box_header("HASIL")
    print(pline(f"{D.GOLD}{D.BOLD}selesai dalam {elapsed:.1f}s{D.RST}"))
    print(pline(f"{D.LIGHT}{D.BOLD}akun jadi  : {D.GOLD}{D.BOLD}{OK}{D.RST}{D.LIGHT}{D.BOLD}/{count}{D.RST}"))
    try:
        print(pline(f"{D.DIM_GRAY}{D.BOLD}api mode : {api_mode_text()}{D.RST}"))
        with API_LOCK:
            st = sorted(API_STATS.items(), key=lambda kv: kv[1]["ok"], reverse=True)[:3]
        top = " ".join(f"{API_NAMES.get(i, i)}:{v['ok']}ok/{v['fail']}f" for i, v in st if v["ok"] or v["fail"])
        if top:
            print(pline(f"{D.DIM_GRAY}{D.BOLD}api top  : {top}{D.RST}"))
    except Exception:
        pass
    color_map = {
        "COMMON": D.LIGHT,
        "UNCOMMON": D.SUCCESS,
        "EPIC": D.PURPLE,
        "LEGENDARY": D.ERROR,
        "MYTHIC": D.PINK
    }
    for rarity, cnt in RARITY_COUNTS.items():
        if cnt > 0:
            color = color_map.get(rarity, D.LIGHT)
            print(pline(f"{color}{D.BOLD}{rarity}: {cnt}{D.RST}"))
    if HUNTER_MODE:
        print(pline(f"{D.GOLD}{D.BOLD}target hunt: {', '.join(HUNTER_TARGETS)}{D.RST}"))
        print(pline(f"{D.DIM_GRAY}{D.BOLD}total percobaan: {ATTEMPTS['n']}{D.RST}"))
    with COUPLE_LOCK:
        if COUPLE_COUNT["BASIC"] > 0 or COUPLE_COUNT["RARE"] > 0:
            print(pline(f"{D.COUPLE}{D.BOLD}<3 basic couple : {COUPLE_COUNT['BASIC']}{D.RST}"))
            print(pline(f"{D.PINK}{D.BOLD}<=3 rare couple : {COUPLE_COUNT['RARE']}{D.RST}"))
    try:
        with STAGE_LOCK:
            parts = []
            for nm in ("register", "token", "mreg", "mlogin", "bind"):
                s = STAGE_T.get(nm)
                if s and s[1]:
                    parts.append(f"{nm} {s[0]/s[1]:.2f}s x{s[1]}")
        if parts:
            print(pline(f"{D.DIM_GRAY}{D.BOLD}stage: {' | '.join(parts)}{D.RST}"))
        with FAIL_LOCK:
            print(pline(f"{D.DIM_GRAY}{D.BOLD}fail: timeout {FAIL_STATS.get('timeout',0)} throttle {FAIL_STATS.get('throttle',0)} conn {FAIL_STATS.get('conn',0)} other {FAIL_STATS.get('other',0)}{D.RST}"))
    except Exception:
        pass
    print(box_footer())
    input(f"\n{BORDER}{D.BOLD}└─>{D.RST} enter buat lanjut...")

def view_rarity_menu():
    _flush_storage_buffer()
    clear_screen()
    display_banner()
    box_header("LIHAT AKUN PER RARITY")
    items = [
        ("1", "COMMON", D.LIGHT),
        ("2", "UNCOMMON", D.SUCCESS),
        ("3", "EPIC", D.PURPLE),
        ("4", "LEGENDARY", D.ERROR),
        ("5", "MYTHIC", D.PINK),
        ("6", "HUNTER", D.GOLD),
        ("7", "COUPLES", D.COUPLE),
        ("0", "Kembali", D.ERROR),
    ]
    for i, (num, label, color) in enumerate(items):
        print(menuline(i, num, label))
    print(box_footer())
    choice = input(f"\n{BORDER}{D.BOLD}└─>{D.RST} pilih: ").strip()
    rarity_map = {"1":"COMMON","2":"UNCOMMON","3":"EPIC","4":"LEGENDARY","5":"MYTHIC"}
    if choice == "0":
        return
    if choice == "6":
        if not os.path.exists(HUNTER_FILE):
            print(f"{D.WARNING}{D.BOLD}belum ada akun hunter.{D.RST}")
            input("enter...")
            return
        data_list = _safe_read_json(HUNTER_FILE)
        if not data_list:
            print(f"{D.WARNING}{D.BOLD}belum ada akun hunter.{D.RST}")
            input("enter...")
            return
        clear_screen()
        display_banner()
        box_header(f"HUNTER ACCOUNTS ({len(data_list)})")
        total = len(data_list)
        for idx, entry in enumerate(data_list[:30], 1):
            acc_id = entry.get("account_id", "N/A")
            detail = entry.get("detail", "N/A")
            rarity = entry.get("rarity", "UNKNOWN")
            color_map = {
                "COMMON": D.LIGHT,
                "UNCOMMON": D.SUCCESS,
                "EPIC": D.PURPLE,
                "LEGENDARY": D.ERROR,
                "MYTHIC": D.PINK
            }
            color = color_map.get(rarity, D.LIGHT)
            det = f" {detail}" if detail and detail != "N/A" else ""
            print(f"{color}{D.BOLD}[{idx:03d}/{total:03d}] ID:{acc_id} {rarity}{det}{D.RST}")
        if len(data_list) > 30:
            print(f"{D.DIM_GRAY}{D.BOLD}... and {len(data_list)-30} more.{D.RST}")
        input(f"\n{BORDER}{D.BOLD}└─>{D.RST} enter buat lanjut...")
        return
    if choice == "7":
        clear_screen()
        display_banner()
        box_header("COUPLES")
        print(menuline(0, "1", "Basic Couples"))
        print(menuline(1, "2", "Rare Couples"))
        print(menuline(2, "0", "Kembali"))
        print(box_footer())
        sub = input(f"\n{BORDER}{D.BOLD}└─>{D.RST} pilih: ").strip()
        if sub == "0":
            return
        folder = COUPLE_BASIC_FOLDER if sub == "1" else COUPLE_RARE_FOLDER if sub == "2" else None
        if not folder or not os.path.exists(folder):
            print(f"{D.WARNING}{D.BOLD}belum ada couple.{D.RST}")
            input("enter...")
            return
        files = [f for f in os.listdir(folder) if f.endswith(('.json', '.jsonl'))]
        if not files:
            print(f"{D.WARNING}{D.BOLD}belum ada couple.{D.RST}")
            input("enter...")
            return
        clear_screen()
        display_banner()
        label = "BASIC" if sub == "1" else "RARE"
        box_header(f"{label} COUPLES ({len(files)})")
        for idx, fname in enumerate(files[:30], 1):
            filepath = os.path.join(folder, fname)
            try:
                data = _safe_read_json(filepath)
                if not data:
                    continue
                couple = data[-1]
                acc1 = couple.get('account1', {})
                acc2 = couple.get('account2', {})
                id1 = acc1.get('account_id', 'N/A')
                id2 = acc2.get('account_id', 'N/A')
                uid1 = acc1.get('uid', 'N/A')
                uid2 = acc2.get('uid', 'N/A')
                color = D.COUPLE if label == "BASIC" else D.PINK
                print(f"{color}{D.BOLD}[{idx:03d}] {id1} <3 {id2} | UID: {uid1} & {uid2}{D.RST}")
            except:
                pass
        if len(files) > 30:
            print(f"{D.DIM_GRAY}{D.BOLD}... and {len(files)-30} more.{D.RST}")
        input(f"\n{BORDER}{D.BOLD}└─>{D.RST} enter buat lanjut...")
        return
    if choice in rarity_map:
        rarity = rarity_map[choice]
        filepath = RARITY_FILES.get(rarity)
        if not filepath or not os.path.exists(filepath):
            print(f"{D.WARNING}{D.BOLD}belum ada akun {rarity}.{D.RST}")
            input("enter...")
            return
        data_list = _safe_read_json(filepath)
        if not data_list:
            print(f"{D.WARNING}{D.BOLD}belum ada akun {rarity}.{D.RST}")
            input("enter...")
            return
        clear_screen()
        display_banner()
        box_header(f"{rarity} ACCOUNTS ({len(data_list)})")
        total = len(data_list)
        color_map = {
            "COMMON": D.LIGHT,
            "UNCOMMON": D.SUCCESS,
            "EPIC": D.PURPLE,
            "LEGENDARY": D.ERROR,
            "MYTHIC": D.PINK
        }
        color = color_map.get(rarity, D.LIGHT)
        for idx, entry in enumerate(data_list[:30], 1):
            acc_id = entry.get("account_id", "N/A")
            detail = entry.get("detail", "N/A")
            det = f" {detail}" if detail and detail != "N/A" else ""
            print(f"{color}{D.BOLD}[{idx:03d}/{total:03d}] ID:{acc_id} {rarity}{det}{D.RST}")
        if len(data_list) > 30:
            print(f"{D.DIM_GRAY}{D.BOLD}... and {len(data_list)-30} more.{D.RST}")
        input(f"\n{BORDER}{D.BOLD}└─>{D.RST} enter buat lanjut...")
    else:
        print(f"{D.ERROR}{D.BOLD}pilihannya nggak ada, coba lagi.{D.RST}")
        input("enter...")

def stats():
    _flush_storage_buffer()
    clear_screen()
    display_banner()
    box_header("STATISTIK AKUN")
    total = 0
    color_map = {
        "COMMON": D.LIGHT,
        "UNCOMMON": D.SUCCESS,
        "EPIC": D.PURPLE,
        "LEGENDARY": D.ERROR,
        "MYTHIC": D.PINK
    }
    for rarity, filepath in RARITY_FILES.items():
        count = len(_safe_read_json(filepath)) if os.path.exists(filepath) else 0
        total += count
        color = color_map.get(rarity, D.LIGHT)
        print(f"  {color}{D.BOLD}* {rarity}: {count}{D.RST}")
    hunter_count = len(_safe_read_json(HUNTER_FILE)) if os.path.exists(HUNTER_FILE) else 0
    print(f"  {D.GOLD}{D.BOLD}[HUNTER] Hunter: {hunter_count}{D.RST}")
    basic_count = len([f for f in os.listdir(COUPLE_BASIC_FOLDER) if f.endswith(('.json', '.jsonl'))]) if os.path.exists(COUPLE_BASIC_FOLDER) else 0
    rare_count = len([f for f in os.listdir(COUPLE_RARE_FOLDER) if f.endswith(('.json', '.jsonl'))]) if os.path.exists(COUPLE_RARE_FOLDER) else 0
    print(f"  {D.COUPLE}{D.BOLD}<3 Basic Couples: {basic_count}{D.RST}")
    print(f"  {D.PINK}{D.BOLD}<=3 Rare Couples : {rare_count}{D.RST}")
    total += basic_count + rare_count
    print(f"\n  {D.GOLD}{D.BOLD}* Total: {total}{D.RST}")
    print()
    input(f"{BORDER}{D.BOLD}└─>{D.RST} enter buat lanjut...")

def cleaner():
    clear_screen()
    display_banner()
    box_header("CLEANER")
    print(pline(f"{D.WARNING}{D.BOLD}[!] ini bakal hapus SEMUA akun tersimpan{D.RST}"))
    print(pline(f"{D.WARNING}{D.BOLD}(termasuk Hunter & Couples)!!{D.RST}"))
    confirm = input(f"{BORDER}{D.BOLD}└─>{D.RST} ketik {D.ERROR}{D.BOLD}CONFIRM{D.RST} buat lanjut: ").strip()
    if confirm.upper() == "CONFIRM":
        _flush_storage_buffer()
        deleted = 0
        for filepath in RARITY_FILES.values():
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    deleted += 1
                except:
                    pass
        if os.path.exists(HUNTER_FILE):
            try:
                os.remove(HUNTER_FILE)
                deleted += 1
            except:
                pass
        for folder in [COUPLE_BASIC_FOLDER, COUPLE_RARE_FOLDER]:
            if os.path.exists(folder):
                for f in os.listdir(folder):
                    if f.endswith(('.json', '.jsonl')):
                        try:
                            os.remove(os.path.join(folder, f))
                            deleted += 1
                        except:
                            pass
        print(f"\n{D.SUCCESS}{D.BOLD}hapus {deleted} file beres{D.RST}")
    else:
        print(f"\n{D.ERROR}{D.BOLD}batal{D.RST}")
    input(f"{BORDER}{D.BOLD}└─>{D.RST} enter buat lanjut...")

def about():
    clear_screen()
    display_banner()
    w = 64
    print(f"{D.PRIMARY}{D.BOLD}╔{'═' * w}╗{D.RST}")
    title = "ABOUT  •  AFRIEZX GEN V4"
    print(f"{D.PRIMARY}{D.BOLD}║{D.RST}{D.PURPLE}{D.BOLD}{title.center(w)}{D.RST}{D.PRIMARY}{D.BOLD}║{D.RST}")
    print(f"{D.PRIMARY}{D.BOLD}╠{'═' * w}╣{D.RST}")
    lines = [
        (D.LIGHT, "AFRIEZ-X GEN V4"),
        (D.GOLD, "Purple Void UI Edition"),
        (D.CYAN, "Python 3.14  •  Termux  •  Mobile"),
        (D.LIGHT, ""),
        (D.GOLD, "Change-logs updated V4 [+]"),
        (D.SUCCESS, "- Generator inti disalin ke V4"),
        (D.WARNING, "- Signature HMAC register dipakai"),
        (D.PURPLE, "- Hunter generator makin nempel"),
        (D.ERROR, "- UI diganti total"),
    ]
    for color, line in lines:
        print(f"{D.PRIMARY}{D.BOLD}║{D.RST}{color}{D.BOLD}{line.center(w)}{D.RST}{D.PRIMARY}{D.BOLD}║{D.RST}")
    print(f"{D.PRIMARY}{D.BOLD}╚{'═' * w}╝{D.RST}")
    print()
    input(f"{BORDER}{D.BOLD}└─>{D.RST} enter buat lanjut...")

def hunter_lock_flow():
    global HUNTER_MODE, HUNTER_TARGETS, GHOST_MODE
    clear_screen()
    display_banner()
    box_header("[HUNTER] LOCK RARITY TARGET")
    print(pline(f"{D.LIGHT}{D.BOLD}pilih rarity target (pisah pakai /){D.RST}"))
    print(pline(f"{D.LIGHT}{D.BOLD}contoh: 1/2 buat Uncommon & Epic{D.RST}"))
    print(menuline(0, "1", "UNCOMMON"))
    print(menuline(1, "2", "EPIC"))
    print(menuline(2, "3", "MYTHIC"))
    print(menuline(3, "4", "LEGENDARY"))
    print(box_footer())
    choice = input(f"\n{BORDER}{D.BOLD}└─>{D.RST} pilihan (misal 1/2/4): {D.INPUT}{D.BOLD}").strip()
    print(D.RST, end='')
    if not choice:
        print(f"{D.ERROR}{D.BOLD}inputnya kosong!{D.RST}")
        input("enter...")
        return
    parts = choice.replace(' ', '').split('/')
    rarity_map = {"1": "UNCOMMON", "2": "EPIC", "3": "MYTHIC", "4": "LEGENDARY"}
    targets = []
    for p in parts:
        if p in rarity_map:
            targets.append(rarity_map[p])
        else:
            print(f"{D.ERROR}{D.BOLD}'{p}' nggak valid!{D.RST}")
            input("enter...")
            return
    if not targets:
        print(f"{D.ERROR}{D.BOLD}nggak ada target yang valid!{D.RST}")
        input("enter...")
        return
    HUNTER_TARGETS = targets
    HUNTER_MODE = True
    ATTEMPTS["n"] = 0

    clear_screen()
    display_banner()
    box_header("PILIH REGION")
    regions = list(REGION_LANG.keys())
    for i, r in enumerate(regions, 1):
        print(menuline(i - 1, str(i), f"{r}  ({REGION_LANG[r]})"))
    print(menuline(len(regions), "12", "GHOST MODE"))
    print(box_footer())
    region_choice = input(f"\n{BORDER}{D.BOLD}└─>{D.RST} pilih nomor region: ").strip()
    if region_choice == "12":
        GHOST_MODE = True
        region = "ID"
    else:
        GHOST_MODE = False
        if not region_choice.isdigit():
            print(f"{D.ERROR}{D.BOLD}nggak valid!{D.RST}")
            input("enter...")
            return
        idx = int(region_choice) - 1
        if idx < 0 or idx >= len(regions):
            print(f"{D.ERROR}{D.BOLD}region nggak ada!{D.RST}")
            input("enter...")
            return
        region = regions[idx]

    clear_screen()
    display_banner()
    box_header("SETTING GENERATOR")
    print(pline(f"{D.LIGHT}{D.BOLD}Region : {region_colored_text(region)}"))
    print(pline(f"{D.LIGHT}{D.BOLD}Target : {D.GOLD}{D.BOLD}{', '.join(HUNTER_TARGETS)}"))
    print(box_footer())
    name_prefix = input(f"{BORDER}{D.BOLD}└─>{D.RST} nama prefix [default: AfriezX]: {D.INPUT}{D.BOLD}").strip() or "AfriezX"
    print(D.RST, end='')
    count = input(f"{BORDER}{D.BOLD}└─>{D.RST} jumlah akun: {D.INPUT}{D.BOLD}").strip()
    print(D.RST, end='')
    if not count.isdigit():
        print(f"{D.ERROR}{D.BOLD}nggak valid!{D.RST}")
        input("enter...")
        return
    count = int(count)
    threads = input(f"{BORDER}{D.BOLD}└─>{D.RST} threads [default: 50, max 100]: {D.INPUT}{D.BOLD}").strip()
    print(D.RST, end='')
    if threads.isdigit():
        threads = int(threads)
        if threads > 100:
            threads = 100
    else:
        threads = 50

    clear_screen()
    display_banner()
    box_header("HUNTER LOCK GEN")
    print(pline(f"{D.LIGHT}{D.BOLD}Region  : {region_colored_text(region)}"))
    print(pline(f"{D.LIGHT}{D.BOLD}Target  : {D.GOLD}{D.BOLD}{count}{D.RST}"))
    print(pline(f"{D.LIGHT}{D.BOLD}Threads : {D.GOLD}{D.BOLD}{threads}{D.RST}"))
    print(pline(f"{D.LIGHT}{D.BOLD}Hunter  : {D.GOLD}{D.BOLD}{', '.join(HUNTER_TARGETS)}"))
    print(box_footer())
    generate(region, name_prefix, count, threads, is_ghost=GHOST_MODE)
    HUNTER_MODE = False
    GHOST_MODE = False

def region_colored_text(region):
    return f"{D.GOLD}{D.BOLD}{region}{D.RST}"

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

INTRO_GLYPHS = {
    "A": [" ███ ", "██ ██", "█████", "██ ██", "██ ██"],
    "F": ["█████", "██   ", "████ ", "██   ", "██   "],
    "R": ["█████", "██ ██", "████ ", "██ ██", "██ ██"],
    "I": ["█████", "  ██ ", "  ██ ", "  ██ ", "█████"],
    "E": ["█████", "██   ", "████ ", "██   ", "█████"],
    "Z": ["█████", "   ██", "  ██ ", " ██  ", "█████"],
    "X": [" ██   ██", "  ██ ██", "   ███ ", "  ██ ██", " ██   ██"],
    "G": [" ███ ", "██   ", "██ ██", "██ ██", " ███ "],
    "N": ["██  ██", "███ ██", "██ ███", "██  ██", "██  ██"],
    "V": ["██ ██", "██ ██", "██ ██", "██ ██", " ███ "],
    "4": ["██  ██", "██  ██", "██████", "    ██", "    ██"],
}

def _intro_fit(content="", width=48):
    w = len(re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", content))
    if w >= width: return content[:width]
    total = width - w
    left = total // 2
    return (" " * left) + content + (" " * (total - left))

def _logo_block(word, grad, side_fn):
    for row in range(5):
        parts = []
        for i, ch in enumerate(word):
            parts.append(f"\033[38;5;{grad[i]}m{D.BOLD}{INTRO_GLYPHS[ch][row]}{D.RST}")
        side_fn(" ".join(parts))
    shadow = " ".join(f"{PURPLE_DARK}{'▀' * len(INTRO_GLYPHS[ch][0])}{D.RST}" for ch in word)
    side_fn(shadow)

def display_intro():
    clear_screen()
    box_w = 48
    term_w = shutil.get_terminal_size((60, 24)).columns
    def pad(line):
        gap = (term_w - vlen(line)) // 2
        return (" " * gap if gap > 0 else "") + line
    def out(line=""):
        print(pad(line) if line else "")
    def side(content=""):
        out(f"{BORDER}║{D.RST}{_intro_fit(content, box_w)}{BORDER}║{D.RST}")
    def frame(left, fill, right):
        out(f"{BORDER}{left}{D.RST}{grad_hline(box_w)}{BORDER}{right}{D.RST}")
    out()
    frame("╔", None, "╗")
    side()
    _logo_block("AFRIEZX", [213, 207, 176, 141, 135, 99, 93], side)
    side()
    _logo_block("GEN", [213, 183, 135], side)
    side()
    frame("╚", None, "╝")
    out()
    frame("╔", None, "╗")
    side(f"{D.BOLD}\033[38;5;203mSCRIPT INI FREE JANGAN DIJUAL!!{D.RST}")
    side(f"{D.BOLD}{D.GOLD}--AFRIEZZA{D.RST}")
    frame("╚", None, "╝")
    out()
    def bare(content=""):
        out(_intro_fit(content, box_w))
    _logo_block("V4", [207, 135], bare)
    out()

def display_banner():
    clear_screen()
    panel_width = 62
    word = "AFRIEZX"
    glyphs = {
        "A": [" ███ ", "██ ██", "█████", "██ ██", "██ ██"],
        "F": ["█████", "██   ", "████ ", "██   ", "██   "],
        "R": ["█████", "██ ██", "████ ", "██ ██", "██ ██"],
        "I": ["█████", "  ██ ", "  ██ ", "  ██ ", "█████"],
        "E": ["█████", "██   ", "████ ", "██   ", "█████"],
        "Z": ["█████", "   ██", "  ██ ", " ██  ", "█████"],
        "X": [" ██   ██", "  ██ ██", "   ███ ", "  ██ ██", " ██   ██"],
    }
    ansi_re = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
    def visible_width(value): return len(ansi_re.sub("", value))
    def fit_center(content="", width=panel_width):
        w = visible_width(content)
        if w >= width: return content[:width]
        total = width - w
        left = total // 2
        return (" " * left) + content + (" " * (total - left))
    def side_line(content=""):
        print(f"{BORDER}║{D.RST}{fit_center(content)}{BORDER}║{D.RST}")
    print()
    print(f"{BORDER}╔{D.RST}{grad_hline(panel_width)}{BORDER}╗{D.RST}")
    side_line()
    letter_grad = [213, 207, 176, 141, 135, 99, 93]
    for row in range(5):
        parts = []
        for i, ch in enumerate(word):
            c = letter_grad[i]
            parts.append(f"\033[38;5;{c}m{D.BOLD}{glyphs[ch][row]}{D.RST}")
        side_line(" ".join(parts))
    shadow_parts = []
    for ch in word:
        wlen = len(glyphs[ch][0])
        shadow_parts.append(f"{PURPLE_DARK}{'▀' * wlen}{D.RST}")
    side_line(" ".join(shadow_parts))
    side_line()
    subtitle = f"{grad_text('GENERATOR AFRIEZX')} {PURPLE_DIM}{D.BOLD}•{D.RST} {D.BOLD}{PURPLE_DIM}VOID EDITION{D.RST}"
    side_line(subtitle)
    side_line()
    print(f"{BORDER}╚{D.RST}{grad_hline(panel_width)}{BORDER}╝{D.RST}")
    print()
    tagline = grad_text("⚡ GENERATOR | HUNTER | COUPLE ⚡")
    print(f"{fit_center(tagline, 62)}")
    print(f"{grad_hline(62, '─')}")
    print()

def safe_exit(signum=None, frame=None):
    global EXIT
    EXIT = True
    print(f"\n{D.ERROR}{D.BOLD}Exiting...{D.RST}")
    sys.exit(0)

def main_menu():
    while True:
        clear_screen()
        display_banner()
        box_header("MAIN MENU")
        items = [
            ("1", "Generate Accounts", D.ACCENT),
            ("2", "Hunter Lock Rarity", D.GOLD),
            ("3", "View Accounts", D.SUCCESS),
            ("4", "Statistics", D.INFO),
            ("5", "Cleaner", D.WARNING),
            ("6", "About", D.PURPLE),
            ("0", "Exit", D.ERROR)
        ]
        for i, (num, label, color) in enumerate(items):
            print(menuline(i, num, label))
        print(box_footer())
        choice = input(f"\n{BORDER}{D.BOLD}└─>{D.RST} pilih menu: ").strip()
        if choice == "1":
            clear_screen()
            display_banner()
            box_header("PILIH REGION")
            regions = list(REGION_LANG.keys())
            for i, r in enumerate(regions, 1):
                print(menuline(i - 1, str(i), f"{r}  ({REGION_LANG[r]})"))
            print(menuline(len(regions), "12", "GHOST MODE"))
            print(box_footer())
            region_choice = input(f"\n{BORDER}{D.BOLD}└─>{D.RST} pilih nomor region: ").strip()
            if region_choice == "12":
                GHOST_MODE = True
                region = "ID"
            else:
                GHOST_MODE = False
                if not region_choice.isdigit(): continue
                idx = int(region_choice) - 1
                if idx < 0 or idx >= len(regions): continue
                region = regions[idx]
            clear_screen()
            display_banner()
            box_header("SETTING GENERATOR")
            print(pline(f"{D.LIGHT}{D.BOLD}Region : {region_colored_text(region)}"))
            print(box_footer())
            name_prefix = input(f"{BORDER}{D.BOLD}└─>{D.RST} nama prefix [default: AfriezX]: {D.INPUT}{D.BOLD}").strip() or "AfriezX"
            print(D.RST, end='')
            count = input(f"{BORDER}{D.BOLD}└─>{D.RST} jumlah akun: {D.INPUT}{D.BOLD}").strip()
            print(D.RST, end='')
            if not count.isdigit(): continue
            count = int(count)
            threads = input(f"{BORDER}{D.BOLD}└─>{D.RST} threads [default: 50, max 100]: {D.INPUT}{D.BOLD}").strip()
            print(D.RST, end='')
            if threads.isdigit():
                threads = int(threads)
                if threads > 100: threads = 100
            else: threads = 50
            clear_screen()
            display_banner()
            box_header("GENERATE AKUN")
            print(pline(f"{D.LIGHT}{D.BOLD}Region  : {region_colored_text(region)}"))
            print(pline(f"{D.LIGHT}{D.BOLD}Target  : {D.GOLD}{D.BOLD}{count}{D.RST}"))
            print(pline(f"{D.LIGHT}{D.BOLD}Threads : {D.GOLD}{D.BOLD}{threads}{D.RST}"))
            print(box_footer())
            ATTEMPTS["n"] = 0
            HUNTER_MODE = False
            generate(region, name_prefix, count, threads, is_ghost=GHOST_MODE)
        elif choice == "2":
            hunter_lock_flow()
        elif choice == "3":
            view_rarity_menu()
        elif choice == "4":
            stats()
        elif choice == "5":
            cleaner()
        elif choice == "6":
            about()
        elif choice == "0":
            safe_exit()
        else:
            continue

if __name__ == "__main__":
    sys.stdout.write("\033]11;#0b0b12\007")
    sys.stdout.flush()
    signal.signal(signal.SIGINT, safe_exit)
    signal.signal(signal.SIGTERM, safe_exit)
    try:
        display_intro()
        input(f"{BORDER}{D.BOLD}└─>{D.RST} enter buat masuk...")
        main_menu()
    except KeyboardInterrupt:
        safe_exit()