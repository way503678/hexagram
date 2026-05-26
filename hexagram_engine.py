# -*- coding: utf-8 -*-
"""
命卦排盤引擎（梅花易數）

起卦規則：
  1. 取公曆日期，換算為農曆月、日
  2. 上卦數 = 農曆日 % 8（0 視為 8）→ 對應八卦
  3. 下卦數 = 農曆月 % 8（0 視為 8）→ 對應八卦
  4. 時辰序號 = 子1 丑2 ... 亥12
  5. 動爻 index = (時辰序號 - 1) % 6，0=初爻（最下），5=上爻（最上）
  6. 本卦 = 上下卦合起來；變卦 = 動爻翻轉後的卦

爻序方向統一為「由下而上」：index 0 = 初爻，index 5 = 上爻

四柱：
  年、月：用 sxtwl 依節氣制（立春分年、節氣分月）
  日：沿用 core_data.day_ganzhi（00:00 換日）
  時：沿用 core_data.hour_ganzhi（五鼠遁）

神煞（以世爻五行為基準）：
  元神 = 生世爻者
  忌神 = 剋世爻者
  仇神 = 世爻所剋者（生忌神、剋元神）
  世爻本身：空字串（由世應欄顯示）
"""

from datetime import datetime
import sxtwl

from core_data import (
    TRIGRAM_LINES, LINES_TO_TRIGRAM, TRIGRAM_NUMBERS,
    HEAVENLY_STEMS, EARTHLY_BRANCHES,
    BRANCH_ELEMENT, TRIGRAM_ELEMENT, relation,
    day_ganzhi, hour_ganzhi, hour_to_shichen, hour_to_branch, line_symbol,
    six_spirits_by_stem,
)
from hexagram_data import HEXAGRAMS, gua_type


SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE   = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
SHENG_ME = {v: k for k, v in SHENG.items()}
KE_ME    = {v: k for k, v in KE.items()}


def _shen_sha(element, shi_element):
    if element == shi_element:
        return ""
    if SHENG_ME[shi_element] == element:
        return "元神"
    if KE_ME[shi_element] == element:
        return "忌神"
    if KE[shi_element] == element:
        return "仇神"
    return ""


def _get_trigram_by_number(n):
    n = n % 8 or 8
    return TRIGRAM_NUMBERS[n]


def _four_pillars(dt: datetime):
    sd = sxtwl.fromSolar(dt.year, dt.month, dt.day)
    y = sd.getYearGZ()
    m = sd.getMonthGZ()
    year_gz  = HEAVENLY_STEMS[y.tg] + EARTHLY_BRANCHES[y.dz]
    month_gz = HEAVENLY_STEMS[m.tg] + EARTHLY_BRANCHES[m.dz]
    day_gz   = day_ganzhi(dt)
    hour_gz  = hour_ganzhi(day_gz[0], dt.hour)
    return {
        "年": year_gz,
        "月": month_gz,
        "日": day_gz,
        "時": hour_gz,
        "農曆年": sd.getLunarYear(),
        "農曆月": sd.getLunarMonth(),
        "農曆日": sd.getLunarDay(),
    }


def _gua_change_summary(orig_name, new_name):
    """
    判斷本卦 → 變卦的格局變化(只在涉及六沖卦/六合卦時才有意義)。
    回傳 dict 或 None:
      {
        "本卦類型": "六沖卦" / "六合卦" / "",
        "變卦類型": "六沖卦" / "六合卦" / "",
        "等級": "凶" / "吉" / "中",
        "標題": "本沖變合" / "本合變沖" / "本沖變沖" / "本合變合" / "本沖" / "本合" / "變沖" / "變合",
        "說明": "...",
      }
    若本卦變卦都不是六沖六合卦,回傳 None(不顯示)。
    """
    orig_type = gua_type(orig_name)
    new_type = gua_type(new_name)
    if not orig_type and not new_type:
        return None

    # 兩卦都有類型
    if orig_type == "六沖卦" and new_type == "六合卦":
        return {
            "本卦類型": orig_type, "變卦類型": new_type,
            "等級": "吉", "標題": "本沖變合",
            "說明": "本卦六沖、變卦六合 — 大事化小、由動轉靜、由凶轉吉,事情有轉機。",
        }
    if orig_type == "六合卦" and new_type == "六沖卦":
        return {
            "本卦類型": orig_type, "變卦類型": new_type,
            "等級": "凶", "標題": "本合變沖",
            "說明": "本卦六合、變卦六沖 — 由靜轉動、由吉轉凶,原本安穩的事將生變。",
        }
    if orig_type == "六沖卦" and new_type == "六沖卦":
        return {
            "本卦類型": orig_type, "變卦類型": new_type,
            "等級": "凶", "標題": "本沖變沖",
            "說明": "本卦六沖、變卦也六沖 — 動盪到底,事情難安、變化大。",
        }
    if orig_type == "六合卦" and new_type == "六合卦":
        return {
            "本卦類型": orig_type, "變卦類型": new_type,
            "等級": "吉", "標題": "本合變合",
            "說明": "本卦六合、變卦也六合 — 安穩到底,事情平順發展。",
        }
    # 只有一邊
    if orig_type == "六沖卦":
        return {
            "本卦類型": orig_type, "變卦類型": new_type,
            "等級": "凶", "標題": "本卦六沖",
            "說明": "本卦為六沖卦 — 事情動盪、難以安定,主散主動。",
        }
    if orig_type == "六合卦":
        return {
            "本卦類型": orig_type, "變卦類型": new_type,
            "等級": "吉", "標題": "本卦六合",
            "說明": "本卦為六合卦 — 事情和合、安穩,主成主合。",
        }
    if new_type == "六沖卦":
        return {
            "本卦類型": orig_type, "變卦類型": new_type,
            "等級": "凶", "標題": "變卦六沖",
            "說明": "變卦為六沖卦 — 事情後續將生變動、由穩轉散。",
        }
    if new_type == "六合卦":
        return {
            "本卦類型": orig_type, "變卦類型": new_type,
            "等級": "吉", "標題": "變卦六合",
            "說明": "變卦為六合卦 — 事情後續將趨於和合、由動轉靜。",
        }
    return None


def cast_hexagram(dt: datetime):
    sz = _four_pillars(dt)
    lunar_m = sz["農曆月"]
    lunar_d = sz["農曆日"]
    day_gz = sz["日"]
    day_stem = day_gz[0]

    shichen_idx = hour_to_shichen(dt.hour)
    shichen_branch = hour_to_branch(dt.hour)

    upper_name = _get_trigram_by_number(lunar_d)
    lower_name = _get_trigram_by_number(lunar_m)

    changing_line_idx = (shichen_idx - 1) % 6

    lines = TRIGRAM_LINES[lower_name] + TRIGRAM_LINES[upper_name]

    changed_lines = lines[:]
    changed_lines[changing_line_idx] = 1 - changed_lines[changing_line_idx]
    new_lower_name = LINES_TO_TRIGRAM[tuple(changed_lines[0:3])]
    new_upper_name = LINES_TO_TRIGRAM[tuple(changed_lines[3:6])]

    orig_info = HEXAGRAMS[(upper_name, lower_name)]
    new_info = HEXAGRAMS[(new_upper_name, new_lower_name)]

    spirits = six_spirits_by_stem(day_stem)

    orig_shi_idx = orig_info["世爻"]
    orig_shi_branch = orig_info["納甲"][orig_shi_idx]
    orig_shi_element = BRANCH_ELEMENT[orig_shi_branch]

    orig_gong_element = orig_info["卦宮五行"]
    orig_rows = []
    for i in range(6):
        branch = orig_info["納甲"][i]
        stem = orig_info["納甲天干"][i]
        ele = BRANCH_ELEMENT[branch]
        liuqin = relation(orig_gong_element, ele)
        shen = "" if i == orig_shi_idx else _shen_sha(ele, orig_shi_element)
        row = {
            "爻序index": i,
            "爻序名": ["初爻","二爻","三爻","四爻","五爻","上爻"][i],
            "陰陽": "陽" if lines[i] == 1 else "陰",
            "爻象": line_symbol(lines[i], is_moving=(i == changing_line_idx)),
            "天干": stem,
            "地支": branch,
            "干支": stem + branch,
            "五行": ele,
            "六親": liuqin,
            "六神": spirits[i],
            "神煞": shen,
            "伏神": [],    # 等第 8b 步計算後填入
            "世": (i == orig_info["世爻"]),
            "應": (i == orig_info["應爻"]),
            "動爻": (i == changing_line_idx),
        }
        if i == changing_line_idx:
            out_branch = new_info["納甲"][i]
            out_stem = new_info["納甲天干"][i]
            out_ele = BRANCH_ELEMENT[out_branch]
            row["動爻出去天干"] = out_stem
            row["動爻出去地支"] = out_branch
            row["動爻出去干支"] = out_stem + out_branch
            row["動爻出去五行"] = out_ele
            row["動爻出去六親"] = relation(orig_gong_element, out_ele)
        orig_rows.append(row)

    # === 8b. 計算伏神（野鶴派）===
    # 規則：
    #   1. 只看本卦原始六親（動爻不影響）
    #   2. 本卦六親齊全（兄弟/子孫/父母/妻財/官鬼 五種都有）→ 無伏神
    #   3. 缺的六親，回本宮首卦找同六親所在爻位，伏在本卦同爻位下
    #   4. 首卦中同一六親出現兩次 → 兩處都標
    FIVE_LIUQIN = {"兄弟", "子孫", "父母", "妻財", "官鬼"}
    present = {row["六親"] for row in orig_rows}
    missing = FIVE_LIUQIN - present
    if missing:
        # 本宮首卦（純卦）
        palace = orig_info["卦宮"]
        palace_info = HEXAGRAMS[(palace, palace)]
        palace_me = palace_info["卦宮五行"]
        # 首卦每爻的六親
        palace_liuqin = [
            relation(palace_me, BRANCH_ELEMENT[br])
            for br in palace_info["納甲"]
        ]
        # 對每個缺的六親，找出它在首卦出現的所有爻位
        for lq in missing:
            for pos, plq in enumerate(palace_liuqin):
                if plq == lq:
                    branch = palace_info["納甲"][pos]
                    stem = palace_info["納甲天干"][pos]
                    orig_rows[pos]["伏神"].append({
                        "六親": lq,
                        "天干": stem,
                        "地支": branch,
                        "干支": stem + branch,
                    })

    new_gong_element = new_info["卦宮五行"]
    new_shi_idx = new_info["世爻"]
    new_shi_branch = new_info["納甲"][new_shi_idx]
    new_shi_element = BRANCH_ELEMENT[new_shi_branch]

    new_rows = []
    for i in range(6):
        branch = new_info["納甲"][i]
        stem = new_info["納甲天干"][i]
        ele = BRANCH_ELEMENT[branch]
        liuqin = relation(new_gong_element, ele)
        shen = "" if i == new_shi_idx else _shen_sha(ele, new_shi_element)
        row = {
            "爻序index": i,
            "爻序名": ["初爻","二爻","三爻","四爻","五爻","上爻"][i],
            "陰陽": "陽" if changed_lines[i] == 1 else "陰",
            "爻象": line_symbol(changed_lines[i]),
            "天干": stem,
            "地支": branch,
            "干支": stem + branch,
            "五行": ele,
            "六親": liuqin,
            "六神": spirits[i],
            "神煞": shen,
            "世": (i == new_info["世爻"]),
            "應": (i == new_info["應爻"]),
            "動爻": False,
        }
        new_rows.append(row)

    return {
        "公曆": dt.strftime("%Y-%m-%d %H:%M"),
        "農曆": f"{sz['農曆年']}年{lunar_m}月{lunar_d}日",
        "四柱": {
            "年": sz["年"],
            "月": sz["月"],
            "日": sz["日"],
            "時": sz["時"],
        },
        "日干支": day_gz,
        "時辰": f"{shichen_branch}時",
        "本卦": {
            "卦名": orig_info["卦名"],
            "卦辭": orig_info["卦辭"],
            "卦宮": orig_info["卦宮"],
            "卦宮五行": orig_info["卦宮五行"],
            "卦變": orig_info["卦變"],
            "上卦": upper_name,
            "下卦": lower_name,
            "世爻五行": orig_shi_element,
            "爻": orig_rows,
        },
        "變卦": {
            "卦名": new_info["卦名"],
            "卦辭": new_info["卦辭"],
            "卦宮": new_info["卦宮"],
            "卦宮五行": new_info["卦宮五行"],
            "卦變": new_info["卦變"],
            "上卦": new_upper_name,
            "下卦": new_lower_name,
            "世爻五行": new_shi_element,
            "爻": new_rows,
        },
        "動爻": {
            "index": changing_line_idx,
            "爻序名": ["初爻","二爻","三爻","四爻","五爻","上爻"][changing_line_idx],
            "描述": f"第{changing_line_idx+1}爻（{['初','二','三','四','五','上'][changing_line_idx]}爻）動",
        },
        "卦變總論": _gua_change_summary(orig_info["卦名"], new_info["卦名"]),
    }


def cast_hexagram_manual(lines, moving, dt: datetime = None):
    """
    手動指定六爻排盤（金錢卦／搖卦結果）

    參數：
      lines:  長度 6 的 list，由下而上 [初, 二, 三, 四, 五, 上]
              每爻：1=陽，0=陰
      moving: 長度 6 的 list，由下而上
              每爻：1=動爻，0=不動爻
      dt:     datetime 物件，用於計算四柱、日干支以決定六神；可選
              若為 None，則四柱、日干支留空、六神也留空

    回傳格式：與 cast_hexagram() 完全相同（包含「世爻五行」、「神煞」、
    「伏神」、京房納甲完整干支），只是「動爻」改為 indices 陣列。
    """
    if len(lines) != 6 or len(moving) != 6:
        raise ValueError("lines 與 moving 必須是長度 6 的陣列")
    for v in lines:
        if v not in (0, 1):
            raise ValueError("lines 元素只能是 0 或 1")
    for v in moving:
        if v not in (0, 1):
            raise ValueError("moving 元素只能是 0 或 1")

    # === 1. 由六爻反查上下卦 ===
    lower_name = LINES_TO_TRIGRAM[tuple(lines[0:3])]
    upper_name = LINES_TO_TRIGRAM[tuple(lines[3:6])]
    orig_info = HEXAGRAMS[(upper_name, lower_name)]

    # === 2. 變卦 = 動爻翻轉 ===
    changed_lines = [(1 - lines[i]) if moving[i] else lines[i] for i in range(6)]
    new_lower_name = LINES_TO_TRIGRAM[tuple(changed_lines[0:3])]
    new_upper_name = LINES_TO_TRIGRAM[tuple(changed_lines[3:6])]
    new_info = HEXAGRAMS[(new_upper_name, new_lower_name)]

    # === 3. 日期、四柱、六神 ===
    if dt is not None:
        sz = _four_pillars(dt)
        day_gz = sz["日"]
        day_stem = day_gz[0]
        shichen_branch = hour_to_branch(dt.hour)
        spirits = six_spirits_by_stem(day_stem)
        date_meta = {
            "公曆": dt.strftime("%Y-%m-%d %H:%M"),
            "農曆": f"{sz['農曆年']}年{sz['農曆月']}月{sz['農曆日']}日",
            "四柱": {
                "年": sz["年"],
                "月": sz["月"],
                "日": sz["日"],
                "時": sz["時"],
            },
            "日干支": day_gz,
            "時辰": f"{shichen_branch}時",
        }
    else:
        spirits = ["", "", "", "", "", ""]
        date_meta = {
            "公曆": "",
            "農曆": "",
            "四柱": {"年": "", "月": "", "日": "", "時": ""},
            "日干支": "",
            "時辰": "",
        }

    # === 4. 本卦世爻五行（為神煞計算基準）===
    orig_shi_idx = orig_info["世爻"]
    orig_shi_branch = orig_info["納甲"][orig_shi_idx]
    orig_shi_element = BRANCH_ELEMENT[orig_shi_branch]

    # === 5. 組裝本卦各爻 ===
    orig_gong_element = orig_info["卦宮五行"]
    orig_rows = []
    moving_indices = []
    for i in range(6):
        branch = orig_info["納甲"][i]
        stem = orig_info["納甲天干"][i]
        ele = BRANCH_ELEMENT[branch]
        liuqin = relation(orig_gong_element, ele)
        is_moving = bool(moving[i])
        shen = "" if i == orig_shi_idx else _shen_sha(ele, orig_shi_element)
        row = {
            "爻序index": i,
            "爻序名": ["初爻","二爻","三爻","四爻","五爻","上爻"][i],
            "陰陽": "陽" if lines[i] == 1 else "陰",
            "爻象": line_symbol(lines[i], is_moving=is_moving),
            "天干": stem,
            "地支": branch,
            "干支": stem + branch,
            "五行": ele,
            "六親": liuqin,
            "六神": spirits[i],
            "神煞": shen,
            "伏神": [],
            "世": (i == orig_info["世爻"]),
            "應": (i == orig_info["應爻"]),
            "動爻": is_moving,
        }
        if is_moving:
            moving_indices.append(i)
            out_branch = new_info["納甲"][i]
            out_stem = new_info["納甲天干"][i]
            out_ele = BRANCH_ELEMENT[out_branch]
            row["動爻出去天干"] = out_stem
            row["動爻出去地支"] = out_branch
            row["動爻出去干支"] = out_stem + out_branch
            row["動爻出去五行"] = out_ele
            row["動爻出去六親"] = relation(orig_gong_element, out_ele)
        orig_rows.append(row)

    # === 6. 計算伏神（野鶴派）===
    FIVE_LIUQIN = {"兄弟", "子孫", "父母", "妻財", "官鬼"}
    present = {row["六親"] for row in orig_rows}
    missing = FIVE_LIUQIN - present
    if missing:
        palace = orig_info["卦宮"]
        palace_info = HEXAGRAMS[(palace, palace)]
        palace_me = palace_info["卦宮五行"]
        palace_liuqin = [
            relation(palace_me, BRANCH_ELEMENT[br])
            for br in palace_info["納甲"]
        ]
        for lq in missing:
            for pos, plq in enumerate(palace_liuqin):
                if plq == lq:
                    branch = palace_info["納甲"][pos]
                    stem = palace_info["納甲天干"][pos]
                    orig_rows[pos]["伏神"].append({
                        "六親": lq,
                        "天干": stem,
                        "地支": branch,
                        "干支": stem + branch,
                    })

    # === 7. 組裝變卦各爻 ===
    new_gong_element = new_info["卦宮五行"]
    new_shi_idx = new_info["世爻"]
    new_shi_branch = new_info["納甲"][new_shi_idx]
    new_shi_element = BRANCH_ELEMENT[new_shi_branch]

    new_rows = []
    for i in range(6):
        branch = new_info["納甲"][i]
        stem = new_info["納甲天干"][i]
        ele = BRANCH_ELEMENT[branch]
        liuqin = relation(new_gong_element, ele)
        shen = "" if i == new_shi_idx else _shen_sha(ele, new_shi_element)
        row = {
            "爻序index": i,
            "爻序名": ["初爻","二爻","三爻","四爻","五爻","上爻"][i],
            "陰陽": "陽" if changed_lines[i] == 1 else "陰",
            "爻象": line_symbol(changed_lines[i]),
            "天干": stem,
            "地支": branch,
            "干支": stem + branch,
            "五行": ele,
            "六親": liuqin,
            "六神": spirits[i],
            "神煞": shen,
            "世": (i == new_info["世爻"]),
            "應": (i == new_info["應爻"]),
            "動爻": False,
        }
        new_rows.append(row)

    # === 8. 動爻描述 ===
    if moving_indices:
        names = [["初","二","三","四","五","上"][i] for i in moving_indices]
        desc = "、".join(f"{n}爻" for n in names) + "動"
    else:
        desc = "無動爻（靜卦）"

    return {
        **date_meta,
        "本卦": {
            "卦名": orig_info["卦名"],
            "卦辭": orig_info["卦辭"],
            "卦宮": orig_info["卦宮"],
            "卦宮五行": orig_info["卦宮五行"],
            "卦變": orig_info["卦變"],
            "上卦": upper_name,
            "下卦": lower_name,
            "世爻五行": orig_shi_element,
            "爻": orig_rows,
        },
        "變卦": {
            "卦名": new_info["卦名"],
            "卦辭": new_info["卦辭"],
            "卦宮": new_info["卦宮"],
            "卦宮五行": new_info["卦宮五行"],
            "卦變": new_info["卦變"],
            "上卦": new_upper_name,
            "下卦": new_lower_name,
            "世爻五行": new_shi_element,
            "爻": new_rows,
        },
        "動爻": {
            "indices": moving_indices,
            "描述": desc,
        },
        "卦變總論": _gua_change_summary(orig_info["卦名"], new_info["卦名"]),
        "起卦法": "手動輸入",
    }


# ============================================================
# 手動排卦的四面向分析
# ============================================================
def analyze_chart_aspects(chart, dt, gender=None, aspect_choice="all"):
    """
    對手動排卦或時辰起卦的結果做四面向判讀。

    手動排卦沒有「流年」概念，但有使用者選擇的時間 dt。
    用 dt 算出來的四柱日辰地支當作「當值地支」。

    參數：
      chart:        cast_hexagram 或 cast_hexagram_manual 的回傳結果
      dt:           使用者選擇的 datetime（用來決定當值地支）
      gender:       'M' / 'F' / None
      aspect_choice: "love" / "health" / "work" / "wealth" / "all"

    回傳 dict：
      {
        "當值地支": "卯",
        "對六爻":   [...],
        "引動伏神": [...],
        "主導爻":   [...],
        "四面向":   {
          "感情": [...] (僅當 aspect_choice 包含),
          "健康": [...],
          ...
        }
      }
    """
    # 延遲 import 避免循環依賴
    from divination.core.trigger import (
        analyze_yao_actions, find_aroused_fushen, dominant_yaos,
    )
    from divination.aspects import love, health, work, wealth

    yao_rows = chart["本卦"]["爻"]

    # 用使用者選擇的日干支地支作為當值地支
    # 四柱日：例「丙申」→ 取「申」
    day_gz = chart["四柱"]["日"]
    if not day_gz or len(day_gz) < 2:
        # 沒日干支則退化 — 但 cast_hexagram 永遠會給日干支
        raise ValueError("手動排卦四面向分析需要有效的日干支")
    day_branch = day_gz[1]

    # 對六爻分析
    yao_actions = analyze_yao_actions(yao_rows, day_branch)
    aroused = find_aroused_fushen(yao_rows, day_branch)
    dom = dominant_yaos(yao_actions)

    # 構造 outer_block（手動排卦也要的「對世爻」資訊）
    from divination.core.elements import element_relation
    shi_yao = next((r for r in yao_rows if r["世"]), None)
    shi_branch = shi_yao["地支"] if shi_yao else ""
    shi_element = shi_yao["五行"] if shi_yao else ""
    day_element = BRANCH_ELEMENT.get(day_branch, "")

    outer_block = {
        "地支":       day_branch,
        "五行":       day_element,
        "對世爻":     element_relation(shi_element, day_element) if shi_element else "",
        "對世爻合沖": relation_branch(shi_branch, day_branch) if shi_branch else "",
        "對六爻":     yao_actions,
        "引動伏神":   aroused,
    }

    # 手動排卦也帶 is_year_scope=True 來呈現所有靜態徵兆
    # （手卦的本質就是「占當下一事」，沒有流月細分）
    aspect_modules = {
        "love":   love,
        "health": health,
        "work":   work,
        "wealth": wealth,
    }
    aspect_names = {
        "love":   "感情",
        "health": "健康",
        "work":   "工作",
        "wealth": "財運",
    }

    aspects_result = {}
    if aspect_choice == "all":
        targets = ["love", "health", "work", "wealth"]
    elif aspect_choice in aspect_modules:
        targets = [aspect_choice]
    else:
        targets = []

    for key in targets:
        mod = aspect_modules[key]
        name = aspect_names[key]
        aspects_result[name] = mod.analyze(
            yao_actions, outer_block, aroused, "本卦",
            gender=gender, is_year_scope=True,
        )

    return {
        "當值地支":   day_branch,
        "當值五行":   day_element,
        "對世爻":     outer_block["對世爻"],
        "對世爻合沖": outer_block["對世爻合沖"],
        "對六爻":     yao_actions,
        "引動伏神":   aroused,
        "主導爻":     dom,
        "四面向":     aspects_result,
    }


def relation_branch(a, b):
    """臨時包裝，避免循環 import — 內部呼叫 fortune_data.branch_relation"""
    from fortune_data import branch_relation
    return branch_relation(a, b)


if __name__ == "__main__":
    dt = datetime(1990, 8, 11, 10, 0)
    r = cast_hexagram(dt)
    sz = r["四柱"]
    print(f"公曆：{r['公曆']}  農曆：{r['農曆']}")
    print(f"四柱：{sz['年']}年 {sz['月']}月 {sz['日']}日 {sz['時']}時")
    print(f"動爻：{r['動爻']['描述']}")
    print(f"本卦：{r['本卦']['卦名']}（{r['本卦']['卦宮']}宮-{r['本卦']['卦變']}，世爻五行 {r['本卦']['世爻五行']}）")
    print(f"變卦：{r['變卦']['卦名']}")
    print()
    for row in reversed(r['本卦']['爻']):
        sy = "世" if row["世"] else ("應" if row["應"] else "")
        dong = ""
        if row.get("動爻"):
            dong = f"  ○→{row['動爻出去干支']}({row['動爻出去六親']})"
        print(f"{row['爻序名']} {row['六神']} {row['爻象']} {row['干支']} {sy} {row['六親']} {row['神煞']}{dong}")
