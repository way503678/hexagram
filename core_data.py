# -*- coding: utf-8 -*-
"""
命卦排盤 - 核心常數與對照表
統一規則：
  - 爻序方向：由下而上，index 0=初爻（最下），index 5=上爻（最上）
  - 卦鍵格式：(上卦, 下卦)
"""

# ============================================================
# 八卦爻象（由下而上，1=陽，0=陰）
# ============================================================
TRIGRAM_LINES = {
    "乾": [1, 1, 1],  # ☰
    "兌": [1, 1, 0],  # ☱  上陰中陽初陽
    "離": [1, 0, 1],  # ☲
    "震": [1, 0, 0],  # ☳  上陰中陰初陽
    "巽": [0, 1, 1],  # ☴  上陽中陽初陰
    "坎": [0, 1, 0],  # ☵
    "艮": [0, 0, 1],  # ☶  上陽中陰初陰
    "坤": [0, 0, 0],  # ☷
}

# 由爻象反查卦名
LINES_TO_TRIGRAM = {tuple(v): k for k, v in TRIGRAM_LINES.items()}

# 梅花易數卦序：乾1、兌2、離3、震4、巽5、坎6、艮7、坤8
TRIGRAM_NUMBERS = {1: "乾", 2: "兌", 3: "離", 4: "震", 5: "巽", 6: "坎", 7: "艮", 8: "坤"}
TRIGRAM_TO_NUMBER = {v: k for k, v in TRIGRAM_NUMBERS.items()}

# 顯示用符號（box-drawing U+2500，視覺上完全連續的直線）
YANG       = "───"   # 靜陽：完全不斷的一條直線
YIN        = "─ ─"   # 靜陰：中間中斷
YANG_DONG  = "─O─"   # 動陽：取代靜陽形狀
YIN_DONG   = "─X─"   # 動陰：取代靜陰形狀

def line_symbol(n, is_moving=False):
    """
    回傳爻象符號。
    n=1 為陽爻，n=0 為陰爻；is_moving=True 時回傳動爻符號（取代靜爻形狀）。
    """
    if is_moving:
        return YANG_DONG if n == 1 else YIN_DONG
    return YANG if n == 1 else YIN


# ============================================================
# 五行
# ============================================================

# 地支五行
BRANCH_ELEMENT = {
    "子": "水", "亥": "水",
    "寅": "木", "卯": "木",
    "巳": "火", "午": "火",
    "申": "金", "酉": "金",
    "辰": "土", "戌": "土", "丑": "土", "未": "土",
}

# 八卦五行（卦宮也用這個）
TRIGRAM_ELEMENT = {
    "乾": "金", "兌": "金",
    "離": "火",
    "震": "木", "巽": "木",
    "坎": "水",
    "艮": "土", "坤": "土",
}

def relation(me_element, other_element):
    """
    以「我」的五行判斷「他」的六親
    規則：
      同我者 = 兄弟
      我生者 = 子孫
      生我者 = 父母
      我剋者 = 妻財
      剋我者 = 官鬼
    """
    if me_element == other_element:
        return "兄弟"
    sheng = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}  # 我生他
    ke   = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}  # 我剋他
    if sheng[me_element] == other_element:
        return "子孫"
    if sheng[other_element] == me_element:
        return "父母"
    if ke[me_element] == other_element:
        return "妻財"
    if ke[other_element] == me_element:
        return "官鬼"
    return "?"


# ============================================================
# 干支
# ============================================================

HEAVENLY_STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
EARTHLY_BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 六十甲子
SEXAGENARY = [
    HEAVENLY_STEMS[i % 10] + EARTHLY_BRANCHES[i % 12] for i in range(60)
]

def day_ganzhi(dt):
    """
    計算某公曆日期的日干支。
    換日規則：以 00:00 換日（題主指定：子時分子，23:00 仍算當天）。
    
    基準：公元 1900-01-01 為「甲戌」日（此為已驗證基準點）
    甲戌在六十甲子中 index = 10 (甲子=0, 乙丑=1, ..., 甲戌=10)
    """
    from datetime import datetime, date
    if isinstance(dt, datetime):
        d = dt.date()
    else:
        d = dt
    base = date(1900, 1, 1)
    delta = (d - base).days
    idx = (10 + delta) % 60
    return SEXAGENARY[idx]


# ============================================================
# 時干支（五鼠遁：依日干推子時干，後依時辰地支順推）
# ============================================================
# 五鼠遁口訣：
#   甲己還加甲，乙庚丙作初，
#   丙辛從戊起，丁壬庚子居，
#   戊癸何方發，壬子是真途。
# 依日干推子時的天干，其他時辰順推。
# 註：此函式純屬天干地支邏輯，不處理換日問題；
#     呼叫端需先依自己的換日規則決定當天的日干，再傳入。
DAY_STEM_TO_ZI_HOUR_STEM = {
    "甲": "甲", "己": "甲",
    "乙": "丙", "庚": "丙",
    "丙": "戊", "辛": "戊",
    "丁": "庚", "壬": "庚",
    "戊": "壬", "癸": "壬",
}

def hour_ganzhi(day_stem, hour):
    """
    時干支。day_stem=當天（由呼叫端依換日規則決定的）日干，hour=0–23 公曆小時。
    本專案採「00:00 換日」：23:00 仍算當天、00:00 起算隔日，
    所以呼叫此函式前 day_stem 必須已依此規則決定。
    """
    zi_stem = DAY_STEM_TO_ZI_HOUR_STEM[day_stem]
    stem_start_idx = HEAVENLY_STEMS.index(zi_stem)
    shichen = hour_to_shichen(hour)  # 1=子、2=丑、... 12=亥
    offset = shichen - 1
    stem = HEAVENLY_STEMS[(stem_start_idx + offset) % 10]
    branch = EARTHLY_BRANCHES[offset % 12]  # 子丑寅卯...亥
    return stem + branch


# ============================================================
# 六神（依日干起）
# ============================================================
# 口訣：甲乙起青龍，丙丁起朱雀，戊日起勾陳，己日起螣蛇，
#       庚辛起白虎，壬癸起玄武。順序：青龍→朱雀→勾陳→螣蛇→白虎→玄武
SIX_SPIRITS = ["青龍", "朱雀", "勾陳", "螣蛇", "白虎", "玄武"]

STEM_TO_SPIRIT_START = {
    "甲": 0, "乙": 0,
    "丙": 1, "丁": 1,
    "戊": 2,
    "己": 3,
    "庚": 4, "辛": 4,
    "壬": 5, "癸": 5,
}

def six_spirits_by_stem(day_stem):
    """回傳 6 爻的六神（由下而上：初爻、二爻、...、上爻）"""
    start = STEM_TO_SPIRIT_START[day_stem]
    return [SIX_SPIRITS[(start + i) % 6] for i in range(6)]


# ============================================================
# 時辰 → 動爻
# 子=1、丑=2、...、亥=12
# 動爻 = 時辰數 mod 6（0 視為 6）
# ============================================================

HOUR_TO_BRANCH = [
    # (起始小時, 結束小時, 地支, 時辰序號)
    # 23~01 為子時（序號1），01~03 丑時（2），...
]

def hour_to_shichen(hour):
    """公曆小時（0-23）轉時辰序號（1=子、2=丑、...、12=亥）"""
    # 23:00~00:59 子時
    if hour == 23 or hour == 0:
        return 1
    # 01~02 丑, 03~04 寅, ...
    return (hour + 1) // 2 + 1

def hour_to_branch(hour):
    """公曆小時轉時辰地支"""
    shichen = hour_to_shichen(hour)
    return EARTHLY_BRANCHES[(shichen - 1) % 12]
