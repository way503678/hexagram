# -*- coding: utf-8 -*-
"""
divination — 命卦排盤判讀核心包

兩層結構：
  divination.core    共用核心層（用神、五行、引動、伏神、訊號）
  divination.aspects 面向特化層（感情、健康、工作、財運）

設計原則：
  - core 層不知道是流年還是手卦，只負責純粹的判讀邏輯
  - aspects 層呼叫 core 層提供基礎運算，再加上該面向的特化規則
  - fortune_engine 與 hexagram_engine 都呼叫同樣的 aspects 模組
"""
