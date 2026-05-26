# -*- coding: utf-8 -*-
"""
divination.core.signals — 訊號發射與去重

提供共用的訊號處理函式，所有面向（aspects）都會用到。

核心功能：
  - emit(out, level, text, yao):  訊號發射，自帶引動效應 + 當值調整 + 標籤
  - dedupe(signals):              訊號去重（同 text 取等級最重者）
  - check_evidence(...):          強化條件原則（多重條件命中才下結論）

訊號等級：「吉 / 中 / 警 / 凶」四級
"""

# 等級順序與索引
_LEVEL_ORDER = ["中", "警", "凶"]
_LEVEL_INDEX = {"吉": -1, "中": 0, "警": 1, "凶": 2}
_LEVEL_RANK  = {"凶": 4, "警": 3, "中": 2, "吉": 1}


# ============================================================
# 當值狀態的等級調整
# ============================================================
_ATTENDANCE_ADJUST = {
    "臨值": 0,    # 由 engagement_effect 用「動值/靜值」處理
    "三合": +1,   # 三合得令，升一級
    "月生": 0,
    "月沖": 0,    # 由 engagement_effect 處理
    "月剋": -1,   # 失令，訊號減弱
    "平":   0,
}


def adjust_level(orig_level, attendance):
    """
    依當值狀態調整訊號等級。
    "吉" 不調整（避免吉慶被升到「凶」）。
    """
    if orig_level == "吉":
        return orig_level
    adj = _ATTENDANCE_ADJUST.get(attendance, 0)
    if adj == 0:
        return orig_level
    idx = _LEVEL_INDEX.get(orig_level, 0)
    new_idx = max(0, min(2, idx + adj))
    return _LEVEL_ORDER[new_idx]


# ============================================================
# 引動效應（傳統六爻學動爻引動規則 7 種）
# ============================================================
def engagement_effect(yao):
    """
    爻對當值（流年/流月地支）的引動狀態 — 傳統六爻學判定。

    回傳 7 種：
      "動值":   動爻 + 臨值（爻地支 = 當值地支）— 動而當令，訊號最強
      "動沖":   動爻 + 被沖 — 沖散，訊號弱
      "動合":   動爻 + 被合 — 合住，動不了
      "靜值":   靜爻 + 臨值 — 應事
      "靜沖":   靜爻 + 被沖 — 暗動
      "靜合":   靜爻 + 被合 — 合住，不報
      "無事":   完全沒被引動 — 動爻「動而懸空」、靜爻「安靜」，皆不報訊號
    """
    hc = yao.get("合沖", "")
    att = yao.get("當值", "")
    is_dong = bool(yao.get("動爻"))
    is_臨值 = (att == "臨值")
    is_沖 = (hc == "相沖")
    is_合 = (hc == "相合")

    if is_dong:
        if is_臨值: return "動值"
        if is_沖:   return "動沖"
        if is_合:   return "動合"
        return "無事"
    else:
        if is_臨值: return "靜值"
        if is_沖:   return "靜沖"
        if is_合:   return "靜合"
        return "無事"


def apply_engagement_to_level(orig_level, yao):
    """
    依爻的引動狀態調整訊號等級。
    回傳 (new_level, should_emit)
    "吉" 不降。
    """
    if orig_level == "吉":
        return orig_level, True
    effect = engagement_effect(yao)

    # 維持原等級：動值、動沖（沖散其實降但保留訊號）、靜值、靜沖
    if effect in ("動值", "靜值", "靜沖"):
        return orig_level, True

    # 降一級：動沖、動合
    if effect in ("動沖", "動合"):
        idx = _LEVEL_INDEX.get(orig_level, 0)
        new_idx = max(0, idx - 1)
        return _LEVEL_ORDER[new_idx], True

    # 不報：靜合、無事
    if effect in ("靜合", "無事"):
        return orig_level, False

    return orig_level, True


# ============================================================
# 訊號發射（封裝 emit 邏輯）
# ============================================================
_TAG_MAP = {
    "動值": "[動而當令]",
    "動沖": "[動沖散]",
    "動合": "[動合住]",
    "靜值": "[臨值應事]",
    "靜沖": "[靜暗動]",
}


def emit(out, level, text, yao=None):
    """
    通用訊號發射函式。

    傳入 yao 時，自動做兩層處理：
      1. 引動效應（傳統）：依爻是否被當月引動決定是否報、要不要降級
      2. 當值調整：三合 → 升級，月剋 → 降級

    "吉" 訊號繞過引動判定（吉慶可以靜態存在）。

    參數：
      out:   訊號 list（會被 mutate）
      level: 原始等級「吉/中/警/凶」
      text:  訊號文字
      yao:   爻的 entry dict（含「動爻」「合沖」「當值」等）。
             為 None 時不做引動 / 當值處理，直接 append。
    """
    if yao is None:
        out.append({"level": level, "text": text})
        return

    # 1. 引動效應
    level, should_emit = apply_engagement_to_level(level, yao)
    if not should_emit:
        return

    # 2. 當值調整
    att = yao.get("當值", "")
    level = adjust_level(level, att)

    # 3. 加標籤
    effect = engagement_effect(yao)
    if effect in _TAG_MAP:
        text = text + " " + _TAG_MAP[effect]
    if att == "三合":
        text = text + " [三合]"
    elif att == "月剋":
        text = text + " [月剋,輕]"

    # 4. 塞入爻位資訊（用 _yao_key 開頭以隱藏，不影響 template）
    # _yao_key 用「爻序名+六親」聚合，比純爻序名更精確
    # 例：「四爻妻財」的所有訊號可以聚成一條
    signal = {"level": level, "text": text}
    if "爻序名" in yao:
        signal["_yao_key"] = f"{yao['爻序名']}{yao.get('六親','')}"
        signal["_yao_index"] = yao.get("index", -1)
    out.append(signal)


def emit_static(out, level, text, yao=None):
    """
    發射「靜態類象訊號」— 不經過引動效應與當值調整，直接保留原 level。

    用途：類象描述、職業類型、財運性質等不依靠引動就成立的訊號。
    例：「妻財臨青龍 — 財運性質：正財...」這條描述跟動靜無關，
        即使該爻在當月「無事」也應該保留。

    與 emit() 的差異：
      - emit:        會被「靜爻無事」「靜爻被合」等狀態吃掉訊號
      - emit_static: 一律保留訊號，只是仍會帶上 _yao_key 讓 merge_by_yao 能聚合

    參數同 emit。yao 不為 None 時會塞入爻位資訊。
    """
    signal = {"level": level, "text": text}
    if yao is not None and "爻序名" in yao:
        signal["_yao_key"] = f"{yao['爻序名']}{yao.get('六親','')}"
        signal["_yao_index"] = yao.get("index", -1)
    out.append(signal)


# ============================================================
# 訊號去重
# ============================================================
def dedupe(signals):
    """
    對訊號 list 去重：
      - 同 text 重複出現 → 只保留等級最重的那一條
      - 等級就高不就低（凶 > 警 > 中 > 吉）
    保留原本順序（以第一次出現的位置為準）。
    """
    if not signals:
        return signals

    seen = {}  # text -> (rank_value, signal_dict, first_index)
    for idx, s in enumerate(signals):
        t = s["text"]
        r = _LEVEL_RANK.get(s["level"], 0)
        if t not in seen or r > seen[t][0]:
            first_idx = seen[t][2] if t in seen else idx
            seen[t] = (r, s, first_idx)
    return [v[1] for v in sorted(seen.values(), key=lambda v: v[2])]


# ============================================================
# 訊號按爻聚合（方案 A）
# 同一爻的多條訊號合併成「主訊號 + 補述」格式
# ============================================================
def merge_by_yao(signals):
    """
    把同一爻（依 _yao_key）的多條訊號合併成一條多行描述。

    主訊號規則：
      - 取該爻所有訊號中等級最高的一條為「主訊號」
      - 同等級時取第一條
      - 主訊號保留原 level

    補述格式：
      - 其他訊號變成 sub-bullet，前綴「· 」
      - 移除重複的開頭詞（如「今年妻財」「四爻妻財」這類前綴）
      - 保留尾部標籤（[動合住]、[月剋,輕] 等）

    沒有 _yao_key 的訊號（不關聯任何爻的卦面綜合徵兆）保持獨立。

    回傳：list of {"level": ..., "text": ...}（不含 _yao_key 等內部欄位）
    """
    if not signals:
        return signals

    # 分組：有 _yao_key 的依爻位聚合；沒有的維持原樣
    groups = {}  # yao_key -> [signals]
    standalone = []  # 沒有 _yao_key 的訊號（按原順序）
    order = []  # 紀錄 yao_key 第一次出現的順序

    for idx, s in enumerate(signals):
        yk = s.get("_yao_key")
        if yk:
            if yk not in groups:
                groups[yk] = []
                order.append(("group", yk))
            groups[yk].append(s)
        else:
            standalone.append((idx, s))
            order.append(("standalone", idx))

    # 整理輸出
    standalone_map = {idx: s for idx, s in standalone}
    result = []
    for kind, key in order:
        if kind == "standalone":
            s = standalone_map[key]
            # 移除內部欄位
            result.append(_clean_signal(s))
        else:
            group = groups[key]
            if len(group) == 1:
                # 只有一條，直接輸出
                result.append(_clean_signal(group[0]))
            else:
                # 多條合併
                result.append(_merge_group(group))

    return result


def _clean_signal(signal):
    """移除訊號內部欄位（_yao_key、_yao_index）"""
    return {k: v for k, v in signal.items() if not k.startswith("_")}


def _merge_group(group):
    """
    把同爻的多條訊號合併成「主訊號 + 補述」格式。

    產出結構：
      {
        "level": ...,
        "text": "主訊號文字",
        "sub": ["補述 1", "補述 2", ...]   # 補述 list（可選欄位）
      }

    若無補述，sub 欄位不會出現（向下相容於原本只有 text 的格式）。

    主訊號優先順序：
      1. 凶/警/吉（有明確判斷的）優先於「中」（描述性的）
      2. 凶 > 警 > 吉（嚴重的判斷優先）
      3. 同優先級時取第一條（保留原順序）
    """
    # 主訊號優先度：凶 > 警 > 吉 > 中
    _MAIN_PRIORITY = {"凶": 4, "警": 3, "吉": 2, "中": 1}

    def main_priority(s):
        return _MAIN_PRIORITY.get(s["level"], 0)

    sorted_group = sorted(enumerate(group), key=lambda x: (-main_priority(x[1]), x[0]))
    main_idx, main = sorted_group[0]

    # 收集補述
    subs = []
    for idx, s in enumerate(group):
        if idx == main_idx:
            continue
        text = _strip_redundant_prefix(s["text"], main["text"])
        subs.append(text)

    result = {
        "level": main["level"],
        "text": main["text"],
    }
    if subs:
        result["sub"] = subs
    return result


def _strip_redundant_prefix(text, main_text):
    """
    若補述開頭與主訊號的「時間+主詞」相同，去掉重複部分，讓補述讀起來簡潔。

    例：
      主訊號：「今年妻財臨青龍得生 — 主正財進益...」
      補述原文：「今年妻財被合 — 財被合走...」
      → 處理後：「妻財被合 — 財被合走...」（去掉「今年」前綴）
    """
    # 移除常見時間前綴
    for prefix in ["今年", "本卦"]:
        if text.startswith(prefix) and main_text.startswith(prefix):
            text = text[len(prefix):]
            break

    # 月份前綴比較動態（正月～臘月），用簡單對齊：取主訊號開頭直到「—」或第一個爻序詞
    # 為避免複雜，月份前綴先不處理（流月本來就有月份標識）

    return text


# ============================================================
# 強化條件原則
# ============================================================
def check_evidence(conditions, min_required=2):
    """
    強化條件原則 — 多重條件命中才下結論。

    用於：
      - 第三者徵兆判定（不可單看「兩現」就斷）
      - 健康嚴重訊號（不可單看「動爻」就斷）
      - 工作職位變動（不可單看「官鬼動」就斷）

    參數：
      conditions:    list of bool 或 list of (bool, weight) tuple
      min_required:  最少要命中幾個條件才算成立

    回傳：
      (is_evidence_sufficient, hit_count)
    """
    if not conditions:
        return False, 0

    hit_count = 0
    for c in conditions:
        if isinstance(c, tuple):
            cond, weight = c
            if cond:
                hit_count += weight
        else:
            if c:
                hit_count += 1
    return (hit_count >= min_required), hit_count


# ============================================================
# 六神語意輔助（共用）
# ============================================================
_LIUSHEN_NATURE = {
    "白虎": "凶",   # 血光、傷災、月經、流產、手術、外傷
    "玄武": "凶",   # 暗病、婦科泌尿、外遇、被偷
    "騰蛇": "凶",   # 怪病、神經、心理症狀、虛驚
    "螣蛇": "凶",   # 異體字
    "朱雀": "中",   # 口舌、文書、發炎、官司
    "勾陳": "中",   # 牽連、慢性、房地產、糾纏
    "青龍": "吉",   # 喜慶、姻緣、貴人、正財
}


def liushen_nature(ls):
    """六神性質：'吉' / '凶' / '中' / ''（無資料）"""
    return _LIUSHEN_NATURE.get((ls or "").strip(), "")


def normalize_tengshe(ls):
    """統一螣蛇/騰蛇為一種寫法（回傳「騰蛇」）"""
    if (ls or "").strip() in ("螣蛇", "騰蛇"):
        return "騰蛇"
    return (ls or "").strip()
