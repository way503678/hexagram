# 六爻引擎確定性計算回歸驗證
# 用法(容器內):docker exec -w /app hexagram python /app/tools/validate_classics.py
# 涵蓋:2 日期 × 64 卦 ×(靜/動1/動2/動3 = 42 組合)= 5376 卦
# 以「完全獨立重算」(不 import 引擎 helper、自帶規則表)逐一 assert:
# 旺衰/空亡/真假空/月破/入墓/日沖暗動日破/動化方向(進退神)/反吟/化空墓絕/飛伏生剋/三合半合
# -*- coding: utf-8 -*-
"""64 卦 ×(靜/動1/動2/動3)獨立重算交叉驗證。不 import 引擎 helper,自帶規則表。"""
import sys, itertools, json
sys.path.insert(0, "/app")
import app

ZHI = "子丑寅卯辰巳午未申酉戌亥"
GAN = "甲乙丙丁戊己庚辛壬癸"
BE = {"子":"水","丑":"土","寅":"木","卯":"木","辰":"土","巳":"火","午":"火",
      "未":"土","申":"金","酉":"金","戌":"土","亥":"水"}
# 十二長生長生地(火土同論,與引擎一致):金巳 木亥 水申 火寅 土寅
CS = {"金":"巳","木":"亥","水":"申","火":"寅","土":"寅"}
PH = ["長生","沐浴","冠帶","臨官","帝旺","衰","病","死","墓","絕","胎","養"]
def tphase(ele, br):
    if ele not in CS or br not in ZHI: return ""
    return PH[(ZHI.index(br) - ZHI.index(CS[ele])) % 12]
TIER = {"長生":"旺","臨官":"旺","帝旺":"旺","沐浴":"中","冠帶":"中","衰":"中","養":"中",
        "病":"弱","死":"弱","墓":"弱","絕":"弱","胎":"弱"}
def tier(ele, br): return TIER.get(tphase(ele, br), "")
def wangshuai(ele, mb, db):
    w = {"旺":1,"中":0,"弱":-1}
    s = w.get(tier(ele,mb),0)*2 + w.get(tier(ele,db),0)
    return "旺" if s>=2 else "偏旺" if s==1 else "持平" if s==0 else "偏弱" if s==-1 else "弱"
def chong(br): return ZHI[(ZHI.index(br)+6)%12] if br in ZHI else ""
MU = {"金":"丑","木":"未","水":"辰","火":"戌","土":"戌"}
LIUHE = {"子":"丑","丑":"子","寅":"亥","亥":"寅","卯":"戌","戌":"卯","辰":"酉","酉":"辰","巳":"申","申":"巳","午":"未","未":"午"}
# 旬空:獨立用「60甲子位置→旬→該旬覆蓋的10支→缺2支」
def xunkong(gz):
    g,z = gz[0],gz[1]
    p = next(i for i in range(60) if i%10==GAN.index(g) and i%12==ZHI.index(z))
    start=(p//10)*10
    covered={(start+k)%12 for k in range(10)}
    return sorted([ZHI[i] for i in range(12) if i not in covered], key=lambda x:ZHI.index(x))
# 進退神對照(同五行,地支順進/退一位)
JIN={("亥","子"),("寅","卯"),("巳","午"),("申","酉"),("丑","辰"),("辰","未"),("未","戌"),("戌","丑")}
TUI={("子","亥"),("卯","寅"),("午","巳"),("酉","申"),("辰","丑"),("未","辰"),("戌","未"),("丑","戌")}
def erel(a,b):  # 從 a 看 b
    SHENG={"木":"火","火":"土","土":"金","金":"水","水":"木"}
    KE={"木":"土","土":"水","水":"火","火":"金","金":"木"}
    if a==b: return "比和"
    if SHENG.get(b)==a: return "生我"
    if SHENG.get(a)==b: return "我生"
    if KE.get(b)==a: return "剋我"
    if KE.get(a)==b: return "我剋"
    return ""
def dong_dir(be_e,be_z,bi_e,bi_z):
    r=erel(be_e,bi_e)
    if r=="生我": return "化回頭生"
    if r=="剋我": return "化回頭克"
    if r=="我生": return "化洩"
    if r=="比和":
        if (be_z,bi_z) in JIN: return "化進神"
        if (be_z,bi_z) in TUI: return "化退神"
        if be_z==bi_z: return "化伏吟"
    return ""
FF={"我剋":("伏剋飛","出暴","吉"),"生我":("飛生伏","得長生","吉"),"我生":("伏生飛","洩氣","凶"),"剋我":("飛剋伏","傷身","凶"),"比和":("飛伏比和","比和","吉")}

errors=[]
def chk(cond, tag, detail):
    if not cond: errors.append((tag, detail))

DATES=[("2026","6","19","14"),("2026","11","20","8")]  # 兩個日期廣化月/日
total=0
for dy,dm,dd,dh in DATES:
  for lines in itertools.product([0,1],repeat=6):
    for k in range(4):
      for mv in itertools.combinations(range(6),k):
        mvset=set(mv)
        yv=[f"{lines[i]},{1 if i in mvset else 0}" for i in range(6)]
        data={"y":dy,"m":dm,"d":dd,"h":dh,"yao_vals":yv,"aspect":"all"}
        pl,err=app._compute_chart(data)
        if err:
            chk(False,"compute_err",(yv,err)); continue
        total+=1
        mb=pl["月令"]["地支"]; db=pl["日令"]["地支"]
        gz=pl["卦象"]["日干支"]
        kong=set(xunkong(gz))
        # 月破地支
        chk(pl["月破地支"]==chong(mb),"月破地支",(gz,mb,pl["月破地支"]))
        # 旬空
        chk(set(pl["旬空"])==kong,"旬空",(gz,pl["旬空"],sorted(kong)))
        for e in pl["對六爻"]:
            z=e["地支"]; el=e["五行"]; dong=e.get("動爻")
            # 旺衰
            exp_ws=wangshuai(el,mb,db)
            got_ws=(e.get("旺衰") or {}).get("綜合旺衰")
            chk(got_ws==exp_ws,"旺衰",(gz,z,el,exp_ws,got_ws))
            # 空亡
            chk(bool(e.get("空亡"))==(z in kong),"空亡",(gz,z))
            # 真假空
            if e.get("空亡"):
                exp="假空" if (exp_ws in ("旺","偏旺") or dong) else "真空"
                chk(e.get("空亡性質")==exp,"空亡性質",(gz,z,exp,e.get("空亡性質")))
            # 月破
            chk(bool(e.get("月破"))==(z==chong(mb)),"月破",(gz,z,mb))
            # 入墓
            mu=MU.get(el); exp_rumu=[]
            if mu:
                if z==mu: exp_rumu.append("臨墓")
                if db==mu: exp_rumu.append("日墓")
            chk((e.get("入墓") or [])==exp_rumu,"入墓",(gz,z,el,exp_rumu,e.get("入墓")))
            # 日沖(暗動/日破)
            exp_rc=None
            if (not dong) and z==chong(db):
                exp_rc="暗動" if exp_ws in ("旺","偏旺","持平") else "日破"
            chk(e.get("日沖")==exp_rc,"日沖",(gz,z,exp_rc,e.get("日沖")))
            # 動爻相關
            if dong:
                out=e.get("動爻出去") or {}
                bz=out.get("地支"); bel=out.get("五行")
                if bz and bel:
                    exp_dir=dong_dir(el,z,bel,bz)
                    got_dir=e.get("動化方向")
                    if exp_dir: chk(got_dir==exp_dir,"動化方向",(gz,z,el,bz,bel,exp_dir,got_dir))
                    else: chk(got_dir in (None,"",), "動化方向",(gz,z,exp_dir,got_dir))
                    # 反吟
                    chk(bool(e.get("動化反吟"))==(bz==chong(z)),"反吟",(gz,z,bz))
                    # 化空墓絕
                    exp_h=[]
                    if bz in kong: exp_h.append("化空")
                    bp=tphase(el,bz)
                    if bp=="墓": exp_h.append("化墓")
                    elif bp=="絕": exp_h.append("化絕")
                    chk((e.get("動化變爻狀態") or [])==exp_h,"化空墓絕",(gz,z,el,bz,exp_h,e.get("動化變爻狀態")))
            # 飛伏生剋
            for fu in (e.get("伏神") or []):
                fz=fu.get("地支"); fe=BE.get(fz)
                if fe and e.get("五行"):
                    r=erel(fe,el)
                    exp=FF.get(r)
                    got=fu.get("飛伏生剋")
                    if exp:
                        chk(got and got.get("關係")==exp[0] and got.get("吉凶")==exp[2],"飛伏生剋",(gz,fz,fe,el,exp,got))
        # 三合(獨立重算)
        bset={e["地支"] for e in pl["對六爻"]}
        exp_sh=[]
        for grp,wang in [("申子辰","子"),("寅午戌","午"),("巳酉丑","酉"),("亥卯未","卯")]:
            pres=[z for z in grp if z in bset]
            if len(pres)>=2:
                exp_sh.append((grp,"成局" if len(pres)==3 else "半合(有帝旺)" if wang in pres else "虛拱(待帝旺支)"))
        got_sh=[(s["組"],s["類型"]) for s in pl["三合"]]
        chk(sorted(got_sh)==sorted(exp_sh),"三合",(gz,exp_sh,got_sh))

print(f"驗證卦數: {total}")
print(f"錯誤數: {len(errors)}")
from collections import Counter
c=Counter(t for t,_ in errors)
print("各項錯誤統計:", dict(c) if c else "無")
for t,d in errors[:15]:
    print("  ✗", t, d)
