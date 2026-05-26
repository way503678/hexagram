# -*- coding: utf-8 -*-
"""
divination.aspects — 面向特化層

四個獨立模組，各負責一個面向的判讀規則：
  - love:    感情面（女命主官鬼、男命主妻財、第三者徵兆）
  - health:  健康面（世爻、官鬼、子孫、卦宮、爻位）
  - work:    工作面（官鬼主、父母輔、子孫忌、六神職業）
  - wealth:  財運面（妻財主、兄弟劫財、野鶴五例外）

對外統一介面（每個面向都有 analyze 函式）：

  analyze(yao_rows, outer_block, aroused_fushen, scope_name,
          gender=None, is_year_scope=False)

  yao_rows:        經過 trigger.analyze_yao_actions 處理的爻 list
  outer_block:     含「對世爻」「對世爻合沖」「地支」的 dict
  aroused_fushen:  經過 trigger.find_aroused_fushen 處理的伏神 list
  scope_name:      訊號的時間範圍前綴（如「今年」「正月」）
  gender:          'M' / 'F' / None
  is_year_scope:   True 表示處理流年（會帶出靜態卦面徵兆）

  回傳：list of {"level": "吉/中/警/凶", "text": "..."}
"""
