# 命果 MINGO(後端 / 網頁)

依京房八宮納甲法 + 野鶴老人《增刪卜易》派的命理排盤系統(原名「命卦排盤」)。
提供:萬年曆(擇日/紫白)、時辰起卦、金錢卦手動排卦、流年分析、四面向判讀、
會員/點數、AI 解讀(串 Claude API)。行動版(功能對等)在另一 repo:`hexagram-app`。

> 開發背景、工作日誌與待辦:**docs/WORKLOG.md**(開新對話先讀這份)。
> 設計系統(web+App 共用):**docs/DESIGN_SYSTEM.md**。

---

## 檔案結構

```
app.py              # Flask 網頁介面（路由）
core_data.py        # 核心常數：八卦、五行、干支、六神、日干支計算
hexagram_data.py    # 64 卦完整資料（卦名、卦辭、卦宮、世應、納甲）
hexagram_engine.py  # 排盤引擎（起卦邏輯 + 手動排卦四面向呼叫）
fortune_engine.py   # 流年排盤引擎（瘦身版，只負責時間軸協調）
fortune_data.py     # 節氣、合沖、三合等資料
db.py               # PostgreSQL(users/point_ledger/divination_questions/growth_reflections)
legal.json          # 個資同意書+免責聲明(單一來源,web 註冊頁與 App 共用)

divination/         # 【新】判讀核心包
├── core/           # 共用核心層（流年、手卦共用）
│   ├── elements.py   # 五行運算、十二長生、三合判定
│   ├── trigger.py    # 動爻引動、對六爻分析、引動伏神
│   ├── hidden.py     # 伏神查詢、用神兩現偵測
│   ├── traits.py     # 卦宮對應臟腑、爻位對應身體部位
│   ├── yongshen.py   # 用神取捨、過旺反凶、動化方向
│   └── signals.py    # 訊號發射、去重、強化條件
│
└── aspects/        # 面向特化層
    ├── love.py       # 感情面（陰陽異性、應爻優先、第三者）
    ├── health.py     # 健康面（久病邏輯、卦宮、爻位、伏神病因）
    ├── work.py       # 工作面（官鬼動化、子孫忌、六神職業）
    └── wealth.py     # 財運面（妻財、兄弟劫財、野鶴五例外）

templates/          # Jinja2 模板
├── base.html         # 母版(側邊欄選單)
├── landing.html      # 首頁
├── almanac.html      # 萬年曆(擇日/紫白)
├── cast.html         # 時辰起卦
├── manual.html       # 卜卦問事(金錢卦擲卦 + AI 解讀)
├── _hexagram_table.html  # 卦象表格(cast/manual/question_detail 共用)
├── register/login/forgot/reset.html   # 會員註冊登入
├── member*.html      # 會員中心(member/history/profile/password/delete…)
└── admin/            # 管理員區(無獨立登入,一般登入+ADMIN_EMAILS 判定)
    ├── history_list.html / history_detail.html
    ├── members.html / questions.html / question_detail.html
    └── fortune.html  # 流年分析(含四面向 + 12 流月)

static/style.css    # 全站樣式(MINGO tokens 在「v2 覆蓋層」的 :root)
```

---

## 執行

```bash
docker compose up -d --build hexagram   # 標準方式(改完程式/模板/prompt 重建上線)
# http://localhost:8080
```

⚠️ **前置相依**:PostgreSQL 來自獨立 compose `/opt/database`(host 名 `postgres`,external 網路
`appnet`),乾淨機器要先啟動它。重開機順序見 `docs/RESUME.md`。(2026-07-12 從舊 finance-apps 抽出。)
主要環境變數(`.env`,參考 `.env.example`):`SECRET_KEY`(必填,弱值拒啟動)、`ADMIN_EMAILS`、
`ANTHROPIC_API_KEY`、`RESEND_API_KEY`、`SESSION_MAX_AGE_HOURS`(預設 24)。

本機開發(不走 Docker):`pip install -r requirements.txt` 後 `python app.py`。

---

## 路由分群(完整清單:`grep "@app.route" app.py`)

| 群 | 路由 |
|----|------|
| 網頁 | `/`(landing)、`/almanac`、`/cast`、`/fortune`、`/manual`(+`/ai_prompt`、`/ai_reading` SSE) |
| 會員 | `/register` `/login` `/logout` `/forgot` `/reset`、`/member`(+history/profile/password/delete) |
| API(App/Web 共用) | `/api/v1/*`:auth、member、chart/cast、almanac、daily、fortune、prompt/reading/chat、reflection、legal、health |
| 管理 | `/admin/history*`、`/admin/members`、`/admin/questions*`(一般 `/login` + `ADMIN_EMAILS` 判定,無獨立管理登入) |

---

## 核心特色

### 一、判讀模組化
所有判讀邏輯抽出到 `divination/` 包，**流年排盤與手動排卦共用同一套判讀**：
- `divination/core/` — 用神、五行、引動、伏神、訊號等共用基礎
- `divination/aspects/` — 四個獨立面向模組

### 二、四面向判讀（依《增刪卜易》《黃金策》）

**感情面**
- 女命主官鬼、男命主妻財、未指定看雙線
- 六神升級：青龍正緣、玄武暗動、白虎衝突、朱雀口舌
- 第三者徵兆（強化條件原則）：動化、合、伏藏、兩現

**健康面**
- 世爻為主用神，配合官鬼（病）、子孫（藥）、父母（壽）
- 十二長生衰旺 + 六神升級（白虎血光、玄武暗病）
- 女命子孫爻婦科訊號
- 卦宮對應臟腑、爻位對應身體部位
- 官鬼伏神位置 → 病因（伏父=勞累、伏兄=情緒、伏財=飲食縱慾）

**工作面**
- 官鬼為主用神，父母為輔（單位、合約）
- 子孫動 / 持世 = 求職升職大忌
- 官鬼六神 → 職業類型（青龍正職、白虎軍警、玄武投機）
- 官鬼動化方向（化進升、化退降、化回頭克）

**財運面**
- 妻財為主用神，兄弟為劫財忌神
- 野鶴五例外：兄弟持世也得財的五種情況
- 兄動喜官動、兄靜忌官動（雙條件）
- 三合兄局、過旺需入墓得財

### 三、Thread-Safe / Process-Safe 設計
所有判讀模組採純函式設計，無模組層級可變狀態：
- 函式只讀 input、回傳新物件
- 訊號累積用 local list
- 同樣的 input 永遠回傳同樣的 output


---

## 起卦規則（時辰起卦）

1. 公曆轉農曆月、日
2. **上卦數** = 農曆日 % 8（0 視為 8）
3. **下卦數** = 農曆月 % 8（0 視為 8）
4. **動爻** = (時辰序號 - 1) % 6（子=1, 丑=2, …, 亥=12）
5. 六神依日干起
6. 六親以本卦卦宮五行為「我」，對各爻地支五行判定
7. 動爻出去六親：變爻後的新地支，對照**原本卦宮五行**的六親

## 換日時間

採 **00:00 換日**（子時分早晚：23:00 仍算當天，00:00 起算下一日）。

## 爻序方向

統一為「由下而上」：`index 0 = 初爻（最下）`，`index 5 = 上爻（最上）`。
顯示時由上而下排列（符合傳統畫法）。

---

## 驗證測試案例

- **1990-08-11 10:00** → 風水渙（離宮五世）、戊申日、上爻動
- **1991-10-28 18:00** → 風天小畜、女命、流年 2026 顯示「官鬼伏於妻財之下 = 夫星藏於他女處」

---

## 效能

| 操作 | 耗時 | 說明 |
|------|------|------|
| 流年分析（含 12 流月、四面向） | ~52 ms | 76% 時間花在 sxtwl 找節氣 |
| 手動排卦四面向 | ~2 ms | 純判讀計算 |

---

## 流年計算規則

- **流年以立春為界**（節氣編號 3）
- **12 個流月以「節」（奇數節氣編號）分界**
- **嚴格三合**：月支必須是帝旺地（子/午/酉/卯），且卦中六爻同時涵蓋同組另外兩個地支
- **嚴格六沖六合卦**（野鶴派）：8 純卦 + 天雷無妄 + 雷天大壯 = 10 六沖；6 個六合卦
- **傳統引動規則 7 種**：動值/動沖/動合/靜值/靜沖/靜合/無事
