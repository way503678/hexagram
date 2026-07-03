# -*- coding: utf-8 -*-
"""
divination.core.elements — 五行運算與十二長生

純粹的五行計算邏輯，不關心是流年還是手動排卦。

核心功能：
  - element_relation(yao_ele, outer_ele):  五行生剋（從爻看外來者）
  - twelve_phase(yao_ele, branch):         十二長生狀態
  - strength_tier(yao_ele, branch):        三級強弱
  - is_full_sanhe(month_branch, all_yao_branches): 嚴格三合判定
  - attendance_status(...):                當值狀態 6 種
"""
from core_data import BRANCH_ELEMENT
from fortune_data import branch_relation


# ============================================================
# 五行生剋
# ============================================================
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE   = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def element_relation(yao_element, outer_element):
    """
    從『爻的角度』看『外來者（流年/流月/日辰）』的生剋關係。

    例如 yao_element=金, outer_element=火 → 火剋金 → 對爻而言是「剋我」

    回傳："比和" / "生我" / "我生" / "剋我" / "我剋" / ""
    """
    if not yao_element or not outer_element:
        return ""
    if yao_element == outer_element:
        return "比和"
    if SHENG.get(outer_element) == yao_element:
        return "生我"
    if SHENG.get(yao_element) == outer_element:
        return "我生"
    if KE.get(outer_element) == yao_element:
        return "剋我"
    if KE.get(yao_element) == outer_element:
        return "我剋"
    return ""


# ============================================================
# 十二長生表
# key: 五行（從爻看自己的五行），value: 該五行在 12 地支的狀態
# ============================================================
_TWELVE_PHASES = {
    # 金（申）─ 長生在巳、帝旺在酉、墓在丑、絕在寅
    "金": {"巳":"長生","午":"沐浴","未":"冠帶","申":"臨官","酉":"帝旺","戌":"衰",
           "亥":"病","子":"死","丑":"墓","寅":"絕","卯":"胎","辰":"養"},
    # 木（寅）─ 長生在亥、帝旺在卯、墓在未、絕在申
    "木": {"亥":"長生","子":"沐浴","丑":"冠帶","寅":"臨官","卯":"帝旺","辰":"衰",
           "巳":"病","午":"死","未":"墓","申":"絕","酉":"胎","戌":"養"},
    # 水（子）─ 長生在申、帝旺在子、墓在辰、絕在巳
    "水": {"申":"長生","酉":"沐浴","戌":"冠帶","亥":"臨官","子":"帝旺","丑":"衰",
           "寅":"病","卯":"死","辰":"墓","巳":"絕","午":"胎","未":"養"},
    # 火（午）─ 長生在寅、帝旺在午、墓在戌、絕在亥
    "火": {"寅":"長生","卯":"沐浴","辰":"冠帶","巳":"臨官","午":"帝旺","未":"衰",
           "申":"病","酉":"死","戌":"墓","亥":"絕","子":"胎","丑":"養"},
    # 土 ─ 寄火，長生在寅、帝旺在午、墓在戌、絕在亥（同火）
    "土": {"寅":"長生","卯":"沐浴","辰":"冠帶","巳":"臨官","午":"帝旺","未":"衰",
           "申":"病","酉":"死","戌":"墓","亥":"絕","子":"胎","丑":"養"},
}


# 三級強弱分類
_STRENGTH_TIER = {
    "長生": "旺", "臨官": "旺", "帝旺": "旺",
    "沐浴": "中", "冠帶": "中", "衰": "中", "養": "中",
    "病": "弱", "死": "弱", "墓": "弱", "絕": "弱", "胎": "弱",
}


def twelve_phase(yao_element, outer_branch):
    """
    回傳爻的五行在指定地支（流年或流月）的十二長生狀態。

    例如：水在午地 → '胎'（火當令水勢極弱）
    """
    table = _TWELVE_PHASES.get(yao_element)
    if not table:
        return ""
    return table.get(outer_branch, "")


def strength_tier(yao_element, outer_branch):
    """
    回傳爻的五行在指定地支的強弱三級(依十二長生)。
    回傳 "旺" / "中" / "弱" / ""
    ⚠️ 依增刪卜易派:十二長生只用於「日辰、動變爻」;**月令旺衰請改用 seasonal_tier**
    (四時旺相休囚死)。經典矛盾例:金在巳月,長生訣=長生(旺)、四時=死(巳火剋金),
    以四時為準。
    """
    phase = twelve_phase(yao_element, outer_branch)
    return _STRENGTH_TIER.get(phase, "")


# ============================================================
# 四時旺相休囚死(月令旺衰專用)
# 以月令地支五行為「我」:臨我者旺、我生者相、生我者休、剋我者囚、我剋者死。
# 無「月墓、月絕」之說 — 長生/墓/絕只存在於日辰與動變爻(十二長生)。
# ============================================================
_SEASONAL_TIER = {"旺": "旺", "相": "旺", "休": "中", "囚": "弱", "死": "弱"}


def seasonal_state(yao_element, month_branch):
    """
    回傳爻五行在月令的四時狀態:"旺"/"相"/"休"/"囚"/"死"/""。
    例:金在巳月(巳=火,火剋金=我剋者)→ 死;木在亥月(亥=水,水生木=我生者)→ 相。
    """
    month_ele = BRANCH_ELEMENT.get(month_branch)
    if not yao_element or not month_ele:
        return ""
    if yao_element == month_ele:
        return "旺"          # 臨我者旺(當令)
    if SHENG.get(month_ele) == yao_element:
        return "相"          # 我(月令)生者相
    if SHENG.get(yao_element) == month_ele:
        return "休"          # 生我(月令)者休
    if KE.get(yao_element) == month_ele:
        return "囚"          # 剋我(月令)者囚
    if KE.get(month_ele) == yao_element:
        return "死"          # 我(月令)剋者死
    return ""


def seasonal_tier(yao_element, month_branch):
    """月令旺衰三級(四時旺相休囚死 → 旺/中/弱)。旺相=旺、休=中、囚死=弱。"""
    return _SEASONAL_TIER.get(seasonal_state(yao_element, month_branch), "")


# ============================================================
# 三合判定
# ============================================================
# 三合各組的「帝旺地」（成局的關鍵）
_SANHE_HUAI = {
    "申子辰": "子",   # 水局帝旺在子
    "寅午戌": "午",   # 火局帝旺在午
    "巳酉丑": "酉",   # 金局帝旺在酉
    "亥卯未": "卯",   # 木局帝旺在卯
}


def get_sanhe_group(branch):
    """回傳 branch 所屬三合圈的三字組合 key，不在任何組則回 None"""
    for key in _SANHE_HUAI.keys():
        if branch in key:
            return key
    return None


def is_full_sanhe(month_branch, all_yao_branches):
    """
    嚴格三合判定：
      1. 月支必須是三合圈的「帝旺地」（子/午/酉/卯）
      2. 卦中六爻地支必須同時涵蓋同組另外兩個地支
    回傳 True 才算三合成局。
    """
    group_key = get_sanhe_group(month_branch)
    if not group_key or _SANHE_HUAI.get(group_key) != month_branch:
        return False
    group_branches = set(group_key)
    other_two = group_branches - {month_branch}
    return other_two.issubset(set(all_yao_branches))


# ============================================================
# 當值狀態判定
# ============================================================
def attendance_status(yao_branch, outer_branch, all_yao_branches=None):
    """
    回傳該爻對外來地支（流年/流月/手卦的當值地支）的當令狀態。

    回傳："臨值" / "三合" / "月生" / "月沖" / "月剋" / "平"

    參數：
      yao_branch:        該爻地支
      outer_branch:      外來地支（流年/流月/當值）
      all_yao_branches:  卦中六爻的全部地支 list（三合判定要用）。
                         為 None 時退化為「不判三合」。
    """
    if yao_branch == outer_branch:
        return "臨值"

    # 三合：嚴格版 — 月支為帝旺地且卦中三爻同時齊全
    if all_yao_branches is not None:
        if is_full_sanhe(outer_branch, all_yao_branches):
            group_key = get_sanhe_group(outer_branch)
            if group_key and yao_branch in group_key and yao_branch != outer_branch:
                return "三合"

    yao_ele = BRANCH_ELEMENT.get(yao_branch)
    outer_ele = BRANCH_ELEMENT.get(outer_branch)
    if yao_ele and outer_ele:
        if SHENG.get(outer_ele) == yao_ele:
            return "月生"
        if KE.get(outer_ele) == yao_ele:
            if branch_relation(yao_branch, outer_branch) == "相沖":
                return "月沖"
            return "月剋"
    return "平"
