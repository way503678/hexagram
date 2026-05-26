# -*- coding: utf-8 -*-
"""
divination.core.hidden — 伏神判斷

核心功能：
  - find_hidden_under(yao_rows, target_liuqin):
      找用神（如「官鬼」）的伏神，並回傳所有伏在哪些飛神（六親）之下。
  - is_present(yao_rows, liuqin_type):
      卦中是否現某六親（決定是否要看伏神）。
  - count_yongshen(yao_rows, liuqin_type):
      用神出現幾次（兩現偵測）。

依《增刪卜易》規則：
  - 卦中有現用神 → 看現的；卦中無現用神 → 看伏神。
  - 伏神位置（伏在哪個飛神下）對病因 / 工作壓力來源 / 感情狀態都有暗示。
"""


def is_present(yao_rows, liuqin_type):
    """
    卦中是否現某六親。
    """
    return any(r["六親"] == liuqin_type for r in yao_rows)


def count_yongshen(yao_rows, liuqin_type):
    """
    回傳某六親在卦中出現幾次。
    用於：用神兩現的偵測。
    """
    return sum(1 for r in yao_rows if r["六親"] == liuqin_type)


def find_by_liuqin(yao_rows, liuqin):
    """
    找出本卦中所有指定六親的爻，回傳 entry list。
    """
    return [r for r in yao_rows if r["六親"] == liuqin]


def find_hidden_under(yao_rows, target_liuqin):
    """
    找用神類型 target_liuqin 的伏神，並回傳伏在哪個飛神之下。

    回傳 list：
      [
        {
          "飛神爻序名": "三爻",
          "飛神六親":   "妻財",   # 飛神（本爻本身）的六親
          "飛神地支":   "申",
          "伏神六親":   target_liuqin,
          "伏神地支":   "亥",
          "伏神干支":   "丁亥",
        },
        ...
      ]

    用於：
      - 健康面：官鬼伏在父母下 = 勞累傷神
      - 感情面（女命）：官鬼伏在妻財下 = 夫藏他女處
      - 工作面：官鬼伏在子孫下 = 工作受後輩牽制
    """
    result = []
    for r in yao_rows:
        for f in r.get("伏神", []) or []:
            if f.get("六親") == target_liuqin:
                result.append({
                    "飛神爻序名": r["爻序名"],
                    "飛神六親":   r["六親"],
                    "飛神地支":   r["地支"],
                    "伏神六親":   f["六親"],
                    "伏神地支":   f["地支"],
                    "伏神干支":   f["干支"],
                })
    return result


def find_hidden_signal(aroused_fushen, target_liuqin):
    """
    在「引動伏神」list 中找特定六親的伏神（已被外來地支引動的）。

    參數：
      aroused_fushen: trigger.find_aroused_fushen() 的回傳值
      target_liuqin:  要找的六親類型

    回傳 list：符合 target_liuqin 的伏神 entry
    """
    return [f for f in aroused_fushen if f.get("六親") == target_liuqin]
