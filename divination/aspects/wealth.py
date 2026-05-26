# -*- coding: utf-8 -*-
"""
divination.aspects.wealth — 財運面判讀

主用神：妻財
元神：子孫（生財之源）
忌神：兄弟（劫財）
通關：官鬼（制兄保財）

判讀規則（對齊原版 + 補強傳統規則）：
  1. 妻財爻 + 六神升級（青龍正財、玄武偏財）
  2. 兄弟動 → 劫財
  3. 妻財伏神浮出

  【新增規則】
  4. 野鶴五例外：兄弟持世也得財的五種情況
  5. 兄動喜官動、兄靜忌官動（雙條件）
  6. 父母旺動 = 耗財（克子孫，斷財源）
  7. 三合兄局 = 大破財
  8. 六神配妻財 = 財的性質
  9. 六神配兄弟 = 破財方式
  10. 用神過旺反凶 — 多財反覆需入墓才得
"""
from ..core import hidden, yongshen
from ..core.signals import emit, emit_static, dedupe, merge_by_yao, normalize_tengshe


# 妻財六神 → 財的性質
_CAI_LIUSHEN_NATURE = {
    "青龍": "正財、喜慶之財、佳偶之財",
    "朱雀": "口才之財、文書之財、教學之財",
    "勾陳": "不動產之財、農林之財、慢進之財",
    "騰蛇": "技術之財、複雜難得之財",
    "白虎": "武職之財、喪葬之財、意外之財",
    "玄武": "偏財、賭博、投機、暗中收入",
}

# 兄弟六神 → 破財方式
_XIONGDI_LIUSHEN_HARM = {
    "青龍": "喜慶之破費（婚喪喜慶）",
    "朱雀": "口舌爭執之破",
    "勾陳": "田產、官非之破",
    "騰蛇": "怪事、虛驚之破",
    "白虎": "血光、官非、意外之破",
    "玄武": "被偷、被騙、暗中損失",
}


def analyze(yao_rows, outer_block, aroused_fushen, scope_name,
            gender=None, is_year_scope=False):
    """
    財運面主分析函式。
    回傳：list of {"level": "吉/中/警/凶", "text": "..."}
    """
    out = []

    cai_yaos = hidden.find_by_liuqin(yao_rows, "妻財")
    xiongdi_yaos = hidden.find_by_liuqin(yao_rows, "兄弟")
    guan_yaos = hidden.find_by_liuqin(yao_rows, "官鬼")
    fu_yaos = hidden.find_by_liuqin(yao_rows, "父母")
    shi_yao = next((r for r in yao_rows if r["世"]), None)
    ying_yao = next((r for r in yao_rows if r["應"]), None)

    # === 主用神取捨（妻財兩現以上時）===
    primary, secondary, role_info = yongshen.select_primary(
        cai_yaos, world_yao=shi_yao, response_yao=ying_yao,
        aspect="wealth", gender=gender
    )

    # === 兩現總綱（只在流年顯示）===
    if is_year_scope and len(cai_yaos) >= 2:
        summary = yongshen.make_summary_signal(
            "妻財", cai_yaos, primary, secondary, role_info, scope_name
        )
        if summary:
            # 財運面額外解釋：兩財代表主副財源、本副業
            extra = " 兩財解讀：動者/旺者為主財，內卦為本業財，外卦為副業財。"
            summary = {**summary, "text": summary["text"] + extra}
            out.append(summary)

    # === 妻財爻判讀（主用神）===
    _check_cai(out, cai_yaos, scope_name, is_year_scope,
               primary=primary, secondary=secondary, role_info=role_info)

    # === 兄弟動 → 劫財 ===
    _check_xiongdi_jiecai(out, xiongdi_yaos, scope_name)

    # === 妻財伏神浮出 ===
    for f in aroused_fushen:
        if f["六親"] == "妻財":
            out.append({"level": "吉",
                        "text": f"{scope_name}妻財伏神浮出 — 潛藏的財源出現，有機會進財。"})

    # === 野鶴五例外：兄弟持世也得財【新增】===
    if is_year_scope:
        _check_yehe_five_exceptions(out, shi_yao, cai_yaos, scope_name)

    # === 兄動喜官動、兄靜忌官動（雙條件）【新增】===
    if is_year_scope:
        _check_guan_xiong_pairing(out, guan_yaos, xiongdi_yaos, scope_name)

    # === 父母旺動 = 耗財【新增】===
    _check_fu_drains_finance(out, fu_yaos, yao_rows, scope_name)

    # === 三合兄局 = 大破財【新增】===
    if is_year_scope:
        _check_sanhe_xiong(out, xiongdi_yaos, yao_rows, outer_block, scope_name)

    # === 六神配兄弟 = 破財方式【新增】===
    if is_year_scope:
        _annotate_xiongdi_liushen(out, xiongdi_yaos, scope_name)

    # === 用神過旺反凶 — 多財反覆需入墓才得【新增】===
    # 過旺只對機兆主用神判斷（不對每個兩現的爻重複報）
    if is_year_scope and primary is not None:
        _check_cai_overflowing(out, [primary], yao_rows, outer_block, scope_name)

    return merge_by_yao(dedupe(out))


# ============================================================
# 妻財爻判讀
# ============================================================
def _check_cai(out, cai_yaos, scope_name, is_year_scope,
               primary=None, secondary=None, role_info=None):
    cai_liushen_emitted = False  # 限制六神性質訊號只發一次
    role_info = role_info or {}

    for y in cai_yaos:
        sk = y["生剋"]
        hc = y["合沖"]
        ls = normalize_tengshe(y.get("六神", ""))
        tag = yongshen.role_tag(y, primary, secondary, role_info)
        tag_suffix = f" {tag}" if tag else ""

        # 六神升級：青龍妻財得生 = 正財貴人；玄武妻財動 + 被擾 = 暗損
        if sk == "生我" and ls == "青龍":
            emit(out, "吉", f"{scope_name}妻財臨青龍得生{tag_suffix} — 主正財進益、有貴人助財,或喜慶之事帶來收入。", y)
        elif sk == "生我":
            emit(out, "吉", f"{scope_name}妻財得生{tag_suffix} — 財運上升，容易進財。", y)
        elif sk == "剋我":
            emit(out, "警", f"{scope_name}妻財被剋{tag_suffix} — 財運受阻，收入減少。", y)

        if y["動爻"] and ls == "玄武" and (hc in ("相沖", "相合") or sk == "我剋"):
            emit(out, "警", f"{scope_name}妻財臨玄武動且被引動{tag_suffix} — 主暗損、被偷盜、意外損失,慎防詐騙。", y)
        elif hc == "相沖":
            emit(out, "警", f"{scope_name}妻財被沖{tag_suffix} — 財來財去，進財不穩或破財。", y)
        elif hc == "相合":
            emit(out, "中", f"{scope_name}妻財被合{tag_suffix} — 財被合走，主代墊、借出、付款。", y)
        if y["動爻"] and ls != "玄武":
            emit(out, "中", f"{scope_name}妻財爻動{tag_suffix} — 財運有明顯變化（請看動爻變出去的方向）。", y)

        # 妻財六神 → 財的性質（只在流年顯示）
        # 此訊號為靜態類象描述，繞過 emit 的引動判定（避免靜爻被吃掉）
        # 但仍帶 _yao_key 讓 merge_by_yao 能正確聚合到該爻
        if is_year_scope and not cai_liushen_emitted and ls in _CAI_LIUSHEN_NATURE:
            nature = _CAI_LIUSHEN_NATURE[ls]
            emit_static(out, "中",
                        f"{scope_name}妻財臨{ls}{tag_suffix} — 財運性質：{nature}。", y)
            cai_liushen_emitted = True


# ============================================================
# 兄弟動 → 劫財
# ============================================================
def _check_xiongdi_jiecai(out, xiongdi_yaos, scope_name):
    for y in xiongdi_yaos:
        if y["動爻"]:
            emit(out, "警", f"{scope_name}兄弟動 — 劫財徵兆，留意破財或合夥糾紛。", y)
            break


# ============================================================
# 野鶴五例外【新增】
# ============================================================
def _check_yehe_five_exceptions(out, shi_yao, cai_yaos, scope_name):
    """
    《增刪卜易·求財章》野鶴秘論：兄弟持世也得財的五種情況：
      1. 世值月破
      2. 世旬空
      3. 世化墓
      4. 日月作財沖世、克世
      5. 世爻兄弟變出財爻
    """
    if not shi_yao or shi_yao.get("六親") != "兄弟":
        return

    # 第 5 條：世爻兄弟變出財爻（最容易判定）
    if shi_yao.get("動爻"):
        dong_out = shi_yao.get("動爻出去") or {}
        if dong_out.get("六親") == "妻財":
            out.append({
                "level": "吉",
                "text": f"{scope_name}世爻兄弟變出妻財（野鶴五例外） — 雖兄弟持世，仍可得財。"
            })


# ============================================================
# 兄動喜官動、兄靜忌官動（雙條件）【新增】
# ============================================================
def _check_guan_xiong_pairing(out, guan_yaos, xiongdi_yaos, scope_name):
    """
    《增刪卜易》：
      「兄爻發動，喜鬼動以制之」
      「倘兄爻安靜，又不宜鬼動，鬼動反洩財爻之氣也」
    """
    xiong_dong = any(y.get("動爻") for y in xiongdi_yaos)
    guan_dong = any(y.get("動爻") for y in guan_yaos)

    if xiong_dong and guan_dong:
        out.append({
            "level": "吉",
            "text": f"{scope_name}兄弟動且官鬼動 — 官鬼制兄，劫財有解，財運轉吉。"
        })
    elif (not xiong_dong) and guan_dong:
        out.append({
            "level": "警",
            "text": f"{scope_name}兄弟安靜而官鬼動 — 官鬼洩財氣，反不利財運，須節制開銷。"
        })


# ============================================================
# 父母旺動 = 耗財【新增】
# ============================================================
def _check_fu_drains_finance(out, fu_yaos, yao_rows, scope_name):
    """父母克子孫 → 斷財源；卦中無子孫救援時更明顯"""
    has_zi = hidden.is_present(yao_rows, "子孫")

    for y in fu_yaos:
        if not y.get("動爻"):
            continue
        if not has_zi:
            emit(out, "警",
                 f"{scope_name}{y['爻序名']}父母動且卦中無子孫救援 — "
                 f"主投資費用大、開銷繁雜，財源斷絕。",
                 y)
        else:
            emit(out, "中",
                 f"{scope_name}{y['爻序名']}父母動 — 主投資、合約、文書相關開銷增加。",
                 y)
        break  # 一條就夠


# ============================================================
# 三合兄局 = 大破財【新增】
# ============================================================
def _check_sanhe_xiong(out, xiongdi_yaos, yao_rows, outer_block, scope_name):
    """
    若兄弟爻在卦中達 3 個以上 + 流年地支屬同三合圈 → 接近三合兄局
    嚴格判定見 core.elements.is_full_sanhe
    """
    from ..core.elements import is_full_sanhe, get_sanhe_group

    if len(xiongdi_yaos) < 2:
        return

    outer_branch = outer_block.get("地支")
    if not outer_branch:
        return

    xiong_branches = [y["地支"] for y in xiongdi_yaos]
    all_branches = [r["地支"] for r in yao_rows]

    # 流年地支是否與兄弟爻成三合
    if is_full_sanhe(outer_branch, all_branches):
        group = get_sanhe_group(outer_branch)
        # 看三合圈內的兄弟爻數量
        xiong_in_group = [b for b in xiong_branches if b in group]
        if len(xiong_in_group) >= 2:
            out.append({
                "level": "凶",
                "text": f"{scope_name}流年地支{outer_branch}成三合{group}局，"
                        f"且兄弟爻多在局中 — 大破財徵兆，慎防大筆損失。"
            })


# ============================================================
# 六神配兄弟 = 破財方式【新增】
# ============================================================
def _annotate_xiongdi_liushen(out, xiongdi_yaos, scope_name):
    """只在有兄弟動爻時補充破財方式提示"""
    for y in xiongdi_yaos:
        if not y.get("動爻"):
            continue
        ls = normalize_tengshe(y.get("六神", ""))
        if ls in _XIONGDI_LIUSHEN_HARM:
            harm = _XIONGDI_LIUSHEN_HARM[ls]
            emit_static(out, "中",
                        f"{scope_name}兄弟臨{ls}動 — 破財方式可能為：{harm}。", y)
            break  # 一條就夠


# ============================================================
# 用神過旺反凶【新增】
# ============================================================
def _check_cai_overflowing(out, cai_yaos, yao_rows, outer_block, scope_name):
    """
    《黃金策·求財章》：
      「多財反覆，必須墓庫以收藏」
      「卦中財臨日月，謂之太旺，若要求謀遂心，須待財爻入墓」
    """
    outer_branch = outer_block.get("地支")
    if not outer_branch:
        return

    overflowing_count = 0
    for y in cai_yaos:
        result = yongshen.check_overflowing(y, outer_branch, yao_rows)
        if result.get("is_overflowing"):
            overflowing_count += 1

    if overflowing_count >= 1 and len(cai_yaos) >= 2:
        out.append({
            "level": "警",
            "text": f"{scope_name}妻財過旺（多財重疊） — "
                    f"財旺反覆難聚，須待入墓之月（辰戌丑未）方能收得，"
                    f"勿急於求成。"
        })
