# -*- coding: utf-8 -*-
"""
萬年曆 / 紫白飛星(擇日用年月日時紫白)。

依賴 sxtwl(壽星天文曆,引擎已用):提供精確農曆、二十四節氣、干支。
日紫白採三元符頭法(超神接氣):
  順遁(陽遁)錨點:冬至起一白、雨水起七赤、穀雨起四綠
  逆遁(陰遁)錨點:夏至起九紫、處暑起三碧、霜降起六白
  各錨點以「最接近該節氣的甲子日」為符頭,順遁逐日 +1、逆遁逐日 −1。
"""
import calendar as _calendar
from datetime import datetime, timedelta

import sxtwl

GAN = "甲乙丙丁戊己庚辛壬癸"
ZHI = "子丑寅卯辰巳午未申酉戌亥"
SHENGXIAO = "鼠牛虎兔龍蛇馬羊猴雞狗豬"

ZIBAI_NAMES = {
    1: "一白", 2: "二黑", 3: "三碧", 4: "四綠", 5: "五黃",
    6: "六白", 7: "七赤", 8: "八白", 9: "九紫",
}

# sxtwl 節氣編號(0=冬至 起,每 4 個為日紫白三元錨點)
JIEQI_NAMES = [
    "冬至", "小寒", "大寒", "立春", "雨水", "驚蟄", "春分", "清明",
    "穀雨", "立夏", "小滿", "芒種", "夏至", "小暑", "大暑", "立秋",
    "處暑", "白露", "秋分", "寒露", "霜降", "立冬", "小雪", "大雪",
]

# 日紫白錨點:jq 編號 -> (方向 +1順/-1逆, 起始星)
_DAY_ANCHORS = {
    0: (1, 1),   # 冬至 → 一白 順
    4: (1, 7),   # 雨水 → 七赤 順
    8: (1, 4),   # 穀雨 → 四綠 順
    12: (-1, 9), # 夏至 → 九紫 逆
    16: (-1, 3), # 處暑 → 三碧 逆
    20: (-1, 6), # 霜降 → 六白 逆
}


def _norm9(v):
    """把任意整數正規化到 1~9。"""
    return (v - 1) % 9 + 1


def _gz_index(tg, dz):
    """由天干(0-9)地支(0-11)求六十甲子序(0-59)。"""
    for k in range(6):
        cand = tg + 10 * k
        if cand % 12 == dz:
            return cand
    raise ValueError(f"非法干支 tg={tg} dz={dz}")


def _day_gz_index(d):
    """某日的六十甲子序(0-59)。d 為 date/datetime。"""
    sd = sxtwl.fromSolar(d.year, d.month, d.day)
    g = sd.getDayGZ()
    return _gz_index(g.tg, g.dz)


def _nearest_jiazi(d):
    """離日期 d 最近的甲子日(回傳 date)。"""
    g = _day_gz_index(d)
    if g <= 30:
        return d - timedelta(days=g)        # 往前到甲子(超神)
    return d + timedelta(days=60 - g)        # 往後到甲子(接氣)


def day_zibai(d):
    """某日的日紫白(1-9)。d 為 date/datetime。"""
    base = datetime(d.year, d.month, d.day)
    # 在 [d-140, d+20] 內找三元錨點節氣,算出各自符頭(甲子),取符頭 <= d 中最晚者
    best = None  # (符頭date, direction, start)
    for off in range(-140, 21):
        cur = base + timedelta(days=off)
        sd = sxtwl.fromSolar(cur.year, cur.month, cur.day)
        if not sd.hasJieQi():
            continue
        jq = sd.getJieQi()
        if jq not in _DAY_ANCHORS:
            continue
        direction, start = _DAY_ANCHORS[jq]
        fu = _nearest_jiazi(cur)              # 該節氣的符頭甲子
        if fu <= base and (best is None or fu > best[0]):
            best = (fu, direction, start)
    if best is None:
        raise RuntimeError("找不到日紫白錨點")
    fu, direction, start = best
    offset = (base - fu).days
    return _norm9(start + direction * offset)


def year_zibai(year):
    """流年紫白(1-9)。逆行,以 2024 甲辰年=三碧 為錨;以立春分年由呼叫端決定。"""
    return _norm9(3 - (year - 2024))


def month_zibai(year_branch_idx, month_branch_idx):
    """流月紫白(1-9)。
    year_branch_idx:年支(0=子)。month_branch_idx:月支(0=子;正月=寅=2)。
    子午卯酉年正月起八白、辰戌丑未年起五黃、寅申巳亥年起二黑;逐月逆行。
    """
    group = year_branch_idx % 3  # 0:子午卯酉 1:..不直接對應,改用支組
    # 子(0)午(6)卯(3)酉(9) -> 8;辰(4)戌(10)丑(1)未(7) -> 5;寅(2)申(8)巳(5)亥(11) -> 2
    if year_branch_idx in (0, 6, 3, 9):
        start = 8
    elif year_branch_idx in (4, 10, 1, 7):
        start = 5
    else:
        start = 2
    # 正月=寅(支2);月序 0..11 由寅起
    m_from_yin = (month_branch_idx - 2) % 12
    return _norm9(start - m_from_yin)


def _jieqi_time(sd):
    """回傳該日節氣的 (名稱, 'HH:MM');無節氣回 (None, None)。"""
    if not sd.hasJieQi():
        return None, None
    jq = sd.getJieQi()
    name = JIEQI_NAMES[jq] if 0 <= jq < 24 else str(jq)
    try:
        t = sd.getJieQiJD()  # 儒略日(sxtwl 已為北京/台北時)
        frac = (t + 0.5) % 1.0
        total_min = int(frac * 24 * 60)
        hh = (total_min // 60) % 24
        mm = total_min % 60
        return name, f"{hh:02d}:{mm:02d}"
    except Exception:
        return name, None


def day_info(year, month, day):
    """單日萬年曆資料。"""
    sd = sxtwl.fromSolar(year, month, day)
    yg, mg, dg = sd.getYearGZ(), sd.getMonthGZ(), sd.getDayGZ()
    d = datetime(year, month, day)
    jq_name, jq_time = _jieqi_time(sd)
    lunar_m = sd.getLunarMonth()
    lunar_d = sd.getLunarDay()
    is_leap = bool(getattr(sd, "isLunarLeap", lambda: False)())
    zb = day_zibai(d)
    return {
        "solar": f"{year:04d}-{month:02d}-{day:02d}",
        "weekday": d.weekday(),               # 0=週一
        "lunar_month": lunar_m,
        "lunar_day": lunar_d,
        "lunar_leap": is_leap,
        "year_gz": GAN[yg.tg] + ZHI[yg.dz],
        "month_gz": GAN[mg.tg] + ZHI[mg.dz],
        "day_gz": GAN[dg.tg] + ZHI[dg.dz],
        "shengxiao": SHENGXIAO[yg.dz],
        "jieqi": jq_name,
        "jieqi_time": jq_time,
        "day_zibai": zb,
        "day_zibai_name": ZIBAI_NAMES[zb],
        "year_zibai": (lambda v: {"n": v, "name": ZIBAI_NAMES[v]})(year_zibai(year)),
    }


def month_info(year, month):
    """整月萬年曆:每日資料 + 當月節氣摘要(供月曆畫面)。"""
    last = _calendar.monthrange(year, month)[1]
    days = [day_info(year, month, d) for d in range(1, last + 1)]
    jieqi = [
        {"day": int(x["solar"][8:10]), "name": x["jieqi"], "time": x["jieqi_time"]}
        for x in days if x["jieqi"]
    ]
    # 當月第一天的星期(0=週一),供畫面排格
    first_weekday = datetime(year, month, 1).weekday()
    return {
        "year": year,
        "month": month,
        "days_in_month": last,
        "first_weekday": first_weekday,
        "jieqi": jieqi,
        "days": days,
    }
