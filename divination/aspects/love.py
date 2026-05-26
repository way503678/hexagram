# -*- coding: utf-8 -*-
"""
divination.aspects.love — 感情面判讀

主用神：
  女命 → 官鬼（夫星/男友）；妻財為情敵
  男命 → 妻財（妻/女友）；官鬼為情敵
  未指定性別 → 妻財 + 官鬼 兩條線

判讀規則（對齊原版 + 補強傳統規則）：
  1. 主用神被生剋沖合（含六神升級：青龍/玄武/白虎/朱雀）
  2. 第三者徵兆（需強化條件，不單看兩現）：
     - 官鬼動化妻財（女）/ 妻財動化官鬼（男）
     - 官鬼與妻財相合
     - 官鬼伏於妻財/兄弟下（女）/ 妻財伏於官鬼/兄弟下（男）
     - 用神兩現 + 配合條件
  3. 用神過旺反凶
  4. 伏神浮出
  5. 男命兄弟動 = 競爭者

is_year_scope=True 時，會帶出靜態卦面徵兆（伏神位置、用神兩現）。
"""
from fortune_data import LIUHE_PAIRS

from ..core import hidden, yongshen
from ..core.signals import emit, dedupe, merge_by_yao, normalize_tengshe


def analyze(yao_rows, outer_block, aroused_fushen, scope_name,
            gender=None, is_year_scope=False):
    """
    感情面主分析函式。

    參數：
      yao_rows:        經過 trigger.analyze_yao_actions 處理的爻 list
      outer_block:     含「對世爻」「對世爻合沖」「地支」的 dict（流年/流月 block）
      aroused_fushen:  被外來地支引動的伏神 list
      scope_name:      訊號的時間範圍前綴（如「今年」「正月」）
      gender:          'M' / 'F' / None
      is_year_scope:   True 時帶出靜態卦面徵兆

    回傳：list of {"level": "吉/中/警/凶", "text": "..."}
    """
    out = []

    cai_yaos  = hidden.find_by_liuqin(yao_rows, "妻財")
    guan_yaos = hidden.find_by_liuqin(yao_rows, "官鬼")

    # 世應爻(感情面 select_primary 需要)
    shi_yao = next((r for r in yao_rows if r.get("世")), None)
    ying_yao = next((r for r in yao_rows if r.get("應")), None)

    if gender == 'F':
        _analyze_female(out, yao_rows, cai_yaos, guan_yaos, aroused_fushen,
                        outer_block, scope_name, is_year_scope,
                        shi_yao, ying_yao)
    elif gender == 'M':
        _analyze_male(out, yao_rows, cai_yaos, guan_yaos, aroused_fushen,
                      outer_block, scope_name, is_year_scope,
                      shi_yao, ying_yao)
    else:
        _analyze_neutral(out, cai_yaos, guan_yaos, aroused_fushen, scope_name)

    return merge_by_yao(dedupe(out))


# ============================================================
# 女命感情判讀
# ============================================================
def _analyze_female(out, yao_rows, cai_yaos, guan_yaos, aroused_fushen,
                    outer_block, scope_name, is_year_scope,
                    shi_yao=None, ying_yao=None):
    """女命：官鬼為主用神，妻財為情敵"""

    # === 主用神取捨（兩現以上時）===
    primary, secondary, role_info = yongshen.select_primary(
        guan_yaos, world_yao=shi_yao, response_yao=ying_yao,
        aspect="love", gender="F"
    )

    # === 兩現總綱（只在流年顯示）===
    if is_year_scope and len(guan_yaos) >= 2:
        summary = yongshen.make_summary_signal(
            "官鬼", guan_yaos, primary, secondary, role_info, scope_name
        )
        if summary:
            out.append(summary)

    # === 官鬼爻判讀（主用神）===
    for y in guan_yaos:
        sk = y["生剋"]
        hc = y["合沖"]
        ls = normalize_tengshe(y.get("六神", ""))
        tag = yongshen.role_tag(y, primary, secondary, role_info)
        tag_suffix = f" {tag}" if tag else ""

        # 六神升級
        if y["動爻"] and ls == "玄武":
            emit(out, "警", f"{scope_name}官鬼臨玄武動{tag_suffix} — 主桃花暗動或第三者(他方)介入，感情有暗潮。", y)
        elif y["動爻"] and ls == "白虎":
            emit(out, "凶", f"{scope_name}官鬼臨白虎動{tag_suffix} — 主與伴侶激烈衝突,或對方有意外、健康問題。", y)
        elif y["動爻"] and ls == "朱雀":
            emit(out, "警", f"{scope_name}官鬼臨朱雀動{tag_suffix} — 主口角爭吵、緋聞或感情糾紛。", y)
        elif y["動爻"] and ls == "青龍" and sk in ("生我", "比和"):
            emit(out, "吉", f"{scope_name}官鬼臨青龍動且得令{tag_suffix} — 主姻緣、正緣、感情升溫,有結婚或喜慶之事。", y)
        elif y["動爻"]:
            emit(out, "中", f"{scope_name}官鬼爻動{tag_suffix} — 伴侶有動向、感情有變化。", y)

        # 不分動靜：被合沖剋
        if hc == "相合":
            emit(out, "中", f"{scope_name}官鬼被合{tag_suffix} — 夫星/伴侶有合來之意,男性緣動。", y)
        elif hc == "相沖" and ls != "白虎":
            emit(out, "警", f"{scope_name}官鬼被沖{tag_suffix} — 夫妻爭執或男方有變動。", y)
        if sk == "剋我":
            emit(out, "警", f"{scope_name}官鬼受剋{tag_suffix} — 夫星受傷,伴侶健康或事業可能出狀況。", y)

    # === 靜態卦面徵兆（只在流年顯示）===
    if is_year_scope:
        _check_female_thirdparty(out, yao_rows, cai_yaos, guan_yaos, scope_name)
        # 過旺反凶只對機兆主用神判斷（不對每個兩現的爻重複報）
        if primary is not None:
            _check_yongshen_overflowing(out, [primary], yao_rows, outer_block, scope_name,
                                        yongshen_name="官鬼", role="夫星")

    # === 伏神浮出 ===
    for f in aroused_fushen:
        if f["六親"] == "官鬼":
            out.append({"level": "中",
                        "text": f"{scope_name}官鬼伏神浮出 — 潛藏的感情線浮現，新對象或舊情人出現。"})
        elif f["六親"] == "妻財":
            out.append({"level": "警",
                        "text": f"{scope_name}妻財伏神浮出 — 潛藏的情敵(藏在暗處的女性)出現。"})


def _check_female_thirdparty(out, yao_rows, cai_yaos, guan_yaos, scope_name):
    """
    女命第三者徵兆判讀（依《增刪卜易》《卜筮正宗》傳統規則）

    重要原則：
    - 所有徵兆用「主...之象」「多為...」等保守語氣，不下絕對斷言
    - 採強化條件原則：單一徵兆下「中」、多重徵兆累加才升「警」
    - 避免單看「兩現」就斷外遇；要配合動爻/合化方向才強化
    """
    response_yao = next((r for r in yao_rows if r["應"]), None)

    # 收集所有徵兆（後面統一整理）
    signals = []

    # === 徵兆 1：官鬼動化妻財 ===
    # 夫星牽連他女（直接的動化徵兆，較明確）
    for y in guan_yaos:
        if not y.get("動爻"):
            continue
        dong_out = y.get("動爻出去") or {}
        if dong_out.get("六親") == "妻財":
            signals.append({
                "強度": "強",
                "text": f"{scope_name}官鬼動化出妻財({y['爻序名']}) — 夫星化向他女,主男方有移情之象。",
                "_yao": y,
            })

    # === 徵兆 2：妻財動化官鬼（女方動向）===
    # 注意：這條已不是傳統的「兩財兩官 → 外遇」單一條件，而是動化的方向
    # 這是「自己（女命）出現了另一個男人」的徵兆，不是男方外遇
    for y in cai_yaos:
        if not y.get("動爻"):
            continue
        dong_out = y.get("動爻出去") or {}
        # 妻財化官鬼 — 在女命卦裡是「自己情感生變」的徵兆，不是直接外遇
        if dong_out.get("六親") == "官鬼":
            signals.append({
                "強度": "中",
                "text": f"{scope_name}妻財動化官鬼({y['爻序名']}) — 卦面複雜,自己也有感情線變動之象。",
                "_yao": y,
            })

    # === 徵兆 3：妻財與官鬼相合（含伏神官鬼）===
    # 「夫星跟別女合住」— 含現的妻財與現/伏的官鬼
    # 依傳統「合」象徵連結、糾纏
    all_guan = list(guan_yaos)
    # 加入伏神官鬼
    hidden_guan = hidden.find_hidden_under(yao_rows, "官鬼")
    for h in hidden_guan:
        all_guan.append({
            "爻序名": h["飛神爻序名"] + "(伏)",
            "地支": h["伏神地支"],
            "動爻": False,
            "_是伏神": True,
        })

    for guan in all_guan:
        for cai in cai_yaos:
            if guan["地支"] == cai["地支"]:
                continue
            pair = frozenset({guan["地支"], cai["地支"]})
            if pair not in LIUHE_PAIRS:
                continue
            # 強化條件：必須有一爻動，或官鬼為伏神（伏神 + 合 = 暗中關連）
            triggered = guan.get("動爻") or cai.get("動爻") or guan.get("_是伏神")
            if not triggered:
                continue
            tag = "(伏神)" if guan.get("_是伏神") else ""
            # 此徵兆歸屬到妻財爻（飛神 / 用神），讓 merge_by_yao 能跟「官鬼伏於妻財之下」聚合
            signals.append({
                "強度": "中",
                "text": f"{scope_name}官鬼{tag}與妻財相合({guan['地支']}{cai['地支']}合) "
                        f"— 主夫星與他女有牽連之象。",
                "_yao": cai,
            })

    # === 徵兆 4：官鬼伏藏的位置（《增刪卜易》——「用神不現則看伏神」）===
    # 重要：傳統有兩種解釋方向，必須說清楚
    # （a）「官鬼伏 → 夫星不顯，亦有兩人分居、異地、外出之象」（《姻緣篇》）
    # （b）「伏於妻財下 → 多為男方有另外感情之象」（《姻緣篇》）
    # 兩說並存，且後者用「多為」而非「必為」
    # 歸屬到飛神所在爻 — 跟「合」徵兆能聚合
    if not hidden.is_present(yao_rows, "官鬼"):
        for h in hidden_guan:
            feishen_lq = h["飛神六親"]
            飛神位 = h["飛神爻序名"]
            # 找到飛神對應的實際爻 entry
            feishen_yao = next((r for r in yao_rows if r["爻序名"] == 飛神位), None)
            if feishen_lq == "妻財":
                signals.append({
                    "強度": "中",
                    "text": f"{scope_name}官鬼不上卦,伏於{飛神位}妻財之下 — "
                            f"傳統有兩說：一主夫星藏於他女處之象,一主分居/異地/夫星不顯。需配合其他卦象綜合判斷。",
                    "_yao": feishen_yao,
                })
            elif feishen_lq == "兄弟":
                signals.append({
                    "強度": "中",
                    "text": f"{scope_name}官鬼不上卦,伏於{飛神位}兄弟之下 — "
                            f"主夫星受競爭者牽絆,亦有夫星受朋友/外人影響之象。",
                    "_yao": feishen_yao,
                })
            elif feishen_lq == "父母":
                signals.append({
                    "強度": "中",
                    "text": f"{scope_name}官鬼不上卦,伏於{飛神位}父母之下 — "
                            f"主夫星受長輩/家族牽制,或夫忙於事業文書,聚少離多。",
                    "_yao": feishen_yao,
                })
            elif feishen_lq == "子孫":
                signals.append({
                    "強度": "中",
                    "text": f"{scope_name}官鬼不上卦,伏於{飛神位}子孫之下 — "
                            f"子孫克官鬼,主夫星受小孩/晚輩牽絆,或女命有「不思夫」之象。",
                    "_yao": feishen_yao,
                })

    # === 徵兆 5：官鬼兩現 + 強化條件 ===
    # 《卜筮正宗》《增刪卜易》：「兩官兩財」主「再嫁再娶」或「外遇之類」
    # 但要看動靜：兩官皆動或一動一靜，意義不同
    # 加上：兩官時，與世爻陰陽異性者為正夫，同性者為偏夫（《六爻測婚總論》）
    if len(guan_yaos) >= 2:
        moving_count = sum(1 for g in guan_yaos if g.get("動爻"))
        if moving_count >= 1:
            signals.append({
                "強度": "強",
                "text": f"{scope_name}卦中官鬼兩現且有動 — 主感情線複雜,有再嫁再娶或多重感情線之象。"
            })
        else:
            signals.append({
                "強度": "中",
                "text": f"{scope_name}卦中官鬼兩現(俱靜) — 主感情可能有多重對象之象,需配合其他條件判斷。"
            })

    # === 徵兆 6：應爻位置不正（《增刪卜易》「應爻為夫位」）===
    # 女命：應爻臨官鬼為正夫位；應臨妻財/兄弟為位不正
    if response_yao:
        ying_lq = response_yao.get("六親", "")
        if ying_lq == "妻財":
            signals.append({
                "強度": "中",
                "text": f"{scope_name}應爻臨妻財(位不正) — 女命應爻當為官鬼夫位,"
                        f"今應臨妻財,主對方位置上有他女之象。",
                "_yao": response_yao,
            })
        elif ying_lq == "兄弟":
            signals.append({
                "強度": "中",
                "text": f"{scope_name}應爻臨兄弟 — 對方位置有競爭者或男性朋友干擾之象。",
                "_yao": response_yao,
            })

    # === 徵兆 7：應爻動化方向（對方變動）===
    if response_yao and response_yao.get("動爻"):
        dong_out = response_yao.get("動爻出去") or {}
        dong_lq = dong_out.get("六親", "")
        if dong_lq == "子孫":
            # 子孫克官鬼，對夫星不利
            signals.append({
                "強度": "中",
                "text": f"{scope_name}應爻動化子孫 — 子孫克官鬼,主對方狀態對夫星不利,夫妻關係有變之象。",
                "_yao": response_yao,
            })
        elif dong_lq == "妻財":
            signals.append({
                "強度": "中",
                "text": f"{scope_name}應爻動化妻財 — 主對方關心錢財或別的女性,感情上分心之象。",
                "_yao": response_yao,
            })

    # === 強化條件原則：依累計徵兆數調整等級 ===
    # 1 條徵兆 → 「中」
    # 2 條徵兆 → 「中」（保持，但加綜合說明）
    # 3+ 條徵兆 → 升「警」 + 綜合提示
    # 「強」徵兆直接 「警」
    
    if not signals:
        return
    
    strong_count = sum(1 for s in signals if s["強度"] == "強")
    total = len(signals)
    
    # 把訊號加入 out，並附上 _yao_key / _yao_index 讓 merge_by_yao 能聚合
    for s in signals:
        level = "警" if s["強度"] == "強" else "中"
        signal = {"level": level, "text": s["text"]}
        y = s.get("_yao")
        if y is not None and "爻序名" in y:
            signal["_yao_key"] = f"{y['爻序名']}{y.get('六親','')}"
            signal["_yao_index"] = y.get("index", -1)
        out.append(signal)
    
    # 多重徵兆綜合提示（3+ 或 含強徵兆 + 2+ 中）
    if total >= 3 or (strong_count >= 1 and total >= 2):
        out.append({
            "level": "警",
            "text": f"{scope_name}【綜合】卦中有 {total} 條第三者/感情變動相關徵兆,"
                    f"提示感情關係可能複雜,建議謹慎處理、多方溝通。"
        })


# ============================================================
# 男命感情判讀
# ============================================================
def _analyze_male(out, yao_rows, cai_yaos, guan_yaos, aroused_fushen,
                  outer_block, scope_name, is_year_scope,
                  shi_yao=None, ying_yao=None):
    """男命：妻財為主用神，官鬼為情敵"""

    # === 主用神取捨（兩現以上時）===
    primary, secondary, role_info = yongshen.select_primary(
        cai_yaos, world_yao=shi_yao, response_yao=ying_yao,
        aspect="love", gender="M"
    )

    # === 兩現總綱（只在流年顯示）===
    if is_year_scope and len(cai_yaos) >= 2:
        summary = yongshen.make_summary_signal(
            "妻財", cai_yaos, primary, secondary, role_info, scope_name
        )
        if summary:
            out.append(summary)

    # === 妻財爻判讀（主用神）===
    for y in cai_yaos:
        sk = y["生剋"]
        hc = y["合沖"]
        ls = normalize_tengshe(y.get("六神", ""))
        tag = yongshen.role_tag(y, primary, secondary, role_info)
        tag_suffix = f" {tag}" if tag else ""

        # 六神升級
        if y["動爻"] and ls == "玄武":
            emit(out, "警", f"{scope_name}妻財臨玄武動{tag_suffix} — 主桃花暗動或感情有暗潮、女方暗中往來。", y)
        elif y["動爻"] and ls == "白虎":
            emit(out, "凶", f"{scope_name}妻財臨白虎動{tag_suffix} — 主與伴侶激烈衝突,或對方有意外、健康問題。", y)
        elif y["動爻"] and ls == "朱雀":
            emit(out, "警", f"{scope_name}妻財臨朱雀動{tag_suffix} — 主口角爭吵、緋聞或感情糾紛。", y)
        elif y["動爻"] and ls == "青龍" and sk in ("生我", "比和"):
            emit(out, "吉", f"{scope_name}妻財臨青龍動且得令{tag_suffix} — 主姻緣、正緣、感情升溫,有結婚或喜慶之事。", y)
        elif y["動爻"]:
            emit(out, "中", f"{scope_name}妻財爻動{tag_suffix} — 伴侶有動向、感情有變化。", y)

        # 不分動靜
        if hc == "相合":
            emit(out, "中", f"{scope_name}妻財被合{tag_suffix} — 妻/女友有合來之意，女性緣動。", y)
        elif hc == "相沖" and ls != "白虎":
            emit(out, "警", f"{scope_name}妻財被沖{tag_suffix} — 與伴侶有爭執，女方有變動。", y)
        if sk == "剋我":
            emit(out, "警", f"{scope_name}妻財受剋{tag_suffix} — 妻星受傷，伴侶健康或事業可能出狀況。", y)

    # === 靜態卦面徵兆（只在流年顯示）===
    if is_year_scope:
        _check_male_thirdparty(out, yao_rows, cai_yaos, guan_yaos, scope_name)
        # 過旺反凶只對機兆主用神判斷
        if primary is not None:
            _check_yongshen_overflowing(out, [primary], yao_rows, outer_block, scope_name,
                                        yongshen_name="妻財", role="妻星")

    # === 兄弟動 = 競爭者 ===
    xiongdi_yaos = hidden.find_by_liuqin(yao_rows, "兄弟")
    for y in xiongdi_yaos:
        if y["動爻"]:
            emit(out, "警",
                 f"{scope_name}兄弟動 — 主競爭者出現,留意身邊男性介入感情或追求對象。",
                 y)
            break  # 一條就夠

    # === 伏神浮出 ===
    for f in aroused_fushen:
        if f["六親"] == "妻財":
            out.append({"level": "中",
                        "text": f"{scope_name}妻財伏神浮出 — 潛藏的感情線浮現，新對象或舊情人出現。"})
        elif f["六親"] == "官鬼":
            out.append({"level": "警",
                        "text": f"{scope_name}官鬼伏神浮出 — 潛藏的競爭者(藏在暗處的男性)出現。"})


def _check_male_thirdparty(out, yao_rows, cai_yaos, guan_yaos, scope_name):
    """
    男命第三者徵兆判讀（依《增刪卜易》《卜筮正宗》傳統規則）

    與女命邏輯對偶：
      - 男命主用神為妻財，官鬼為情敵/競爭者
      - 應用同樣的「徵兆 + 強化條件」原則
    """
    response_yao = next((r for r in yao_rows if r["應"]), None)
    signals = []

    # === 徵兆 1：妻財動化官鬼 ===
    # 妻星牽連他男（直接的動化徵兆）
    for y in cai_yaos:
        if not y.get("動爻"):
            continue
        dong_out = y.get("動爻出去") or {}
        if dong_out.get("六親") == "官鬼":
            signals.append({
                "強度": "強",
                "text": f"{scope_name}妻財動化出官鬼({y['爻序名']}) — 妻星化向他男,主女方有移情之象。",
                "_yao": y,
            })

    # === 徵兆 2：官鬼動化妻財（男方動向）===
    for y in guan_yaos:
        if not y.get("動爻"):
            continue
        dong_out = y.get("動爻出去") or {}
        if dong_out.get("六親") == "妻財":
            signals.append({
                "強度": "中",
                "text": f"{scope_name}官鬼動化妻財({y['爻序名']}) — 卦面複雜,自己也有感情線變動之象。",
                "_yao": y,
            })

    # === 徵兆 3：妻財與官鬼相合（含伏神妻財）===
    all_cai = list(cai_yaos)
    hidden_cai = hidden.find_hidden_under(yao_rows, "妻財")
    for h in hidden_cai:
        all_cai.append({
            "爻序名": h["飛神爻序名"] + "(伏)",
            "地支": h["伏神地支"],
            "動爻": False,
            "_是伏神": True,
        })

    for cai in all_cai:
        for guan in guan_yaos:
            if cai["地支"] == guan["地支"]:
                continue
            pair = frozenset({cai["地支"], guan["地支"]})
            if pair not in LIUHE_PAIRS:
                continue
            triggered = cai.get("動爻") or guan.get("動爻") or cai.get("_是伏神")
            if not triggered:
                continue
            tag = "(伏神)" if cai.get("_是伏神") else ""
            # 歸屬到官鬼爻（用神 / 飛神）
            signals.append({
                "強度": "中",
                "text": f"{scope_name}妻財{tag}與官鬼相合({cai['地支']}{guan['地支']}合) "
                        f"— 主妻星與他男有牽連之象。",
                "_yao": guan,
            })

    # === 徵兆 4：妻財伏藏的位置 ===
    # 歸屬到飛神所在爻
    if not hidden.is_present(yao_rows, "妻財"):
        for h in hidden_cai:
            feishen_lq = h["飛神六親"]
            飛神位 = h["飛神爻序名"]
            feishen_yao = next((r for r in yao_rows if r["爻序名"] == 飛神位), None)
            if feishen_lq == "官鬼":
                signals.append({
                    "強度": "中",
                    "text": f"{scope_name}妻財不上卦,伏於{飛神位}官鬼之下 — "
                            f"傳統有兩說：一主妻星藏於他男處之象,一主分居/異地/妻星不顯。需配合其他卦象。",
                    "_yao": feishen_yao,
                })
            elif feishen_lq == "兄弟":
                signals.append({
                    "強度": "中",
                    "text": f"{scope_name}妻財不上卦,伏於{飛神位}兄弟之下 — "
                            f"主妻星受競爭者牽絆,亦有妻星受朋友/外人影響之象。",
                    "_yao": feishen_yao,
                })
            elif feishen_lq == "父母":
                signals.append({
                    "強度": "中",
                    "text": f"{scope_name}妻財不上卦,伏於{飛神位}父母之下 — "
                            f"主妻星受長輩或娘家牽制,聚少離多。",
                    "_yao": feishen_yao,
                })
            elif feishen_lq == "子孫":
                signals.append({
                    "強度": "中",
                    "text": f"{scope_name}妻財不上卦,伏於{飛神位}子孫之下 — "
                            f"妻星受子孫所牽,主妻子心力放在子女身上,夫妻交流減少。",
                    "_yao": feishen_yao,
                })

    # === 徵兆 5：妻財兩現 + 強化條件 ===
    if len(cai_yaos) >= 2:
        moving_count = sum(1 for c in cai_yaos if c.get("動爻"))
        if moving_count >= 1:
            signals.append({
                "強度": "強",
                "text": f"{scope_name}卦中妻財兩現且有動 — 主感情線複雜,有再婚再娶或多重感情線之象。"
            })
        else:
            signals.append({
                "強度": "中",
                "text": f"{scope_name}卦中妻財兩現(俱靜) — 主感情可能有多重對象之象,需配合其他條件判斷。"
            })

    # === 徵兆 6：應爻位置不正 ===
    # 男命：應爻臨妻財為正妻位；應臨官鬼/兄弟為位不正
    if response_yao:
        ying_lq = response_yao.get("六親", "")
        if ying_lq == "官鬼":
            signals.append({
                "強度": "中",
                "text": f"{scope_name}應爻臨官鬼(位不正) — 男命應爻當為妻財妻位,"
                        f"今應臨官鬼,主對方位置上有他男之象或對方強勢。",
                "_yao": response_yao,
            })
        elif ying_lq == "兄弟":
            signals.append({
                "強度": "中",
                "text": f"{scope_name}應爻臨兄弟 — 對方位置有競爭者或同性朋友干擾之象。",
                "_yao": response_yao,
            })

    # === 徵兆 7：應爻動化方向 ===
    if response_yao and response_yao.get("動爻"):
        dong_out = response_yao.get("動爻出去") or {}
        dong_lq = dong_out.get("六親", "")
        if dong_lq == "兄弟":
            signals.append({
                "強度": "中",
                "text": f"{scope_name}應爻動化兄弟 — 兄弟克妻財,主對方狀態對妻星不利,夫妻關係有變之象。",
                "_yao": response_yao,
            })
        elif dong_lq == "官鬼":
            signals.append({
                "強度": "中",
                "text": f"{scope_name}應爻動化官鬼 — 主對方關心事業或別的男性,感情上分心之象。",
                "_yao": response_yao,
            })

    # === 強化條件原則 ===
    if not signals:
        return
    
    strong_count = sum(1 for s in signals if s["強度"] == "強")
    total = len(signals)
    
    # 把訊號加入 out，並附上 _yao_key / _yao_index 讓 merge_by_yao 能聚合
    for s in signals:
        level = "警" if s["強度"] == "強" else "中"
        signal = {"level": level, "text": s["text"]}
        y = s.get("_yao")
        if y is not None and "爻序名" in y:
            signal["_yao_key"] = f"{y['爻序名']}{y.get('六親','')}"
            signal["_yao_index"] = y.get("index", -1)
        out.append(signal)
    
    if total >= 3 or (strong_count >= 1 and total >= 2):
        out.append({
            "level": "警",
            "text": f"{scope_name}【綜合】卦中有 {total} 條第三者/感情變動相關徵兆,"
                    f"提示感情關係可能複雜,建議謹慎處理、多方溝通。"
        })


def _check_yongshen_overflowing(out, yongshens, yao_rows, outer_block, scope_name,
                                 yongshen_name, role):
    """過旺反凶偵測（《增刪卜易》原則）"""
    outer_branch = outer_block.get("地支")
    if not outer_branch:
        return
    for y in yongshens:
        result = yongshen.check_overflowing(y, outer_branch, yao_rows)
        if result.get("is_overflowing"):
            out.append({
                "level": "警",
                "text": f"{scope_name}{yongshen_name}過旺({result['phase']}地，"
                        f"卦中另有{result['evidence_count']}爻支撐) — "
                        f"{role}過旺反主感情壓力大、過度依賴或關係失衡。"
            })


# ============================================================
# 未指定性別：統合看
# ============================================================
def _analyze_neutral(out, cai_yaos, guan_yaos, aroused_fushen, scope_name):
    """未指定性別：沿用原本『統合看』的規則"""
    for y in cai_yaos:
        if y["合沖"] == "相合":
            emit(out, "中", f"{scope_name}妻財被合 — 有情感合來，女性緣動。", y)
        elif y["合沖"] == "相沖":
            emit(out, "警", f"{scope_name}妻財被沖 — 女性緣有變動或衝突。", y)

    for y in guan_yaos:
        if y["合沖"] == "相合":
            emit(out, "中", f"{scope_name}官鬼被合 — 有男性貴人或感情合來。", y)
        elif y["合沖"] == "相沖":
            emit(out, "警", f"{scope_name}官鬼被沖 — 男性緣有變動。", y)

    for f in aroused_fushen:
        if f["六親"] in ("妻財", "官鬼"):
            out.append({"level": "中",
                        "text": f"{scope_name}{f['六親']}伏神浮出 — 隱藏的感情線浮現，新緣分或舊情人出現。"})
