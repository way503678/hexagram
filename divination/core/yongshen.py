# -*- coding: utf-8 -*-
"""
divination.core.yongshen — 用神取捨與過旺反凶

最重要的新核心邏輯，四個面向都會用到。

核心功能：
  - select_primary(yongshens, world_yao, aspect, gender):
      用神兩現時的取捨函式，回傳 (primary, secondary, role_info)。
  - check_overflowing(yongshen, outer_branch, all_yao_rows):
      過旺反凶偵測（《增刪卜易》物極必反原則）。
  - get_yongshen_liuqin(aspect, gender):
      依面向回傳該面向的主用神六親類型。

設計原則（依 06 號筆記）：
  - 通用層：動 > 旺 > 不空（古法 / 野鶴擇一）、主卦 / 變卦時間軸、伏神優先級
  - 特化層：感情面的「陰陽異性 = 正配」、「臨應 = 正配」由 love.py 處理
"""
from core_data import BRANCH_ELEMENT
from .elements import strength_tier, twelve_phase, element_relation


# ============================================================
# 依面向取主用神六親類型
# ============================================================
def get_yongshen_liuqin(aspect, gender=None):
    """
    依面向回傳主用神六親。

    aspect: "love" / "health" / "work" / "wealth"
    gender: "M" / "F" / None

    回傳：六親名（"妻財"/"官鬼"/"父母"/"兄弟"/"子孫"）或 None（健康看世爻）
    """
    if aspect == "love":
        if gender == "F":
            return "官鬼"
        elif gender == "M":
            return "妻財"
        else:
            return None  # 不分性別，看妻財+官鬼兩條線
    elif aspect == "health":
        return None  # 自占用神 = 世爻
    elif aspect == "work":
        return "官鬼"  # 主用神，輔以父母
    elif aspect == "wealth":
        return "妻財"
    return None


# ============================================================
# 用神取捨（兩現以上時）
# ============================================================
def select_primary(yongshens, world_yao=None, response_yao=None,
                   aspect=None, gender=None):
    """
    從多個用神候選爻中選出主用神。

    取捨優先順序（共用基礎）：
      1. 動爻優先  — 動 > 靜
      2. 旺者優先  — 旺 > 衰
      3. 不空優先  — 不空不破 > 空破（古法；可由面向決定是否倒轉成野鶴派）
      4. 與世爻有生剋沖合關係者 > 無關係者
      5. 內卦近 > 外卦遠

    面向特化（感情面）：
      - 「機兆主用神」走通用 select_primary 邏輯（動爻優先）
      - 「角色正配」由 _select_love_primary_role 額外判定（臨應 > 陰陽異性）
      - 兩者可能是同一個爻，也可能不同
      - role_info["primary_role_yao"] / ["secondary_role_yao"] 標出「正配/偏配」具體在哪爻

    參數：
      yongshens:     候選用神爻 list
      world_yao:     世爻 entry
      response_yao:  應爻 entry
      aspect:        "love"/"health"/"work"/"wealth"
      gender:        "M"/"F"/None

    回傳：
      (primary, secondary, role_info)
        primary:    機兆主用神（取捨後最關鍵的爻，動者優先）
        secondary:  次用神
        role_info:  dict，內容因面向而異：
                    通用：{"primary_role": ..., "secondary_role": ..., "reason": ...}
                    感情面額外：
                      "love_zheng_yao":  正配（夫/妻）所在爻 entry
                      "love_pian_yao":   偏配 / 情人所在爻 entry
                      "love_zheng_reason": 為何認為它是正配（"臨應爻" / "陰陽異性與世匹配"）
    """
    if not yongshens:
        return None, None, {}

    if len(yongshens) == 1:
        return yongshens[0], None, {}

    # === Step 1: 動爻優先 ===
    moving = [y for y in yongshens if y.get("動爻")]
    static = [y for y in yongshens if not y.get("動爻")]

    reason_parts = []

    if len(moving) == 1:
        primary = moving[0]
        secondary = _pick_strongest(static, world_yao) if static else None
        reason_parts.append("動者優先(僅一動爻)")
    elif len(moving) > 1:
        # 多動爻 → 第二輪：旺者優先
        primary = _pick_strongest(moving, world_yao)
        others = [y for y in moving if y is not primary]
        secondary = others[0] if others else None
        reason_parts.append("多動爻 → 取與世有關係或內卦者")
    else:
        # 全靜 → 旺者優先
        primary = _pick_strongest(yongshens, world_yao)
        others = [y for y in yongshens if y is not primary]
        secondary = others[0] if others else None
        reason_parts.append("全靜 → 取與世有關係或內卦者")

    # === Step N: 依面向標註角色 ===
    role_info = _annotate_roles(primary, secondary, aspect, gender)
    role_info["reason"] = "、".join(reason_parts)

    # === 感情面額外：正配/偏配判定 ===
    if aspect == "love":
        zheng, pian, zheng_reason = _select_love_role(
            yongshens, world_yao, response_yao
        )
        if zheng is not None:
            role_info["love_zheng_yao"] = zheng
            role_info["love_pian_yao"] = pian
            role_info["love_zheng_reason"] = zheng_reason

    return primary, secondary, role_info


def _select_love_role(yongshens, world_yao, response_yao):
    """
    感情面正配/偏配判定（與通用主用神取捨並行）。

    優先順序：
      1. 臨應爻者為正配
      2. 與世爻陰陽異性者為正配（夫妻陰陽異性結合）
      3. 都無法判定 → 不標註（回傳 None, None, None）

    回傳：(zheng_yao, pian_yao, reason)
    """
    if not yongshens or len(yongshens) < 2:
        return None, None, None

    # 規則 1: 臨應爻者為正配
    if response_yao is not None:
        resp_idx = response_yao.get("爻序index")
        if resp_idx is not None:
            on_response = [y for y in yongshens if y.get("爻序index") == resp_idx]
            if len(on_response) == 1:
                zheng = on_response[0]
                pian_candidates = [y for y in yongshens if y is not zheng]
                pian = pian_candidates[0] if pian_candidates else None
                return zheng, pian, "臨應爻"

    # 規則 2: 與世爻陰陽異性者為正配
    if world_yao is not None:
        world_yy = world_yao.get("陰陽")
        if world_yy in ("陰", "陽"):
            opposite = "陽" if world_yy == "陰" else "陰"
            异性者 = [y for y in yongshens if y.get("陰陽") == opposite]
            同性者 = [y for y in yongshens if y.get("陰陽") == world_yy]
            if len(异性者) == 1 and len(同性者) >= 1:
                zheng = 异性者[0]
                pian = 同性者[0]
                return zheng, pian, "陰陽異性與世匹配"

    return None, None, None


def _pick_strongest(yaos, world_yao=None):
    """
    從爻 list 中挑出「最強」的一個。

    判準：
      1. 與世爻有生剋沖合關係者優先（不為「平」）
      2. 不空 > 空（爻沒空亡標記時跳過此步）
      3. 內卦（index 0-2）優先於外卦（index 3-5）
      4. 都同條件 → 取第一個
    """
    if not yaos:
        return None
    if len(yaos) == 1:
        return yaos[0]

    def score(y):
        s = 0
        # 與世爻有關係
        if y.get("生剋") and y["生剋"] != "":
            s += 1
        if y.get("合沖") in ("相沖", "相合"):
            s += 1
        # 內卦（爻序 0-2 為內卦，3-5 為外卦）
        if y.get("爻序index", 5) < 3:
            s += 1
        return s

    yaos_sorted = sorted(yaos, key=score, reverse=True)
    return yaos_sorted[0]


def _annotate_roles(primary, secondary, aspect, gender):
    """
    依面向標註 primary / secondary 的角色名稱。

    這只負責「命名」，不負責進一步判讀（如「是不是第三者」），
    那是 aspects/love.py 等模組的工作。
    """
    if not secondary:
        return {}

    if aspect == "love":
        return {
            "primary_role":   "正配（夫/妻）",
            "secondary_role": "情人/偏配/競爭對手",
        }
    elif aspect == "work":
        return {
            "primary_role":   "主職",
            "secondary_role": "副職/兼職",
        }
    elif aspect == "wealth":
        return {
            "primary_role":   "主財源",
            "secondary_role": "副財源/偏財",
        }
    elif aspect == "health":
        return {
            "primary_role":   "主病",
            "secondary_role": "次病/併發",
        }
    return {}


# ============================================================
# 過旺反凶偵測（《增刪卜易》原則）
# ============================================================
def check_overflowing(yongshen, outer_branch, all_yao_rows=None):
    """
    用神是否「過旺反凶」。

    判定條件（《增刪卜易》）：
      - 用神五行當值（臨值 / 帝旺地）
      - 且卦中有兩個以上同五行的爻生扶用神
      - 或日月作財星 + 卦中財爻多現

    回傳 dict：
      {
        "is_overflowing":  bool,
        "phase":           十二長生狀態
        "evidence_count":  支撐爻的數量
        "reason":          判定原因
      }
    """
    if not yongshen or not outer_branch:
        return {"is_overflowing": False}

    yao_ele = yongshen.get("五行") or BRANCH_ELEMENT.get(yongshen.get("地支", ""))
    if not yao_ele:
        return {"is_overflowing": False}

    phase = twelve_phase(yao_ele, outer_branch)
    tier = strength_tier(yao_ele, outer_branch)

    # 必要條件：用神當值或臨帝旺地
    if phase not in ("臨官", "帝旺") and tier != "旺":
        return {"is_overflowing": False, "phase": phase}

    # 統計卦中同五行支撐
    evidence_count = 0
    if all_yao_rows:
        for r in all_yao_rows:
            if r is yongshen:
                continue
            r_ele = r.get("五行") or BRANCH_ELEMENT.get(r.get("地支", ""))
            if r_ele == yao_ele:
                evidence_count += 1

    # 過旺判定：當值 + 卦中至少有 1 個同五行支撐
    is_over = (phase in ("臨官", "帝旺")) and (evidence_count >= 1)

    return {
        "is_overflowing":  is_over,
        "phase":           phase,
        "evidence_count":  evidence_count,
        "reason": (
            f"用神{yao_ele}在「{phase}」地，卦中另有 {evidence_count} 爻同五行支撐"
            if is_over else ""
        ),
    }


# ============================================================
# 用神動化判定
# ============================================================
# 進神/退神:動爻化出「同五行」之變爻,地支順進一位=進神、順退一位=退神。
# (子午卯酉/寅申巳亥 各自±1;四土 丑→辰→未→戌 順為進、逆為退)
_JINSHEN_PAIRS = {
    ("亥", "子"), ("寅", "卯"), ("巳", "午"), ("申", "酉"),
    ("丑", "辰"), ("辰", "未"), ("未", "戌"), ("戌", "丑"),
}
_TUISHEN_PAIRS = {
    ("子", "亥"), ("卯", "寅"), ("午", "巳"), ("酉", "申"),
    ("辰", "丑"), ("未", "辰"), ("戌", "未"), ("丑", "戌"),
}


def get_dong_direction(yongshen):
    """
    判斷用神的動化方向（完全依「本爻 vs 變爻」自算,不依賴對外參照之生剋）。

    回傳：
      "化進神"   — 變爻與本爻同五行,地支順進一位(亥→子、丑→辰…)
      "化退神"   — 變爻與本爻同五行,地支順退一位(子→亥、戌→未…)
      "化伏吟"   — 變爻與本爻同地支(伏吟,非進退)
      "化回頭生" — 變爻生本爻
      "化回頭克" — 變爻剋本爻
      "化洩"     — 本爻生變爻(洩氣)
      "靜"       — 沒有動
      ""         — 動但無上述特殊方向

    註:進/退神舊版誤用「比和→進、我生(洩氣)→退」判定,已改為地支對照表。
    """
    if not yongshen or not yongshen.get("動爻"):
        return "靜"

    dong_out = yongshen.get("動爻出去")
    if not dong_out:
        return ""

    ben_ele, ben_zhi = yongshen.get("五行"), yongshen.get("地支")
    bian_ele, bian_zhi = dong_out.get("五行"), dong_out.get("地支")
    if not (ben_ele and bian_ele):
        return ""

    rel = element_relation(ben_ele, bian_ele)  # 從「本爻」看「變爻」
    if rel == "生我":
        return "化回頭生"          # 變爻生本爻
    if rel == "剋我":
        return "化回頭克"          # 變爻剋本爻
    if rel == "我生":
        return "化洩"              # 本爻生變爻(洩氣);舊版誤判為化退神
    if rel == "比和":              # 同五行 → 依地支定進/退/伏吟
        if (ben_zhi, bian_zhi) in _JINSHEN_PAIRS:
            return "化進神"
        if (ben_zhi, bian_zhi) in _TUISHEN_PAIRS:
            return "化退神"
        if ben_zhi == bian_zhi:
            return "化伏吟"
    return ""


# ============================================================
# 兩現總綱訊號生成（給各 aspect 統一呼叫）
# ============================================================

_YAO_POSITION_NAME = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]


def yao_pos_name(yao):
    """爻序 0-5 → 「初爻/二爻/.../上爻」名稱"""
    if not yao:
        return ""
    idx = yao.get("爻序index", -1)
    if 0 <= idx <= 5:
        return _YAO_POSITION_NAME[idx]
    return ""


def yao_brief(yao):
    """產出爻的簡短描述：「初爻寅木(動,玄武)」用於總綱顯示"""
    if not yao:
        return ""
    pos = yao_pos_name(yao)
    gz = yao.get("地支", "") + (yao.get("五行", "") if yao.get("五行") else "")
    if not gz:
        gz = yao.get("地支", "") or ""
    attrs = []
    if yao.get("動爻"):
        attrs.append("動")
    if yao.get("世"):
        attrs.append("世")
    if yao.get("應"):
        attrs.append("應")
    ls = yao.get("六神", "")
    if ls:
        # 騰蛇/螣蛇統一
        if ls in ("螣蛇", "騰蛇"):
            ls = "騰蛇"
        attrs.append(ls)
    attr_str = ",".join(attrs)
    return f"{pos}{gz}({attr_str})" if attr_str else f"{pos}{gz}"


def make_summary_signal(yongshen_name, yongshens, primary, secondary, role_info,
                         scope_name=""):
    """
    產出「主用神判定」總綱訊號，給流年層使用。

    參數：
      yongshen_name: "官鬼" / "妻財" / "父母" 等
      yongshens:     卦中所有同六親爻 list
      primary:       機兆主用神
      secondary:     次用神
      role_info:     select_primary 回傳的 role_info dict
      scope_name:    "今年" / "正月" 等時間範圍前綴

    回傳：訊號 dict（level=中，作為描述性總綱）
          沒兩現時回傳 None
    """
    if not yongshens or len(yongshens) < 2:
        return None
    if primary is None:
        return None

    yao_briefs = "、".join(yao_brief(y) for y in yongshens)
    lines = [f"{scope_name}{yongshen_name}兩現:{yao_briefs}。"]

    reason = role_info.get("reason", "")
    primary_role = role_info.get("primary_role", "主用神")

    # 機兆主用神描述
    if reason:
        lines.append(f"取「{yao_brief(primary)}」為機兆主用神({reason}),此爻為事發關鍵。")
    else:
        lines.append(f"取「{yao_brief(primary)}」為機兆主用神。")

    # 感情面的正配/偏配額外資訊
    zheng = role_info.get("love_zheng_yao")
    pian = role_info.get("love_pian_yao")
    zheng_reason = role_info.get("love_zheng_reason", "")
    if zheng is not None:
        if zheng is primary:
            lines.append(f"「{yao_brief(zheng)}」同為「角色正配」({zheng_reason}) — 機兆與正配為同一爻。")
        else:
            lines.append(f"另取「{yao_brief(zheng)}」為「角色正配」({zheng_reason}),代表正夫/正妻整體狀況。")
        if pian is not None and pian is not primary:
            lines.append(f"「{yao_brief(pian)}」為「偏配/情人/競爭對手」位置。")

    text = " ".join(lines)
    return {
        "level": "中",
        "text": text,
        "_yao_key": None,   # 全卦總綱不歸特定爻
    }


def role_tag(yao, primary, secondary, role_info):
    """
    取得單爻在「兩現分工」中的角色標籤,用於訊號文字後綴。

    回傳:
      "[主用神]" / "[次用神]" / "[正配]" / "[偏配]" / ""
    """
    if not yao or primary is None:
        return ""

    # 感情面特殊:有正配/偏配時優先標角色
    zheng = role_info.get("love_zheng_yao")
    pian = role_info.get("love_pian_yao")
    if zheng is not None:
        if yao is zheng:
            return "[正配]"
        if yao is pian:
            return "[偏配]"

    # 通用:機兆主用神 / 次用神
    if yao is primary:
        return "[主用神]"
    if secondary is not None and yao is secondary:
        return "[次用神]"
    return ""
