# -*- coding: utf-8 -*-
"""
divination.aspects.work — 工作面判讀

主用神：官鬼（職位、上司、工作）；父母為輔（單位、合約、文書）

判讀規則（對齊原版 + 補強傳統規則）：
  1. 官鬼爻 + 六神升級（青龍升遷、騰蛇變故、白虎軍警、玄武投機）
  2. 父母爻 + 六神升級（朱雀文書、勾陳房地產）
  3. 官鬼伏神浮出

  【新增規則】
  4. 子孫動 / 持世 = 求職升職大忌（《增刪卜易》功名章）
  5. 官鬼動化方向（化進升、化退降、化回頭克受傷）
  6. 官鬼六神對應職業類型
  7. 兄弟動 = 競爭
  8. 妻財動克父母 = 不利文書
  9. 用神過旺反凶
"""
from ..core import hidden, yongshen
from ..core.signals import emit, emit_static, dedupe, merge_by_yao, normalize_tengshe


# 官鬼六神 → 職業類型對照
_GUAN_LIUSHEN_PROFESSION = {
    "青龍": "公務員、高雅職務、文化教育類",
    "朱雀": "文書、教育、口才類、媒體",
    "勾陳": "行政、不動產、辦公室類",
    "騰蛇": "技術、工程、需專精的職業",
    "白虎": "軍警、法務、外勤、體力類",
    "玄武": "金融、投機、暗中或機密類業務",
}


def analyze(yao_rows, outer_block, aroused_fushen, scope_name,
            gender=None, is_year_scope=False):
    """
    工作面主分析函式。
    回傳：list of {"level": "吉/中/警/凶", "text": "..."}
    """
    out = []

    guan_yaos = hidden.find_by_liuqin(yao_rows, "官鬼")
    fu_yaos = hidden.find_by_liuqin(yao_rows, "父母")
    zi_yaos = hidden.find_by_liuqin(yao_rows, "子孫")
    xiongdi_yaos = hidden.find_by_liuqin(yao_rows, "兄弟")
    cai_yaos = hidden.find_by_liuqin(yao_rows, "妻財")
    shi_yao = next((r for r in yao_rows if r["世"]), None)
    ying_yao = next((r for r in yao_rows if r["應"]), None)

    # === 主用神取捨（官鬼兩現以上時）===
    guan_primary, guan_secondary, guan_role = yongshen.select_primary(
        guan_yaos, world_yao=shi_yao, response_yao=ying_yao,
        aspect="work", gender=gender
    )
    # === 父母兩現取捨（合約/單位）===
    fu_primary, fu_secondary, fu_role = yongshen.select_primary(
        fu_yaos, world_yao=shi_yao, response_yao=ying_yao,
        aspect="work", gender=gender
    )

    # === 兩現總綱（只在流年顯示）===
    if is_year_scope:
        if len(guan_yaos) >= 2:
            s = yongshen.make_summary_signal("官鬼", guan_yaos,
                                              guan_primary, guan_secondary, guan_role, scope_name)
            if s:
                s = {**s, "text": s["text"] + " 兩官解讀：雙重職務/兼職/主副管/兩個機會,動者為當年事發點。"}
                out.append(s)
        if len(fu_yaos) >= 2:
            s = yongshen.make_summary_signal("父母", fu_yaos,
                                              fu_primary, fu_secondary, fu_role, scope_name)
            if s:
                s = {**s, "text": s["text"] + " 兩父解讀：兩份合約/單位,主卦父母為現任、變卦父母為將去。"}
                out.append(s)

    # === 官鬼爻判讀（主用神）===
    _check_guan(out, guan_yaos, scope_name, is_year_scope,
                primary=guan_primary, secondary=guan_secondary, role_info=guan_role)

    # === 官鬼動化方向【新增】===
    if is_year_scope:
        _check_guan_dong_direction(out, guan_yaos, scope_name)

    # === 官鬼伏神浮出 ===
    for f in aroused_fushen:
        if f["六親"] == "官鬼":
            out.append({"level": "中",
                        "text": f"{scope_name}官鬼伏神浮出 — 浮現新的工作機會或職務變化。"})

    # === 父母爻判讀（輔助）===
    _check_fu(out, fu_yaos, scope_name,
              primary=fu_primary, secondary=fu_secondary, role_info=fu_role)

    # === 子孫動 / 持世 = 求職升職大忌【新增】===
    if is_year_scope:
        _check_zisun_taboo(out, zi_yaos, shi_yao, scope_name)

    # === 兄弟動 = 競爭【新增】===
    _check_xiongdi(out, xiongdi_yaos, scope_name)

    # === 妻財動克父母 = 不利文書【新增】===
    _check_cai_attacks_fu(out, cai_yaos, fu_yaos, scope_name)

    # === 用神過旺反凶【新增】===
    # 只對機兆主用神判斷
    if is_year_scope and guan_primary is not None:
        _check_guan_overflowing(out, [guan_primary], yao_rows, outer_block, scope_name)

    return merge_by_yao(dedupe(out))


# ============================================================
# 官鬼爻判讀
# ============================================================
def _check_guan(out, guan_yaos, scope_name, is_year_scope,
                primary=None, secondary=None, role_info=None):
    role_info = role_info or {}
    for y in guan_yaos:
        sk = y["生剋"]
        hc = y["合沖"]
        ls = normalize_tengshe(y.get("六神", ""))
        tag = yongshen.role_tag(y, primary, secondary, role_info)
        tag_suffix = f" {tag}" if tag else ""

        # 六神升級：騰蛇官鬼動 → 工作不確定
        if y["動爻"] and ls == "騰蛇":
            emit(out, "警", f"{scope_name}官鬼臨騰蛇動{tag_suffix} — 工作有變故、不確定性高，計劃可能臨時生變。", y)

        if sk == "生我":
            if ls == "青龍":
                emit(out, "吉", f"{scope_name}官鬼臨青龍得力{tag_suffix} — 主升遷、貴人提拔、權位提升。", y)
            else:
                emit(out, "吉", f"{scope_name}官鬼得力{tag_suffix} — 主升遷、被重用、權位提升。", y)
        elif sk == "剋我":
            emit(out, "警", f"{scope_name}官鬼受剋{tag_suffix} — 工作上權威受挑戰，上司或職位有變。", y)

        if hc == "相沖":
            emit(out, "警", f"{scope_name}官鬼被沖{tag_suffix} — 職務變動、人事異動。", y)

        # 官鬼六神 → 職業類型（只在流年顯示，避免每月重複）
        if is_year_scope and ls and ls in _GUAN_LIUSHEN_PROFESSION:
            prof = _GUAN_LIUSHEN_PROFESSION[ls]
            emit_static(out, "中",
                        f"{scope_name}官鬼臨{ls}{tag_suffix} — 職業性質傾向：{prof}。", y)
            break  # 一條就夠


# ============================================================
# 官鬼動化方向【新增】
# ============================================================
def _check_guan_dong_direction(out, guan_yaos, scope_name):
    for y in guan_yaos:
        if not y.get("動爻"):
            continue
        direction = yongshen.get_dong_direction(y)
        if direction == "化進神":
            emit_static(out, "吉",
                        f"{scope_name}{y['爻序名']}官鬼動化進神 — 主升職、職位上升、權力擴大。", y)
        elif direction == "化退神":
            emit_static(out, "警",
                        f"{scope_name}{y['爻序名']}官鬼動化退神 — 主降職、職位下降或退步。", y)
        elif direction == "化回頭克":
            emit_static(out, "凶",
                        f"{scope_name}{y['爻序名']}官鬼動化回頭克 — 主工作受損、職務出狀況。", y)
        elif direction == "化回頭生":
            emit_static(out, "吉",
                        f"{scope_name}{y['爻序名']}官鬼動化回頭生 — 主工作穩固、有後援支持。", y)


# ============================================================
# 父母爻判讀
# ============================================================
def _check_fu(out, fu_yaos, scope_name,
              primary=None, secondary=None, role_info=None):
    role_info = role_info or {}
    for y in fu_yaos:
        sk = y["生剋"]
        ls = normalize_tengshe(y.get("六神", ""))
        tag = yongshen.role_tag(y, primary, secondary, role_info)
        tag_suffix = f" {tag}" if tag else ""

        # 六神升級
        if y["動爻"] and ls == "朱雀":
            emit(out, "警", f"{scope_name}父母臨朱雀動{tag_suffix} — 文書、合約、官司糾紛,簽署前務必詳閱。", y)
            continue
        if y["動爻"] and ls == "勾陳":
            emit(out, "中", f"{scope_name}父母臨勾陳動{tag_suffix} — 房產、不動產或長期合約有牽連事。", y)
            continue

        if sk == "生我":
            emit(out, "吉", f"{scope_name}父母得生{tag_suffix} — 文書、合約、考試相關事務順利。", y)
            break  # 一條就夠

    for y in fu_yaos:
        ls = normalize_tengshe(y.get("六神", ""))
        tag = yongshen.role_tag(y, primary, secondary, role_info)
        tag_suffix = f" {tag}" if tag else ""
        if y["合沖"] == "相沖" and not (y["動爻"] and ls == "朱雀"):
            emit(out, "警", f"{scope_name}父母被沖{tag_suffix} — 文書、合約恐有變動或糾紛。", y)
            break


# ============================================================
# 子孫動 / 持世 = 求職升職大忌【新增】
# ============================================================
def _check_zisun_taboo(out, zi_yaos, shi_yao, scope_name):
    """
    《增刪卜易·功名章》：
      「求名切忌子孫持世」、「子孫為克官之神，有職之官而陳奏者，不宜見之」
    """
    # 子孫持世
    if shi_yao and shi_yao.get("六親") == "子孫":
        out.append({
            "level": "警",
            "text": f"{scope_name}子孫持世 — 求職升職之大忌，主無心仕途或職位難求；"
                    f"若已在職，亦防降職或辭職之念。"
        })

    # 子孫動 = 克官
    for y in zi_yaos:
        if y.get("動爻"):
            emit(out, "警",
                 f"{scope_name}{y['爻序名']}子孫動 — 克制官星，主工作有阻、求職難成、升遷受阻。",
                 y)
            break


# ============================================================
# 兄弟動 = 競爭【新增】
# ============================================================
def _check_xiongdi(out, xiongdi_yaos, scope_name):
    for y in xiongdi_yaos:
        if y.get("動爻"):
            emit(out, "警",
                 f"{scope_name}{y['爻序名']}兄弟動 — 工作上有競爭對手或同事爭利，提防小人。",
                 y)
            break


# ============================================================
# 妻財動克父母 = 不利文書【新增】
# ============================================================
def _check_cai_attacks_fu(out, cai_yaos, fu_yaos, scope_name):
    if not fu_yaos:
        return
    for y in cai_yaos:
        if not y.get("動爻"):
            continue
        # 變出去的爻是否是父母的剋星 — 簡化判斷：妻財動本身就會克父母
        out.append({
            "level": "警",
            "text": f"{scope_name}{y['爻序名']}妻財動 — 動則克父母（文書），文書、合約事務恐有變故。"
        })
        break


# ============================================================
# 用神過旺反凶【新增】
# ============================================================
def _check_guan_overflowing(out, guan_yaos, yao_rows, outer_block, scope_name):
    outer_branch = outer_block.get("地支")
    if not outer_branch:
        return
    for y in guan_yaos:
        result = yongshen.check_overflowing(y, outer_branch, yao_rows)
        if result.get("is_overflowing"):
            out.append({
                "level": "警",
                "text": f"{scope_name}官鬼過旺({result['phase']}地，"
                        f"卦中另有{result['evidence_count']}爻支撐) — "
                        f"官星過旺反主壓力過大、職位過重、易遭忌憚。"
            })
            break  # 一條就夠
