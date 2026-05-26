# -*- coding: utf-8 -*-
"""
流年排盤引擎（瘦身版）

只負責流年時間軸的協調：
  1. 跑原命盤（呼叫 hexagram_engine.cast_hexagram）
  2. 計算流年地支 + 流月地支
  3. 對六爻分析（呼叫 divination.core.trigger）
  4. 引動伏神（呼叫 divination.core.trigger）
  5. 產生白話斷語（內建）
  6. 產生四面向斷語（呼叫 divination.aspects.*）

對外介面與原版完全一致：
  analyze_fortune(chart_dt, target_year, gender=None) -> dict

回傳結構與原版完全一致，templates 不用改。
"""
import sxtwl

from core_data import HEAVENLY_STEMS, EARTHLY_BRANCHES, BRANCH_ELEMENT
from hexagram_engine import cast_hexagram
from fortune_data import (
    branch_relation, JIEQI_NAMES, MONTH_JIEQI,
    JIEQI_TO_MONTH_BRANCH, MONTH_BRANCH_ORDER, MONTH_BRANCH_NAMES,
)

# 共用核心層
from divination.core.elements import element_relation
from divination.core.trigger import (
    analyze_yao_actions, find_aroused_fushen, dominant_yaos,
)

# 面向特化層
from divination.aspects import love, health, work, wealth


# ============================================================
# 流年立春與流月節氣
# ============================================================
def _find_lichun(year):
    """找該西元年的立春日 sxtwl Day 物件"""
    d = sxtwl.fromSolar(year, 2, 1)
    for _ in range(15):
        if d.hasJieQi() and d.getJieQi() == 3:  # 3 = 立春
            return d
        d = d.after(1)
    raise ValueError(f"找不到 {year} 年的立春")


def _gz_string(gz_obj):
    """sxtwl GZ 物件轉成『甲子』字串"""
    return HEAVENLY_STEMS[gz_obj.tg] + EARTHLY_BRANCHES[gz_obj.dz]


def _collect_months(year):
    """
    收集流年 12 個流月。
    從 year 立春日開始，連續找 12 個「節」（奇數節氣編號）。
    """
    d = _find_lichun(year)
    months = []
    while len(months) < 12:
        if d.hasJieQi() and d.getJieQi() in MONTH_JIEQI:
            jq = d.getJieQi()
            m_gz = d.getMonthGZ()
            month_branch = JIEQI_TO_MONTH_BRANCH[jq]
            months.append({
                "節氣編號": jq,
                "節氣": JIEQI_NAMES[jq],
                "月地支": month_branch,
                "月序": MONTH_BRANCH_ORDER[month_branch],
                "月名": MONTH_BRANCH_NAMES[month_branch],
                "起始": "%04d-%02d-%02d" % (
                    d.getSolarYear(), d.getSolarMonth(), d.getSolarDay()
                ),
                "干支": _gz_string(m_gz),
                "天干": HEAVENLY_STEMS[m_gz.tg],
                "地支": EARTHLY_BRANCHES[m_gz.dz],
            })
        d = d.after(1)
    return months


# ============================================================
# 六親類象表（用於白話斷語）
# 依《增刪卜易》《卜筮正宗》傳統類象
# ============================================================
_LIUQIN_CATEGORY = {
    # 通用類象（不分性別）
    None: {
        "父母": "文書、合約、學業、房產、車輛、長輩",
        "官鬼": "工作、職位、官非、疾病",
        "妻財": "錢財、生意、物品",
        "子孫": "子女、晚輩、寵物、出行、解憂、藥物",
        "兄弟": "朋友、合夥、競爭、破財、同輩",
    },
    # 女命類象（官鬼加上「夫星/男友」）
    "F": {
        "父母": "文書、合約、學業、房產、車輛、長輩",
        "官鬼": "工作、職位、丈夫/男友、疾病、官非",
        "妻財": "錢財、生意、物品",
        "子孫": "子女、晚輩、寵物、出行、解憂、藥物",
        "兄弟": "朋友、合夥、競爭、破財、同輩",
    },
    # 男命類象（妻財加上「妻/女友」）
    "M": {
        "父母": "文書、合約、學業、房產、車輛、長輩",
        "官鬼": "工作、職位、官非、疾病",
        "妻財": "錢財、妻子/女友、生意、物品",
        "子孫": "子女、晚輩、寵物、出行、解憂、藥物",
        "兄弟": "朋友、合夥、競爭、破財、同輩",
    },
}


def _liuqin_category(liuqin, gender=None):
    """
    回傳六親對應的人事物範疇文字。
    依性別調整：女命強調「夫星」，男命強調「妻星」。
    """
    table = _LIUQIN_CATEGORY.get(gender) or _LIUQIN_CATEGORY[None]
    return table.get(liuqin, liuqin)


# ============================================================
# 流年斷語（白話版）
# ============================================================
def _year_remarks(year_block, shi_liuqin, gender=None):
    """流年層級斷語"""
    out = []
    sk = year_block["對世爻"]
    hc = year_block["對世爻合沖"]

    if sk == "比和":
        text = "流年跟世爻同五行，氣場合得來。今年自己狀態不錯，但要留意身邊同輩、合夥人之間的拉扯。"
        if shi_liuqin == "兄弟":
            text += "特別要小心因為朋友合夥的事破財。"
        out.append({"level": "中", "text": text})
    elif sk == "生我":
        out.append({"level": "吉",
                    "text": "流年生世爻 — 今年容易遇到貴人、長輩幫忙，文書合約、學習考試都比較順。"})
    elif sk == "我生":
        out.append({"level": "中",
                    "text": "世爻生流年 — 今年比較會付出、操心、為別人忙，口舌是非也偏多。"})
    elif sk == "剋我":
        out.append({"level": "凶",
                    "text": "流年剋世爻 — 今年壓力比較大，事情阻力多，要提防小人跟是非。"})
    elif sk == "我剋":
        out.append({"level": "警",
                    "text": "世爻剋流年 — 今年凡事想自己作主，但跟大環境／上面的人會有摩擦，別硬碰硬。"})

    if hc == "相沖":
        out.append({"level": "凶",
                    "text": "歲沖世爻 — 今年變動多、奔波、不安穩，計畫常常會反覆改來改去。"})
    elif hc == "相合":
        out.append({"level": "吉",
                    "text": "歲合世爻 — 今年和氣、機會多、貴人到位，要做的事比較容易成。"})

    for r in year_block["對六爻"]:
        if r["動爻"] and r["動爻出去"]:
            o = r["動爻出去"]
            category = _liuqin_category(o["六親"], gender)
            if o["合沖"] == "相沖":
                out.append({
                    "level": "警",
                    "text": f"{r['爻序名']}動，變出去的{o['六親']}（主{category}）跟太歲相沖 — "
                            f"今年在這方面（{category}）會有突如其來的變動或衝突。"
                })
            elif o["合沖"] == "相合":
                out.append({
                    "level": "吉",
                    "text": f"{r['爻序名']}動，變出去的{o['六親']}（主{category}）跟太歲相合 — "
                            f"今年在這方面（{category}）比較容易塵埃落定、有好結果。"
                })

    for f in year_block["引動伏神"]:
        category = _liuqin_category(f["六親"], gender)
        out.append({
            "level": "中",
            "text": f"伏在{f['爻序名']}底下的{f['六親']}（{f['地支']}，主{category}）被太歲引動 — "
                    f"今年在這方面（{category}）會浮上檯面、有明顯動向。"
        })

    return out


def _month_remarks(month_block, shi_liuqin, gender=None):
    """流月層級斷語"""
    out = []
    sk = month_block["對世爻"]
    hc = month_block["對世爻合沖"]
    m_name = month_block["月名"]

    if sk == "剋我" and hc == "相沖":
        out.append({"level": "凶",
                    "text": f"{m_name}最要小心 — 流月又剋又沖世爻。重要的事這個月先別動，留意意外跟身體健康。"})
    elif sk == "剋我":
        out.append({"level": "警",
                    "text": f"{m_name}壓力大 — 工作上的事、人際是非會比較多，提防小人。"})
    elif sk == "生我" and hc == "相合":
        out.append({"level": "吉",
                    "text": f"{m_name}最順 — 流月生合世爻，該推動的事這個月推，容易遇到貴人。"})
    elif sk == "生我":
        out.append({"level": "吉",
                    "text": f"{m_name}有助力 — 文書、合約、學習、長輩相關的事比較順。"})

    for f in month_block["引動伏神"]:
        lq = f["六親"]
        if lq == "妻財":
            out.append({"level": "吉", "text": f"{m_name}引動妻財 — 利財運，容易進財。"})
        elif lq == "官鬼":
            out.append({"level": "警", "text": f"{m_name}引動官鬼 — 工作壓力、是非、健康要特別注意。"})
        elif lq == "父母":
            out.append({"level": "中", "text": f"{m_name}引動父母 — 文書、合約、長輩、房子車子之類的事會有動向。"})
        elif lq == "子孫":
            out.append({"level": "吉", "text": f"{m_name}引動子孫 — 後輩、小孩、出門遠行、宗教相關的事比較有進展，煩心事也容易解開。"})
        elif lq == "兄弟":
            out.append({"level": "警", "text": f"{m_name}引動兄弟 — 跟朋友合夥、競爭有關的事會冒出來，留意破財。"})

    for r in month_block["對六爻"]:
        if r["動爻"] and r["動爻出去"] and r["動爻出去"]["合沖"] == "相沖":
            o = r["動爻出去"]
            category = _liuqin_category(o["六親"], gender)
            out.append({
                "level": "警",
                "text": f"{m_name} — {r['爻序名']}動，變出去的{o['六親']}（主{category}）跟月支相沖，"
                        f"這個月在這方面（{category}）會有狀況或變動。"
            })

    return out


def generate_remarks(fortune_result):
    """根據流年計算結果產生白話斷語清單"""
    shi_liuqin = fortune_result["原命盤"]["本卦"]["世爻六親"]
    gender = fortune_result.get("性別")
    year_list = _year_remarks(fortune_result["流年"], shi_liuqin, gender=gender)
    month_map = {}
    for m in fortune_result["流月"]:
        month_map[m["月名"]] = _month_remarks(m, shi_liuqin, gender=gender)
    return {"流年": year_list, "流月": month_map}


# ============================================================
# 四面向斷語（呼叫 divination.aspects.*）
# ============================================================
def _generate_aspects_for_block(block, scope_name, gender=None, is_year_scope=False):
    """對一個 fortune block 產生四面向斷語"""
    yao_rows = block["對六爻"]
    aroused = block["引動伏神"]
    return {
        "財運": wealth.analyze(yao_rows, block, aroused, scope_name,
                               gender=gender, is_year_scope=is_year_scope),
        "健康": health.analyze(yao_rows, block, aroused, scope_name,
                               gender=gender, is_year_scope=is_year_scope),
        "工作": work.analyze(yao_rows, block, aroused, scope_name,
                             gender=gender, is_year_scope=is_year_scope),
        "感情": love.analyze(yao_rows, block, aroused, scope_name,
                             gender=gender, is_year_scope=is_year_scope),
    }


def generate_aspects(fortune_result, gender=None):
    """產生流年 + 12 流月的四面向斷語"""
    year_aspects = _generate_aspects_for_block(
        fortune_result["流年"], "今年", gender=gender, is_year_scope=True)

    month_aspects = {}
    for m in fortune_result["流月"]:
        month_aspects[m["月名"]] = _generate_aspects_for_block(
            m, m["月名"], gender=gender, is_year_scope=False)

    return {"流年": year_aspects, "流月": month_aspects}


# ============================================================
# 主函式
# ============================================================
def analyze_fortune(chart_dt, target_year, gender=None):
    """
    流年排盤主函式。

    輸入：
      chart_dt:    原命盤 datetime
      target_year: 流年西元年（例如 2026）
      gender:      'M' / 'F' / None — 影響健康(婦科)與感情面向

    輸出 dict 與原版完全一致（含「原命盤」「流年」「流月」「斷語」「四面向」）
    """
    # === 1. 跑原命盤 ===
    chart = cast_hexagram(chart_dt)
    orig = chart["本卦"]
    yao_rows = orig["爻"]
    shi_idx = next(i for i, r in enumerate(yao_rows) if r["世"])
    shi_branch = yao_rows[shi_idx]["地支"]
    shi_element = yao_rows[shi_idx]["五行"]
    shi_liuqin = yao_rows[shi_idx]["六親"]

    # === 2. 流年地支 ===
    lichun_day = _find_lichun(target_year)
    year_gz = lichun_day.getYearGZ()
    year_stem = HEAVENLY_STEMS[year_gz.tg]
    year_branch = EARTHLY_BRANCHES[year_gz.dz]
    year_element = BRANCH_ELEMENT[year_branch]

    year_yao_rows = analyze_yao_actions(yao_rows, year_branch)
    year_block = {
        "西元":     target_year,
        "立春日":   "%04d-%02d-%02d" % (
            lichun_day.getSolarYear(),
            lichun_day.getSolarMonth(),
            lichun_day.getSolarDay()
        ),
        "干支":     year_stem + year_branch,
        "天干":     year_stem,
        "地支":     year_branch,
        "五行":     year_element,
        "對世爻":     element_relation(shi_element, year_element),
        "對世爻合沖": branch_relation(shi_branch, year_branch),
        "對六爻":     year_yao_rows,
        "主導爻":     dominant_yaos(year_yao_rows),
        "引動伏神":   find_aroused_fushen(yao_rows, year_branch),
    }

    # === 3. 流月 ===
    months_raw = _collect_months(target_year)
    flow_months = []
    for m in months_raw:
        m_branch = m["地支"]
        m_element = BRANCH_ELEMENT[m_branch]
        m_yao_rows = analyze_yao_actions(yao_rows, m_branch)
        flow_months.append({
            "月序":     m["月序"],
            "月名":     m["月名"],
            "節氣":     m["節氣"],
            "起始":     m["起始"],
            "干支":     m["干支"],
            "天干":     m["天干"],
            "地支":     m_branch,
            "五行":     m_element,
            "對世爻":     element_relation(shi_element, m_element),
            "對世爻合沖": branch_relation(shi_branch, m_branch),
            "對六爻":     m_yao_rows,
            "主導爻":     dominant_yaos(m_yao_rows),
            "引動伏神":   find_aroused_fushen(yao_rows, m_branch),
        })

    # === 4. 組合結果 ===
    result = {
        "原命盤": {
            "公曆": chart["公曆"],
            "農曆": chart["農曆"],
            "四柱": chart["四柱"],
            "本卦": {
                "卦名":     orig["卦名"],
                "卦辭":     orig["卦辭"],
                "卦宮":     orig["卦宮"],
                "卦變":     orig["卦變"],
                "世爻五行": orig["世爻五行"],
                "世爻index": shi_idx,
                "世爻地支":  shi_branch,
                "世爻六親":  shi_liuqin,
            },
            "變卦卦名": chart["變卦"]["卦名"],
            "卦變總論": chart.get("卦變總論"),
        },
        "流年": year_block,
        "流月": flow_months,
        "性別": gender,
    }
    # === 5. 附上白話斷語與四面向 ===
    result["斷語"] = generate_remarks(result)
    result["四面向"] = generate_aspects(result, gender=gender)
    return result


# ============================================================
# 自測
# ============================================================
if __name__ == "__main__":
    from datetime import datetime
    chart_dt = datetime(1990, 8, 11, 10, 0)
    result = analyze_fortune(chart_dt, 2026)

    print(f"=== 原命盤 ===")
    print(f"公曆 {result['原命盤']['公曆']}")
    print(f"本卦 {result['原命盤']['本卦']['卦名']} "
          f"({result['原命盤']['本卦']['卦宮']}宮)")

    y = result["流年"]
    print(f"\n=== 流年 {y['西元']} {y['干支']} ===")
    print(f"立春:{y['立春日']}  對世爻:{y['對世爻']}/{y['對世爻合沖'] or '—'}")

    print(f"\n=== 流年四面向 ===")
    for aspect, items in result["四面向"]["流年"].items():
        print(f"  [{aspect}] {len(items)} 條訊號")
