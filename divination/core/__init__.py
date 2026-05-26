# -*- coding: utf-8 -*-
"""
divination.core — 共用核心層

提供所有面向（aspects）共用的判讀基礎：
  - elements:  五行運算、十二長生、三合判定
  - trigger:   動爻引動、外來地支對六爻分析
  - hidden:    伏神查詢
  - traits:    卦宮對應臟腑、爻位對應身體部位
  - yongshen:  用神取捨、過旺反凶
  - signals:   訊號發射、去重、強化條件、六神語意
"""

from . import elements
from . import trigger
from . import hidden
from . import traits
from . import yongshen
from . import signals
