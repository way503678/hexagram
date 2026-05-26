# -*- coding: utf-8 -*-
"""
divination.aspects.health — 健康面判讀

用神：世爻為主（自占），同時參考官鬼（病）、子孫（醫藥）、父母（壽元）。

判讀規則（對齊原版 + 補強傳統規則）：
  A. 沖世爻 — 身體不安、突發狀況
  B. 世爻五行衰旺（十二長生）— 弱地警示
  C. 子孫爻婦科訊號（女命專屬）
  D. 動爻變出子孫（女命專屬）
  E. 六神搭配：青龍臨世（吉慶）、玄武臨世剋（暗病）、白虎臨世（血光）

  【新增規則】
  F. 用化鬼、鬼化用、世變鬼 = 最凶
  G. 用神過旺反凶（《增刪卜易》物極必反）
  H. 官鬼伏神位置 → 病因（伏父=勞累、伏兄=情緒、伏財=飲食縱慾、伏子=驚嚇）
  I. 卦宮對應臟腑（指出可能病位）
  J. 子孫旬空 + 官鬼旬空 = 不治自愈（罕見組合）
"""
from core_data import BRANCH_ELEMENT

from ..core import hidden, traits, yongshen
from ..core.elements import strength_tier, twelve_phase
from ..core.signals import emit, dedupe, merge_by_yao, normalize_tengshe


def analyze(yao_rows, outer_block, aroused_fushen, scope_name,
            gender=None, is_year_scope=False):
    """
    健康面主分析函式。

    回傳：list of {"level": "吉/中/警/凶", "text": "..."}
    """
    out = []
    shi_yao = next((r for r in yao_rows if r["世"]), None)

    # 規則 A：沖世爻
    _check_world_disturbed(out, shi_yao, outer_block, scope_name)

    # 規則 B：世爻十二長生 + 六神搭配
    _check_world_strength(out, shi_yao, outer_block, scope_name)

    # 規則 C / D：女命子孫爻婦科訊號
    zi_disturbed_count = 0
    if gender == 'F':
        zi_disturbed_count = _check_female_zisun(out, yao_rows, scope_name)
        _check_female_dong_to_zisun(out, yao_rows, scope_name)

    # 規則 E：官鬼動 + 六神
    _check_guan_with_liushen(out, yao_rows, scope_name)

    # 規則 F：用化鬼、鬼化用、世變鬼（新增）
    if is_year_scope:
        _check_self_change_to_guan(out, shi_yao, scope_name)

    # 規則 G：用神過旺反凶（新增）
    if is_year_scope:
        _check_world_overflowing(out, shi_yao, yao_rows, outer_block, scope_name)

    # 規則 H：官鬼伏神位置 → 病因（新增）
    if is_year_scope:
        _check_guan_hidden_cause(out, yao_rows, scope_name)

    # 規則 I：卦宮對應臟腑（新增）
    if is_year_scope:
        _annotate_gong_organs(out, yao_rows, outer_block, scope_name)

    # 規則 J：子孫空 + 官鬼空 = 不治自愈（新增，罕見）
    if is_year_scope:
        _check_zi_guan_both_empty(out, yao_rows, scope_name)

    # 既有規則：官鬼得生 / 官鬼伏神浮出 / 子孫得生
    _check_legacy_rules(out, yao_rows, aroused_fushen, scope_name,
                        gender, zi_disturbed_count)

    return merge_by_yao(dedupe(out))


# ============================================================
# 規則 A：沖世爻
# ============================================================
def _check_world_disturbed(out, shi_yao, outer_block, scope_name):
    if not shi_yao:
        return
    sk = outer_block.get("對世爻", "")
    hc = outer_block.get("對世爻合沖", "")

    if sk == "剋我" and hc == "相沖":
        emit(out, "凶",
             f"{scope_name}健康警訊 — 世爻又剋又沖，留意意外、慢性病復發。",
             shi_yao)
    elif sk == "剋我":
        emit(out, "警",
             f"{scope_name}精神壓力大 — 容易疲勞、小病小痛。",
             shi_yao)
    elif hc == "相沖":
        # 沖世爻 + 六神升級
        shi_ls = normalize_tengshe(shi_yao.get("六神", ""))
        if shi_ls == "白虎":
            emit(out, "凶",
                 f"{scope_name}世爻臨白虎又被沖 — 主血光、外傷意外或女性出血類問題，特別小心。",
                 shi_yao)
        elif shi_ls == "玄武":
            emit(out, "警",
                 f"{scope_name}世爻臨玄武又被沖 — 暗病、泌尿或婦科系統易發狀況，亦防情緒低落。",
                 shi_yao)
        else:
            emit(out, "警",
                 f"{scope_name}世爻被沖 — 身體不安、容易突發狀況或舊疾發作，須注意作息與檢查。",
                 shi_yao)


# ============================================================
# 規則 B：世爻十二長生 + 六神搭配
# ============================================================
def _check_world_strength(out, shi_yao, outer_block, scope_name):
    if not shi_yao:
        return
    outer_branch = outer_block.get("地支")
    shi_element = BRANCH_ELEMENT.get(shi_yao["地支"])
    if not (outer_branch and shi_element):
        return

    phase = twelve_phase(shi_element, outer_branch)
    shi_ls = normalize_tengshe(shi_yao.get("六神", ""))

    if phase in ("絕", "墓", "胎"):
        if shi_ls in ("白虎", "玄武"):
            tail = "防血光手術" if shi_ls == "白虎" else "防暗病潛伏"
            out.append({
                "level": "凶",
                "text": f"{scope_name}世爻臨{shi_ls}又入「{phase}」地 — 健康險境，{tail}，務必就醫檢查。"
            })
        else:
            out.append({
                "level": "警",
                "text": f"{scope_name}世爻氣場虛弱(處於「{phase}」地)— 抵抗力差、體力下降，容易疲勞或舊疾發作。"
            })
    elif phase in ("病", "死"):
        out.append({
            "level": "中",
            "text": f"{scope_name}世爻氣勢稍弱(處於「{phase}」地)— 平穩中略有疲倦，注意作息。"
        })

    # 規則 E1：青龍臨世 + 得生或比和（吉慶）
    if shi_ls == "青龍" and shi_yao["生剋"] in ("生我", "比和"):
        out.append({"level": "吉",
                    "text": f"{scope_name}世爻臨青龍且得力 — 身心狀態佳，有醫療貴人或喜慶之事。"})

    # 規則 E2：玄武臨世 + 被剋（暗病訊號）
    if shi_ls == "玄武" and shi_yao["生剋"] == "剋我":
        out.append({"level": "警",
                    "text": f"{scope_name}世爻臨玄武且受剋 — 暗病潛伏、易心情低落或泌尿婦科問題，需檢查。"})


# ============================================================
# 規則 C：女命子孫爻婦科訊號
# ============================================================
def _check_female_zisun(out, yao_rows, scope_name):
    """回傳擾動的子孫爻數量"""
    zi_yaos = hidden.find_by_liuqin(yao_rows, "子孫")
    zi_disturbed_count = 0
    zi_has_baihu = False
    zi_has_xuanwu = False
    zi_has_qinglong = False
    zi_signals = []

    for y in zi_yaos:
        disturbed = False
        if y["合沖"] == "相沖":
            zi_signals.append("被沖")
            disturbed = True
        elif y["合沖"] == "相合":
            zi_signals.append("被合")
            disturbed = True
        if y["動爻"]:
            zi_signals.append("動爻")
            disturbed = True
            if y.get("動爻出去") and y["動爻出去"].get("生剋") == "比和":
                zi_signals.append("化進神")
        if disturbed:
            zi_disturbed_count += 1
            ls = normalize_tengshe(y.get("六神", ""))
            if ls == "白虎": zi_has_baihu = True
            elif ls == "玄武": zi_has_xuanwu = True
            elif ls == "青龍": zi_has_qinglong = True

    if zi_disturbed_count >= 2:
        tag = ""
        if zi_has_baihu: tag = "(臨白虎,主出血、血光)"
        elif zi_has_xuanwu: tag = "(臨玄武,主暗病、慢性婦科)"
        elif zi_has_qinglong: tag = "(臨青龍,可能為懷孕或經期變動,偏吉)"
        out.append({
            "level": "凶" if not zi_has_qinglong else "警",
            "text": f"{scope_name}子孫多爻被擾動{tag}({'、'.join(zi_signals)}) — 主婦科、月經有異常，需就醫檢查。"
        })
    elif zi_disturbed_count == 1:
        sig_text = "、".join(zi_signals)
        if zi_has_baihu:
            out.append({
                "level": "凶",
                "text": f"{scope_name}子孫臨白虎被擾動({sig_text}) — 主出血、月經失調、流產風險，需立即就醫。"
            })
        elif zi_has_xuanwu:
            out.append({
                "level": "凶",
                "text": f"{scope_name}子孫臨玄武被擾動({sig_text}) — 主暗病或慢性婦科問題、賀爾蒙失調，需就醫檢查。"
            })
        elif zi_has_qinglong:
            out.append({
                "level": "警",
                "text": f"{scope_name}子孫臨青龍被擾動({sig_text}) — 可能為懷孕徵兆或經期變動(偏吉),但仍需檢查確認。"
            })
        else:
            out.append({
                "level": "警",
                "text": f"{scope_name}子孫被擾動({sig_text}) — 主婦科、月經有異常，需就醫檢查。"
            })

    return zi_disturbed_count


# ============================================================
# 規則 D：動爻變出子孫（女命）
# ============================================================
def _check_female_dong_to_zisun(out, yao_rows, scope_name):
    for y in yao_rows:
        if not y.get("動爻"):
            continue
        dong_out = y.get("動爻出去")
        if not dong_out:
            continue
        if dong_out.get("六親") == "子孫" and dong_out.get("生剋") in ("比和", "生我"):
            ori_liuqin = y.get("六親", "")
            if ori_liuqin == "子孫":
                continue
            dong_ls = normalize_tengshe(y.get("六神", ""))
            if dong_ls == "白虎":
                emit(out, "凶",
                     f"{scope_name}{y['爻序名']}{ori_liuqin}(臨白虎)動化出子孫 — 主出血類婦科症狀，月經異常或流產風險,需立即就醫。",
                     y)
            elif dong_ls == "朱雀":
                emit(out, "警",
                     f"{scope_name}{y['爻序名']}{ori_liuqin}(臨朱雀)動化出子孫 — 主婦科炎症、發炎類問題，需就醫檢查。",
                     y)
            elif dong_ls == "玄武":
                emit(out, "警",
                     f"{scope_name}{y['爻序名']}{ori_liuqin}(臨玄武)動化出子孫 — 主暗病或慢性婦科問題,需檢查。",
                     y)
            else:
                emit(out, "警",
                     f"{scope_name}{y['爻序名']}{ori_liuqin}動爻化出子孫且當令 — 主婦科有事，月經或生殖系統有異常，需就醫檢查。",
                     y)


# ============================================================
# 規則 E：官鬼動 + 六神
# ============================================================
def _check_guan_with_liushen(out, yao_rows, scope_name):
    guan_yaos = hidden.find_by_liuqin(yao_rows, "官鬼")
    for y in guan_yaos:
        guan_ls = normalize_tengshe(y.get("六神", ""))
        if y["動爻"]:
            if guan_ls == "朱雀":
                emit(out, "警", f"{scope_name}官鬼臨朱雀動 — 主發炎、上火、咽喉口腔或心火旺，注意飲食作息。", y)
            elif guan_ls == "騰蛇":
                emit(out, "警", f"{scope_name}官鬼臨騰蛇動 — 主怪病、失眠、心理症狀或神經系統不適。", y)
            elif guan_ls == "白虎":
                emit(out, "凶", f"{scope_name}官鬼臨白虎動 — 主急性病、開刀、外傷,慎防意外。", y)


# ============================================================
# 規則 F：用化鬼、鬼化用、世變鬼【新增】
# ============================================================
def _check_self_change_to_guan(out, shi_yao, scope_name):
    """世爻變鬼 = 最凶"""
    if not shi_yao or not shi_yao.get("動爻"):
        return
    dong_out = shi_yao.get("動爻出去") or {}
    if dong_out.get("六親") == "官鬼":
        out.append({
            "level": "凶",
            "text": f"{scope_name}世爻動化出官鬼 — 主自身轉為憂病之兆，須提防身體狀況惡化或意外。"
        })
    # 化回頭克
    if dong_out.get("生剋") == "剋我":
        out.append({
            "level": "凶",
            "text": f"{scope_name}世爻動化回頭克 — 主自身受傷，健康問題嚴重。"
        })


# ============================================================
# 規則 G：用神過旺反凶【新增】
# ============================================================
def _check_world_overflowing(out, shi_yao, yao_rows, outer_block, scope_name):
    if not shi_yao:
        return
    outer_branch = outer_block.get("地支")
    result = yongshen.check_overflowing(shi_yao, outer_branch, yao_rows)
    if result.get("is_overflowing"):
        out.append({
            "level": "警",
            "text": f"{scope_name}世爻過旺({result['phase']}地，"
                    f"卦中另有{result['evidence_count']}爻同五行支撐) — "
                    f"用神過旺反主健康壓力，提防突發、過勞或暴飲暴食。"
        })


# ============================================================
# 規則 H：官鬼伏神位置 → 病因【新增】
# ============================================================
def _check_guan_hidden_cause(out, yao_rows, scope_name):
    # 卦中已現官鬼則跳過（《增刪卜易》：有現則不看伏）
    if hidden.is_present(yao_rows, "官鬼"):
        return

    hidden_guan = hidden.find_hidden_under(yao_rows, "官鬼")
    cause_map = {
        "父母": "勞力傷神、衣食寒暖失調所致",
        "兄弟": "情緒鬱結、口舌爭執或飲食不振",
        "妻財": "飲食過度或縱慾傷身",
        "子孫": "受驚嚇或孩童相關之病",
    }
    for h in hidden_guan:
        feishen_lq = h["飛神六親"]
        cause = cause_map.get(feishen_lq)
        if cause:
            out.append({
                "level": "中",
                "text": f"{scope_name}官鬼伏於{feishen_lq}之下({h['飛神爻序名']}) — "
                        f"病因可能為{cause}，從此方面留意。"
            })


# ============================================================
# 規則 I：卦宮對應臟腑【新增】
# ============================================================
def _annotate_gong_organs(out, yao_rows, outer_block, scope_name):
    """
    若有明顯的健康警訊（已存在 凶/警 訊號），追加卦宮對應臟腑提示。
    避免每張卦都報，只在有警訊時才補充。
    """
    # 統計目前是否已有 凶/警 訊號
    has_warning = any(s["level"] in ("凶", "警") for s in out)
    if not has_warning:
        return

    # 找受剋或被沖的官鬼，依其爻位給臟腑提示
    guan_yaos = hidden.find_by_liuqin(yao_rows, "官鬼")
    for y in guan_yaos:
        if y["生剋"] == "剋我" or y["合沖"] == "相沖" or y.get("動爻"):
            body = traits.get_yao_body_part(y["index"])
            if body:
                parts_text = "、".join(body["部位"][:3])
                out.append({
                    "level": "中",
                    "text": f"{scope_name}官鬼在{body['位置']}（對應{parts_text}）"
                            f" — 注意相關部位有無異狀。"
                })
                break


# ============================================================
# 規則 J：子孫旬空 + 官鬼旬空 = 不治自愈【新增】
# ============================================================
def _check_zi_guan_both_empty(out, yao_rows, scope_name):
    """
    子孫空 + 官鬼空 = 不治自愈
    注：旬空判斷需日辰旬資訊，此處用「卦中無此六親」近似判定為「該六親不顯」。
    嚴格旬空判定需要傳入日辰旬空資訊，未來可擴充。
    """
    has_guan = hidden.is_present(yao_rows, "官鬼")
    has_zi = hidden.is_present(yao_rows, "子孫")
    if not has_guan and not has_zi:
        out.append({
            "level": "吉",
            "text": f"{scope_name}卦中官鬼、子孫俱不現 — 病無形跡、藥無蹤跡，反主不藥而愈或本無大礙。"
        })


# ============================================================
# 既有規則：官鬼得生 / 官鬼伏神浮出 / 子孫得生
# ============================================================
def _check_legacy_rules(out, yao_rows, aroused_fushen, scope_name,
                        gender, zi_disturbed_count):
    guan_yaos = hidden.find_by_liuqin(yao_rows, "官鬼")
    for y in guan_yaos:
        guan_ls = normalize_tengshe(y.get("六神", ""))
        if y["生剋"] == "生我":
            emit(out, "警", f"{scope_name}官鬼受生而旺 — 主有病災，家中長輩也要留意健康。", y)
        if y["動爻"] and guan_ls not in ("朱雀", "騰蛇", "白虎"):
            emit(out, "警", f"{scope_name}官鬼爻動 — 健康變動，舊疾可能復發。", y)

    for f in aroused_fushen:
        if f["六親"] == "官鬼":
            out.append({"level": "警",
                        "text": f"{scope_name}官鬼伏神浮出 — 舊病可能復發，潛藏的健康問題浮現。"})

    # 子孫得生（女命子孫已擾動時跳過）
    skip_zi_jisheng = (gender == 'F' and zi_disturbed_count >= 1)
    if not skip_zi_jisheng:
        zi_yaos = hidden.find_by_liuqin(yao_rows, "子孫")
        for y in zi_yaos:
            if y["生剋"] == "生我" and not y["動爻"] and not y["合沖"]:
                emit(out, "吉", f"{scope_name}子孫得力 — 有醫療貴人或解病之機。", y)
                break
