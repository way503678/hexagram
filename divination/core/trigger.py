# -*- coding: utf-8 -*-
"""
divination.core.trigger — 動爻引動與外來地支分析

核心功能：
  - analyze_yao_actions(yao_rows, outer_branch):
      對本卦六爻分析「外來地支」的作用（流年地支/流月地支/手卦當值地支）。
  - find_aroused_fushen(yao_rows, outer_branch):
      找出被外來地支引動的伏神。
  - dominant_yaos(yao_rows_with_attendance):
      回傳主導爻（臨值 + 三合）。

「外來地支」是抽象概念，可以是：
  - 流年地支（fortune_engine 用）
  - 流月地支（fortune_engine 用）
  - 手卦的當值地支（hexagram_engine 用，依場景而定）
"""
from core_data import BRANCH_ELEMENT
from fortune_data import branch_relation

from .elements import element_relation, attendance_status
from .signals import normalize_tengshe


def analyze_yao_actions(yao_rows, outer_branch):
    """
    對本卦六爻分析「外來地支」（流年/流月/當值）的作用。

    參數：
      yao_rows:     本卦的爻 list（cast_hexagram 回傳的 r['本卦']['爻']），
                    已含「地支」「五行」「六親」「世」「應」「動爻」「動爻出去地支」等
      outer_branch: 外來地支（單一字串）

    回傳 list（由下而上 6 筆），每筆包含原本資訊 + 對 outer_branch 的分析：
      {
        "index": 0..5, "爻序名": "初爻"..,
        "干支": ..., "地支": ..., "六親": ..., "六神": ...,
        "伏神": [...],
        "生剋": "...", "合沖": "...", "當值": "...",
        "世": bool, "應": bool, "動爻": bool,
        "動爻出去": None 或 {
          "干支": ..., "地支": ..., "六親": ...,
          "生剋": ..., "合沖": ...,
        }
      }
    """
    outer_ele = BRANCH_ELEMENT[outer_branch]
    # 收集卦中六爻全部地支（三合判定要用）
    all_branches = [row["地支"] for row in yao_rows]

    rows = []
    for row in yao_rows:
        yao_branch = row["地支"]
        yao_ele = row["五行"]

        entry = {
            "index":   row["爻序index"],
            "爻序index": row["爻序index"],   # 別名，與原始 cast_hexagram 一致（供 yongshen 等模組使用）
            "爻序名":  row["爻序名"],
            "陰陽":    row.get("陰陽"),       # 陽爻 / 陰爻（供感情面陰陽異性正配判定使用）
            "干支":    row["干支"],
            "地支":    yao_branch,
            "五行":    yao_ele,
            "六親":    row["六親"],
            "六神":    normalize_tengshe(row.get("六神", "")),
            "伏神":    row.get("伏神") or [],
            "生剋":    element_relation(yao_ele, outer_ele),
            "合沖":    branch_relation(yao_branch, outer_branch),
            "當值":    attendance_status(yao_branch, outer_branch, all_branches),
            "世":      row["世"],
            "應":      row["應"],
            "動爻":    row["動爻"],
            "動爻出去": None,
        }

        # 動爻變出去的新地支
        if row.get("動爻") and "動爻出去地支" in row:
            out_branch = row["動爻出去地支"]
            out_ele = row["動爻出去五行"]
            entry["動爻出去"] = {
                "干支":  row["動爻出去干支"],
                "地支":  out_branch,
                "五行":  out_ele,
                "六親":  row["動爻出去六親"],
                "生剋":  element_relation(out_ele, outer_ele),
                "合沖":  branch_relation(out_branch, outer_branch),
            }
        rows.append(entry)
    return rows


def find_aroused_fushen(yao_rows, outer_branch):
    """
    找出被「外來地支」引動的伏神。

    野鶴派：伏神地支 == 當值地支（流年/流月/手卦當值）即被引動。

    回傳 list，每筆：
      {"爻序名": "三爻", "六親": "官鬼", "地支": "亥", "干支": "丁亥"}
    """
    aroused = []
    for row in yao_rows:
        for f in row.get("伏神", []):
            if f["地支"] == outer_branch:
                aroused.append({
                    "爻序名": row["爻序名"],
                    "六親":   f["六親"],
                    "地支":   f["地支"],
                    "干支":   f["干支"],
                })
    return aroused


def dominant_yaos(yao_rows_with_attendance):
    """
    回傳本年/本月的主導爻（臨值 + 三合 的爻）。

    參數：
      yao_rows_with_attendance: 已經由 analyze_yao_actions 處理過的爻 list

    回傳：
      list of dict，每筆含「爻序名」「六親」「地支」「六神」「當值」
      臨值排在三合之前
    """
    result = []
    for r in yao_rows_with_attendance:
        a = r.get("當值", "")
        if a in ("臨值", "三合"):
            result.append({
                "爻序名": r["爻序名"],
                "六親":   r["六親"],
                "地支":   r["地支"],
                "六神":   r.get("六神", ""),
                "當值":   a,
            })
    result.sort(key=lambda r: 0 if r["當值"] == "臨值" else 1)
    return result
