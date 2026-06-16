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


_CN_NUM = "〇一二三四五六七八九十"
_LMONTH = ["", "正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]


def _lunar_day_cn(d):
    """農曆日數字 -> 中文(初一/十五/廿三/三十)。"""
    if d == 10:
        return "初十"
    if d == 20:
        return "二十"
    if d == 30:
        return "三十"
    if d < 10:
        return "初" + _CN_NUM[d]
    if d < 20:
        return "十" + _CN_NUM[d - 10]
    return "廿" + _CN_NUM[d - 20]


def _lunar_month_cn(m, leap):
    """農曆月 -> 中文(閏五月 / 正月)。"""
    return ("閏" if leap else "") + _LMONTH[m] + "月"


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
        "lunar_day_cn": _lunar_day_cn(lunar_d),
        "lunar_month_cn": _lunar_month_cn(lunar_m, is_leap),
        # 月曆每格主標:初一顯示月名,其餘顯示日;
        "lunar_label": _lunar_month_cn(lunar_m, is_leap) if lunar_d == 1 else _lunar_day_cn(lunar_d),
        "year_gz": GAN[yg.tg] + ZHI[yg.dz],
        "month_gz": GAN[mg.tg] + ZHI[mg.dz],
        "day_gz": GAN[dg.tg] + ZHI[dg.dz],
        "shengxiao": SHENGXIAO[yg.dz],
        "jieqi": jq_name,
        "jieqi_time": jq_time,
        "day_zibai": zb,
        "day_zibai_name": ZIBAI_NAMES[zb],
        "擇日": day_zeri(year, month, day),
        "year_zibai": (lambda v: {"n": v, "name": ZIBAI_NAMES[v]})(year_zibai(year)),
    }


# ============================================================
# 擇日(建除十二神 + 神煞,標準公有規則,中性用詞)
# ============================================================
_JIANCHU = ["建", "除", "滿", "平", "定", "執", "破", "危", "成", "收", "開", "閉"]

# 建除各神:(吉凶等級, 宜忌)— 依董公原典 12 月歸納調整
_JIANCHU_INFO = {
    "建": ("凶", "月建日,往亡氣旺;忌出行、嫁娶、動土,小事可用。"),
    "除": ("小吉", "除舊布新;宜祭祀、解除、療病、出行,小事可用。"),
    "滿": ("凶", "天富、天賊;宜納采,忌嫁娶、就醫、動土。"),
    "平": ("凶", "朱雀、勾絞;忌起造、出行、安葬、婚姻、入宅,易招官非口舌。"),
    "定": ("吉", "黃羅、紫檀諸吉;宜嫁娶、開市、入學、上樑、安葬。"),
    "執": ("小吉", "執持;宜造作、立契、捕捉,忌出行、移徙。"),
    "破": ("大凶", "月破日,諸事不宜,惟宜破屋、療病、求醫。"),
    "危": ("小吉", "黃羅、紫檀星臨,多次吉;宜小作、修造,大事仍宜謹慎。"),
    "成": ("大吉", "天喜星臨,成就;宜嫁娶、開市、入學、修造、立業。"),
    "收": ("凶", "朱雀、勾絞、到州;忌出行、安葬、入宅,易招官司。"),
    "開": ("小吉", "開通;宜開市、入學、修造、出行,忌安葬。"),
    "閉": ("凶", "閉塞;宜築堤、埋葬,忌開市、出行、就醫。"),
}

_LEVEL_RANK = {"大凶": 0, "凶": 1, "平": 2, "小吉": 3, "吉": 4, "大吉": 5}

# 三煞:日支三合局 -> 煞方;坐向忌事模板
_SANSHA_OPP = {"東": "西", "南": "北", "西": "東", "北": "南"}


def _sansha_dir(dz):
    if dz in (8, 0, 4):   # 申子辰
        return "南"
    if dz in (2, 6, 10):  # 寅午戌
        return "北"
    if dz in (5, 9, 1):   # 巳酉丑
        return "東"
    return "西"           # 亥卯未


def _tianshe(tg, dz, mdz):
    """天赦日:春戊寅、夏甲午、秋戊申、冬甲子(季別依月建支)。"""
    if mdz in (2, 3, 4):    # 春(寅卯辰月)
        return (tg, dz) == (4, 2)   # 戊寅
    if mdz in (5, 6, 7):    # 夏
        return (tg, dz) == (0, 6)   # 甲午
    if mdz in (8, 9, 10):   # 秋
        return (tg, dz) == (4, 8)   # 戊申
    return (tg, dz) == (0, 0)       # 冬 甲子


def _yuede_gan(mdz):
    """月德天干 index(寅午戌→丙、申子辰→壬、亥卯未→甲、巳酉丑→庚)。"""
    if mdz in (2, 6, 10):
        return 2   # 丙
    if mdz in (8, 0, 4):
        return 8   # 壬
    if mdz in (11, 3, 7):
        return 0   # 甲
    return 6       # 庚


# 往亡日:月序(1=正月/寅月) -> 日支index
_WANGWANG = {1: 2, 2: 5, 3: 8, 4: 11, 5: 3, 6: 6,
             7: 9, 8: 0, 9: 4, 10: 7, 11: 10, 12: 1}


def _wangwang(midx, dz):
    return _WANGWANG.get(midx) == dz


def _sifei(tg, dz, mdz):
    """正四廢:春庚申辛酉、夏壬子癸亥、秋甲寅乙卯、冬丙午丁巳(季依月建支)。"""
    gz = (tg, dz)
    if mdz in (2, 3, 4):    # 春
        return gz in ((6, 8), (7, 9))    # 庚申、辛酉
    if mdz in (5, 6, 7):    # 夏
        return gz in ((8, 0), (9, 11))   # 壬子、癸亥
    if mdz in (8, 9, 10):   # 秋
        return gz in ((0, 2), (1, 3))    # 甲寅、乙卯
    return gz in ((2, 6), (3, 5))        # 冬 丙午、丁巳


def _hongsha(mdz, dz):
    """小紅沙:孟月(寅申巳亥)逢巳、仲月(子午卯酉)逢酉、季月(辰戌丑未)逢丑。
    (依原典:正月平巳=紅沙、五月平酉=紅沙、九月平丑=紅沙)"""
    if mdz in (2, 8, 5, 11):   # 孟
        return dz == 5          # 巳
    if mdz in (0, 6, 3, 9):    # 仲
        return dz == 9          # 酉
    return dz == 1              # 季 丑


def _tianzhuan(tg, dz, mdz):
    """天地轉煞:春乙卯/辛卯、夏丙午/戊午、秋辛酉/癸酉、冬壬子/丙子(季依月建支)。"""
    gz = (tg, dz)
    if mdz in (2, 3, 4):    # 春
        return gz in ((1, 3), (7, 3))    # 乙卯、辛卯
    if mdz in (5, 6, 7):    # 夏
        return gz in ((2, 6), (4, 6))    # 丙午、戊午
    if mdz in (8, 9, 10):   # 秋
        return gz in ((7, 9), (9, 9))    # 辛酉、癸酉
    return gz in ((8, 0), (2, 0))        # 冬 壬子、丙子


# 天德:月序 -> ('g',干index) 或 ('z',支index)
_TIANDE = {1: ("g", 3), 2: ("z", 8), 3: ("g", 8), 4: ("g", 7), 5: ("z", 11),
           6: ("g", 0), 7: ("g", 9), 8: ("z", 2), 9: ("g", 2), 10: ("g", 1),
           11: ("z", 5), 12: ("g", 6)}


def _tiande(midx, tg, dz):
    kind, idx = _TIANDE.get(midx, (None, None))
    if kind == "g":
        return tg == idx
    if kind == "z":
        return dz == idx
    return False


try:
    from divination.donggong_data import DONGGONG
except Exception:
    DONGGONG = {}


def _donggong_level(text):
    """由董公原典判詞文字推吉凶等級(供月曆色標;全文為準)。"""
    if not text:
        return None
    if any(k in text for k in ("大凶", "百事不宜", "百事皆忌", "不宜用事", "諸事不宜")):
        return "大凶"
    if "百事大吉" in text or "大發" in text or "諸吉星" in text:
        return "大吉"
    if "大吉" in text:
        return "大吉"
    if "次吉" in text or "小作" in text or "小事" in text:
        return "小吉"
    if "不宜" in text or "忌" in text:
        return "凶"
    if "宜" in text:
        return "吉"
    return "平"


def day_zeri(year, month, day):
    """單日擇日資料(董公原典判詞 + 建除/神煞 + 三煞/正沖)。"""
    sd = sxtwl.fromSolar(year, month, day)
    dg, mg = sd.getDayGZ(), sd.getMonthGZ()
    tg, dz, mdz = dg.tg, dg.dz, mg.dz

    jc = _JIANCHU[(dz - mdz) % 12]
    base_level, base_text = _JIANCHU_INFO[jc]
    level, text = base_level, base_text
    midx = (mdz - 2) % 12 + 1

    # 偵測神煞
    shen = []
    she = _tianshe(tg, dz, mdz)
    yd = tg == _yuede_gan(mdz)
    td = _tiande(midx, tg, dz)
    sf = _sifei(tg, dz, mdz)
    hs = _hongsha(mdz, dz)
    ww = _wangwang(midx, dz)
    tz = _tianzhuan(tg, dz, mdz)
    if jc == "破":
        shen.append("月破")
    if jc == "建":
        shen.append("月建")
    if jc in ("平", "收"):
        shen.append("朱雀勾絞")
    if ww:
        shen.append("往亡")
    if hs:
        shen.append("小紅沙")
    if sf:
        shen.append("正四廢")
    if tz:
        shen.append("天地轉煞")
    if she:
        shen.append("天赦")
    if yd:
        shen.append("月德")
    if td:
        shen.append("天德")

    # 吉凶優先序:大凶煞 > 吉神 > 凶煞 > 建除基準
    if sf:
        level, text = "大凶", "正四廢日,四時休囚,百事不宜。"
    elif jc == "破":
        level, text = "大凶", "月破日,諸事不宜,惟宜破屋、療病、求醫。"
    elif tz:
        level, text = "凶", "天地轉煞,氣機反逆,諸事不宜。"
    elif she:
        level, text = "大吉", "天赦日,百無禁忌;宜修造、嫁娶、開市、出行、入宅。"
    elif yd:
        level, text = "大吉", "月德,百事大吉。"
    elif td:
        level = "吉"
        text = "天德星臨,逢凶化吉;宜安葬、祈福、出行、見貴。"
    elif hs:
        level, text = "凶", "小紅沙日,易招官非、損財,諸事不宜。"
    elif ww:
        level, text = "凶", "往亡日,忌出行、嫁娶、赴任、求財。"
    # 否則維持建除基準 level/text

    sdir = _sansha_dir(dz)
    opp = _SANSHA_OPP[sdir]
    return {
        "建除": jc,
        "正沖生肖": SHENGXIAO[(dz + 6) % 12],
        "三煞方位": sdir,
        "三煞註": (
            f"三煞在{sdir},{sdir}方忌修造、增建、興工、動土、開井、開池;"
            f"坐{sdir}向{opp}的房子,不宜入宅、安神位、開市、奠基、破土、啟建、上樑、修造。"
        ),
        "神煞": shen,
        "吉凶": level,
        "吉凶分": _LEVEL_RANK[level],
        "宜忌": text,
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
