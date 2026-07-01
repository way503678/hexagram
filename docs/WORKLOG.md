# 命卦排盤專案 — 工作紀錄 / 背景速覽

> **用途**:開新對話時固定先讀這份,快速接上專案背景、已完成事項與待辦。
> **這份是「主檔 / 共用背景」**(專案速覽、prompt 原則、跨平台決策、總待辦)。
> **App 專屬**操作與紀錄(Expo/EAS build、畫面結構、App 待辦)另放
> `/opt/hexagram-app/WORKLOG.md`;接 App 任務時讀那份 + 本檔共用段。
> **維護慣例**:每次做完一批事,把「做了什麼 + 結論」追加到「工作日誌」,並更新「待辦」。

最後更新:2026-06-18

---

## 一、專案速覽

命卦排盤(梅花易數 + 京房八宮納甲,野鶴《增刪卜易》派),分兩個 repo,**改功能時 web + app 都要做、功能要一樣**(兩平台對等原則)。

| repo | 路徑 | 技術 | 說明 |
|------|------|------|------|
| 後端 | `/opt/hexagram` | Flask + PostgreSQL + Docker | 排盤引擎、判讀、會員/登入、AI 解讀、網頁介面 |
| App | `/opt/hexagram-app` | React Native / Expo | web 的對等行動版(iOS / Android / Web) |

- **AI 解讀**:串 Claude API。兩份 prompt 在 `docs/AI_INTERPRETER_MANUAL_PROMPT_v1.md`(手動解卦)、`docs/AI_FORTUNE_PROMPT_v1.md`(流年宜忌)。
- **命理輸出原則**:一律白話、面向大眾、**忠於引擎原意**(不美化、不自創訊號)。
- GitHub:`git@github.com:way503678/hexagram.git`(後端)。

## 二、環境 / 常用指令

```bash
cd /opt/hexagram
docker compose ps                       # 容器狀態(hexagram + hexagram-db-backup)
docker compose up -d --build hexagram   # 改完程式/模板/prompt 後重建上線
# 本機網址 http://localhost:8080  ;容器名 hexagram;埠 8080
```
- **prompt / 模板 / 程式改動後一定要重建容器**才生效(prompt 在程式啟動時載入)。
- 改完 → 重建 → 等 healthy → 驗證 → commit。詳見 skill `deploy-verify`。

## 三、解卦 Prompt 設計原則(已定案,改 prompt 時遵守)

1. **白話只講一次、各段分工不重複**(v1.4 重點):完整白話集中在〇白話總結(4–6 句講透),技術段一~四只給卦理判斷 + 極短點題、不再白話復述,§五 只做 2–4 句收束。**這是最容易出包的地方——放寬「多解釋」時務必同時規定「不重複」**。
2. **誠實但建設地鼓勵**:卦象吉凶**強度照引擎、不淡化不誇大**;只改語氣與收尾——阻力翻成「可留意/可準備/可著力之處」,結尾給正面、賦能的鼓勵。**不是美化卦象**。
3. **依吉凶展開、扣著問題**:越明顯吉/凶就多解釋;每個重點回扣「對你問的這件事代表什麼」,把同一問題講深,不延伸別話題。
4. **空亡/旺衰白話化**:空亡≈時機未到、力量未到位,待出空填實才使得上力。
5. **世應/用神依月令、日令判強弱**:月令=`四柱.月`地支、日令=`四柱.日`地支;月令為主、日令次之。
6. **不下成敗斷言、不代決定、不超出問事**;性別關係詞中性化。
7. **版本表寫在 `===== PROMPT 開始/結束 =====` marker 之外**(不會被送進 AI);loader 只認「獨立成行」的 marker。

## 四、工作日誌(新到舊)

### 2026-07-01 — 解讀 prompt v2.1:象內講白(調直白度)
- 使用者回饋 v2.0 教練腔過軟,沒正面回答「合不合/決定好壞/後續會不會有問題」;要「在卦象顯示的範圍內講直白」。
- **prompt v2.1**(`AI_INTERPRETER_MANUAL_PROMPT_v1.md`):§四 新增「**象內講白**」強制原則(卦顯示範圍內講直講白、針對在意面向具體正面答、別用「或許/可能有一點」稀釋清楚的象);§三之二【為什麼是這一卦】【可能的發展】改「卦有顯示就直接講、不迴避」。**界線不變**:不下絕對成敗斷言、不代決定(傾向可講、絕對結論不可),象外/不確定才保守。
- **醫療特例**:健康/醫療/手術/法律/大錢——留意點照講但格外不下好壞判決 + 收尾強調「卦看不了醫療專業、以醫師判斷為準、記得追蹤」。
- 驗證:loader 擷取確認新內容進 prompt、版本表未外洩;重建後容器內 `_MANUAL_AI_PROMPT` 含「象內講白」。**未改引擎/命理判讀規則(§一~§五)**,只改語氣直白度。

### 2026-06-30 — 架構體檢 + 兩項優化(SECRET_KEY fail-fast、style.css 雙 :root 清理)
- **架構體檢**(診斷,見當時對話):核心引擎與安全基本面紮實(扣點原子 `UPDATE…WHERE balance>=`、SQL 全參數化、AI 問題截斷 500、pbkdf2、登入鎖定)。主要債在可維護性:app.py 2691 行單檔、style.css 雙 :root、模板 inline style 多、無 DB 連線池、扣退點/登入檢查重複、無 rate limit。
- **#1 SECRET_KEY fail-fast**(app.py:45):原本 `os.environ.get("SECRET_KEY", "change-this-…")` 有弱預設,.env 掉了會默默用弱值 → token 可偽造。改成偵測「未設或已知弱值(含 docker-compose 的 `please-change-me-…`)就 `raise RuntimeError` 拒絕啟動」。production 實際有 64 字元真 key(docker-compose 從 .env 透傳),不受影響;已驗證真 key 放行、弱/空 key 被擋。
- **style.css 雙 :root 清理**:檔頭原有一份 v1 `:root`(7-26)被後面「v2 覆蓋層」(line 1322)蓋掉 → 改色易只改到死的那層(本人踩過)。把 v1 獨有的功能色 `--moving`/`--danger` 搬進 v2,刪掉整個 v1 區塊,改放指路註解。現在只剩單一 :root(v2)。驗證:線上單一 :root、主色/功能色都在、容器 healthy。

### 2026-06-29 — 個資/免責條文改單一來源(legal.json,web+App 共用)
- 目標:條文只存一處,改一次兩平台同步(原本 web `register.html` 寫死 + App `legal.ts` 各一份手動維護)。
- **單一來源 `legal.json`**(repo 根):`{version, documents:[{key,title,body[],agree}]}`(privacy/disclaimer)。
- **後端 `app.py`**:啟動 `LEGAL = json.load(legal.json)`,`CONSENT_VERSION` 從它來;新增 `GET /api/v1/legal` 回整份;`register_page` 兩處 render 傳 `legal=LEGAL["documents"]`。
- **`register.html`**:兩個寫死的同意框 → `{% for doc in legal %}` 迴圈渲染(checkbox `name="agree_{{doc.key}}"`,維持 agree_privacy/agree_disclaimer)。
- **⚠️ Dockerfile 踩雷**:只 COPY `*.py`/templates/static/docs,根目錄的 `legal.json` 沒被複製 → 容器 `FileNotFoundError` 啟動失敗。**加 `COPY legal.json ./`** 修正。教訓:加根目錄非 .py 的執行期檔案,要同步加 Dockerfile COPY。
- **App 對等**(見 App WORKLOG):`api.ts fetchLegal()` 抓 `/api/v1/legal` + 本地快取;`WelcomeScreen` 改用抓到的條文;**刪除 `src/legal.ts`**(不再有第二份)。
- 驗證:`/api/v1/legal` 回 version+2 docs、register 頁 2 個 consent-title。**改條文今後只改 `legal.json`**。

### 2026-06-29 — hamburger 置中 + 移除卦辭裝飾星號(截圖確認)
- **手機版 hamburger `☰` 偏右沒置中** → `.hamburger` 加 `display:flex/align/justify/padding:0/line-height:1`(手機 `display:block`→`flex`)。截圖確認已置中。桌面版本就隱藏(有 sidebar),不受影響。
- **本卦↔卦辭之間的金色星號 `✦`**(v2 `.guaci::before content:"✦"`,純裝飾)→ 移除該規則。手機版回到原本低調的金色細線分隔(`@media` 內 `.guaci::before` 30px 線),桌面則無裝飾。

### 2026-06-29 — 會員中心點數限 5 筆 + 跑版修正(實機截圖檢視)
- **點數紀錄限 5 筆**:member 路由 `db.list_ledger(user["id"], limit=5)`(完整在「我的紀錄」)。
- **用 playwright + chromium 實際開網頁截圖檢視**(桌面 1280 + 手機 390,公開頁 + 註冊登入後 member/history),逐頁看跑版:
  - **修:會員中心長 email 橫向溢出撐破卡片** → 會員資訊 div 加 `overflow-wrap:anywhere`(手機已驗證會換行)。
  - **修:模板內嵌舊 theme 色沒跟著換**(11 模板共 ~26 處 `#5E548E` 等)→ sed 全域換成 `var(--primary/--accent/--gold/--primary-dark)`(模板都 extends base.html,以後換色自動跟)。命理功能色不動。
  - 其餘頁(landing/login/register/almanac/manual/history)桌機手機皆正常;cast 六爻表手機偏擠但有「左右滑動」提示,屬半刻意,暫不動。
- 截圖工具裝在 scratchpad(非專案),事後已清(playwright+chromium ~664MB);臨時測試帳號 `ptest_*@example.com`(4 個,id 100-103)及其 ledger 已從 DB 刪除,真實帳號未動。

### 2026-06-29 — 首頁設計規範換色(配色/風格/排版,兩平台)
- 使用者提供「命果 設計規範」HTML 稿,套**配色+風格+排版**(中文字體不動、latin 載 Cormorant),App+web 一起。tab/結構不動,只換視覺。
- **Web `static/style.css`**:**注意有兩層 `:root`**——line 7 原始層 + line ~1318「MINGO v2 覆蓋層」,**v2 那層才真正生效**(會蓋掉前者),兩層都要改。全部對齊:`--primary #6F5E9B`、`--accent #8A79B3`、`--gold #E9B34A`、`--bg-light #F1E9DC`、`--text #2C2942`、漸層/陰影/圓角(lg 26)同步;body 背景改暖米線性漸層(`#F5EFE4→#E9E0D2`)+ 一抹頂部微光金,桌面與 `@media` 手機版都改;殘留硬編舊色(remark 中性 `#8E8AA3`、reset 鈕灰紫、側欄品牌白)一併清。grep 確認 0 殘留。
- **`base.html`**:加 Google Fonts `<link>` 載 Cormorant Garamond 500;CSS `.brand-en/.landing-wordmark/.landing-subtitle-en` 走 Cormorant(中文維持思源黑體)。
- **`DESIGN_SYSTEM.md`**:基準文件色票/漸層/圓角/陰影/字體段全面更新為新規範。
- 已 build 上線、curl 驗證(新色就位、舊色歸 0、Cormorant link 在)。App 對等見 App WORKLOG 0d。
- **教訓**:style.css 有 v2 覆蓋層,只改第一層 `:root` 不會生效;改色要先 grep 找出**所有硬編色**+ 確認生效的是哪層。

### 2026-06-28(晚)— landing 去詩句 + App 啟動流程重整
- **Web `templates/landing.html`**:刪除整段 `landing-main` 詩句(明日何如/舉杯邀月/所往者…),落地頁只留 wordmark + slogan(對齊 App「只有 logo+slogan」)。
- **App**(詳見 App WORKLOG 0c):落地頁只留 logo+slogan、首次彈同意 Modal(按一次不再顯示)、同意後才出登入/註冊入口;已登入直接進主頁、主頁今日黃曆卡 — 後三項本就滿足。

### 2026-06-28(下午)— 解卦改人生教練式(Mingo 1.0)
- **理念**:Mingo 不當算命老師,當「懂易經的人生教練」——不給答案,陪使用者從迷惘走向行動。守兩條鐵線:**強度照實、不代做決定**。
- **Phase 1 完成(prompt + 兩平台渲染)**:
  - prompt **v2.0**(`AI_INTERPRETER_MANUAL_PROMPT_v1.md`):命理判讀規則(§一~§五)不動,只把 §三 原 6 段改成「內部判讀依據」,新增 §三之二 **Mingo 1.0 輸出格式**:【一句話】【現在的你】【這一卦在說】【為什麼是這一卦】【可以怎麼做(今/週/月)】【可能的發展】【易經原文(收合)】【深入理論(收合)】【陪你一句】。先講人再講卦、漸進揭露、術語只進【深入理論】;§六 加【可以怎麼做】界線(只能釐清/準備型、不可代決定)。端到端實測(離職占)九段齊全。
  - **Web**:`manual.html` 解讀完成後 `renderMingo()` 依【標記】分段渲染(一句話=亮紫卡、陪你一句=金、原文/理論=`<details>` 收合);`style.css` 加 `.mingo-*`。
  - **App 對等**:新增後端 `POST /api/v1/reading`(非串流即時解讀,扣 1 點失敗退點);App `components/MingoReading.tsx` 同邏輯渲染,CastScreen 主按鈕「✨ 命果為你解讀」,複製 Prompt 降為次要。
- **Phase 2 完成 — Chat CTA**:解讀後「繼續聊」。後端 `POST /api/v1/chat`(多輪、帶卦象+先前解讀上下文、每則扣 `CHAT_AI_COST` 點失敗退點、守不代決定);Web 解讀 modal 加泡泡對話、App `MingoChat` 對等。
- **Phase 3 完成 — 🌱成長反思 + 回訪**:
  - DB:`growth_reflections` 表(feeling/goal/remind_at/status/reminded_at)+ `db.create_reflection / list_due_reflections / mark_reflection_reviewed / list_reminders_to_send / mark_reflection_reminded`。
  - 後端:`POST /api/v1/reflection`(最有感一句 → AI `_craft_growth_goal` 生本週小事,**免費**,remind_at=+7天)、`GET /api/v1/reflections/due`、`POST /api/v1/reflection/done`、`POST /api/v1/reflections/dispatch_reminders`(寄 Email 回訪,授權:管理員或 `X-Cron-Token`=env `CRON_TOKEN`)。
  - 前端:Web 解讀 modal 加 🌱 反思捕捉;會員中心顯示「上週你給自己的小事」到期回訪卡(可「我回顧過了」)。App:CastScreen `MingoReflect`、MemberScreen 到期回訪卡,均對等。
  - **回訪管道**:站內(會員中心,已可用,零外部依賴)+ Email(Resend,需設 `CRON_TOKEN` 並由每日排程 curl 打 dispatch 端點;站內不受影響)。推播留待之後做推播時一起。

### 2026-06-28
- **改名「命果 MINGO」+ 全面換膚(MINGO 設計系統)**。使用者提供 MINGO 規格書,決議:全面改名、先換視覺(新功能後議)、App+Web 一起做、舊風格廢除。
  - **基準文件**:新增 `docs/DESIGN_SYSTEM.md`(色票/圓角/字體/元件,單一真實來源);記憶 `mingo-design.md`。設計語言:低飽和紫(primary `#5E548E`、accent 亮紫 `#A78BFA`、primaryDark `#2B2D42`)+ 米白 `#F7F4EE` + 金黃 `#F6BD60`、大圓角、柔和陰影、紫色漸層。
  - **舊風格廢除**:Web 朱紅水墨(`#8b0000`/宣紙/印章/朱砂)、App 舊紫米色票全部移除。**命理功能色保留**(五行/世應/吉凶綠紅/動爻紅/凶警紅)——CSS 用 `--moving`/`--danger` token 還原被誤轉的功能紅。
  - **Web**:`static/style.css` 加 `:root` MINGO tokens,sed 全域換品牌色(紫),sidebar 深紫、按鈕大圓角 pill、form 加柔和陰影;`base.html`/landing/所有模板標題改「命果 MINGO」,landing 改 wordmark + 標語「看懂變化・走向更好的自己」。email 主旨改名。各頁 200 OK。
  - **App**(見 App WORKLOG):theme.ts MINGO tokens、共用元件 ui.tsx、首頁重做、改名 app.json。
  - **待辦(第二階段新功能)**:AI 問答 tab、今日指引詳情頁(接 analyze_daily)、探索頁、tab 改 首頁/探索/指引/記錄/我的。各內頁(member/cast/admin)細部漸層卡可再精修。

### 2026-06-23
- **寄信加 Resend API 後端**。`_send_mail` 改成:設了 `RESEND_API_KEY` 就走 Resend HTTP API(`_send_via_resend`,stdlib urllib、無新套件),否則自動退回原本 SMTP;兩者皆無則只寫 log。向下相容(舊 SMTP 設定不受影響)。
  - **踩雷**:urllib 預設 UA 被 Cloudflare 擋(error 1010 / HTTP 403)→ 加 `User-Agent: hexagram-mailer/1.0` 後正常打到 Resend(假金鑰回乾淨的 401 JSON)。
  - docker-compose 加 `RESEND_API_KEY` 環境變數透傳。
  - **上線設定**:`.env` 填 `RESEND_API_KEY=re_...` + `MAIL_FROM=命卦排盤 <noreply@已驗證網域>`;Resend 後台驗證網域並到 DNS 設 SPF/DKIM/DMARC。或零改程式走 Resend SMTP(SMTP_HOST=smtp.resend.com / USER=resend / PASS=API key)。

### 2026-06-22
- **每日運勢 MVP(六爻終身卦流日)**(`5fd3151`)。會員中心「我的命盤」下加「今日運勢」卡——命卦對今日干支算運勢與可能問題。**純引擎、零 AI、零 token、0.4ms 可快取**。
  - **命理定位(查證後)**:六爻有「終身卦排運/流日」傳統,以世爻為軸、日辰為一日主宰、生扶=順刑沖克害=逆、用神旺衰定吉凶。**雖非野鶴一事一占(屬李洪成系),使用者接受**;誠實標「每日參考、非鐵口」。判斷標準明確可程式化(同我們驗證過的生克/旺衰那套)。
  - engine `analyze_daily(命卦, 今日)`:重用流年同套機制(`analyze_yao_actions` + 旺衰)縮到日;算世爻今日旺衰+日辰對世(生/剋/沖/合)+各六親被日辰沖剋的面向+六神性質 → 白話總評與提醒。
  - **純白話化**(本次):使用者要求「白話文解釋,不需要任何原文/術語」。輸出全改口語——拿掉世爻/六親/地支/五行/日辰/干支/旺衰/卦名等術語;回傳結構改為 `{日期, 整體狀態, 今日提醒[], 面向提醒[], 定位}`(術語只留在 `_debug` 內部欄位,不顯示)。`_LIUQIN_ASPECT` 改白話(錢財/工作壓力人際是非/長輩文件車房/健康心情/朋友同輩花費)。member.html 卡片同步移除「本命星(世爻)/今日干支/命卦」標籤,只剩日期+白話。
  - **待辦:App 端對等**(兩平台原則)——RN 會員中心加同樣的今日運勢卡(後端可開 `/api` 端點吐 analyze_daily 結果)。

### 2026-06-20
- **解讀模型最終 = Sonnet 4.6**(先 →Opus `6a82acb`,評估後又改回 `a35513d`)。脈絡:對打發現 Opus 在「AI 自推」項(元神、世應生剋)較準,一度切 Opus;**但接著把那些自推項全搬進引擎(元神查找表 v1.19、世應生剋對世欄位 v1.20+回歸測試),下游已不靠 model**;再做「取用神」專項對打(6 刁鑽題)→ **Sonnet 6/6 = Opus 6/6 平手**。結論:準確度兩者等同,差別只剩文筆精煉度(Opus 略佳)vs 成本(Sonnet 省約 4 成)→ 改回 Sonnet。`_AI_READING_MODEL` 預設 sonnet-4-6(env `AI_READING_MODEL` 可覆寫,要頂規文筆隨時切回 opus-4-8)。
- **元神 BUG 修正**(`e672a27`,prompt v1.19):batch12 讓 AI 用六親生剋鏈自推元神/忌神,兩 model 都把五行生剋與六親搞混(元神幾乎全錯)→ 改**固定查找表**(用神→元/忌/仇神),兩 model 皆修正。
- **世應生剋搬引擎(治本)**(`b8d960e`,prompt v1.20):§四「用神對世、世應之間」原 AI 自推(Sonnet 會把方向寫反)→ 引擎算 `對六爻[].對世`(生世/剋世/世生/世剋+合世/沖世),AI 只讀;**納入 validate_classics.py,5376 卦含對世獨立重算 0 錯**。至此 §四 無 AI 自推。
- **教訓 7**:回歸測試只驗「引擎確定性欄位」,測不到「AI 自推」的錯(元神 BUG 在 AI 推理層)。**準確度的治本 = 把所有「AI 自算生剋/關係」搬進引擎 + 納入 0-token 回歸測試**。目前確定性命理計算(旺衰/空亡/月破/入墓/飛伏/進退/化空墓絕/三合/應期/對世)全部引擎算且回歸證明;**剩下唯一的 AI 判斷是「取用神(哪個六親配這問題)」**——本質需理解問句、無法完全去除,靠規則表 + Opus 降風險。

### 2026-06-19
- **原典法則彙編 workflow + 分批落地**(進行中)。多代理 workflow(35 代理/170萬 token/查原典+讀引擎碼)產出 `docs/CLASSICS_RULES.md`(確定性法則/判讀原則/各占類斷法 + 引擎現況 + 優先序)。`87c091b`
  - **batch 1**(`6424d2a`):修進神/退神 BUG——`get_dong_direction` 舊版用「比和→進、洩氣→退」且依賴「變爻vs日辰」的生剋,改為自足「本爻vs變爻」五行+地支對照表;單測 9 案全過。
  - **batch 2**(`085dbea`):加月破偵測(月支對沖)+ prompt 白話。
  - **batch 3-6**(`caf8b31`):真空/假空、暗動/日破、入墓(臨墓/日墓)、動化方向(批1修正版暴露)+爻反吟。**注意**:入墓墓庫表須與引擎十二長生一致(土寄火墓戌,非水土辰),否則與旺衰矛盾——已對齊。
  - **batch 7**(`684e787`):prompt §5.1.1 占類反例(久病六沖凶/占產六沖反吉/行人化進不歸)+ §5.1.2 各占類補充。
  - **batch 8**(`6ce5faf`):應期引擎 `_yingqi_candidates`(依空/破/墓/動/靜給應期候選日)。
  - **batch 9**(`6168294`,prompt v1.15):卦變總論明示讀取(引擎本就完整)+ 六親持世訣 + 占類限制誠實告知(胎爻/天時/三刑)。
  - **batch 10**(`5c7a683`,v1.16):化空/化墓/化絕(完成動化狀態機)。
  - **batch 11**(`ecee1d3`,v1.17):三合半合/虛拱偵測(待補支供應期)。
  - **payload 新欄位總覽**(AI 只讀不自算):頂層 `月令/日令/月破地支/三合`;每爻 `旺衰/空亡/空亡性質/月破/入墓/日沖/動化方向/動化反吟/動化變爻狀態/應期候選`;伏神 `五行/旺衰/飛伏生剋/空亡/月破`;`卦象.卦變總論`(引擎原有)。對應 prompt v1.10~v1.17。
  - **刻意未做(判斷後 defer)**:合處逢沖/沖中逢合(需合源+沖源雙偵測,邊際)、卦反吟(需八宮對沖卦序表,爻反吟已做)、旺相休囚死獨立五態(現五級旺衰已堪用)、三刑引擎化(野鶴實證驗少、易過度斷凶,故只在 prompt 保守註記)。胎爻(系統無此概念,已誠實告知不斷有無孕)。
  - **batch 12(神煞 + JSON 瘦身)**(`f60b28a`,prompt v1.18):神煞(元神/忌神/仇神,相對世爻)從本卦爻併入 `對六爻[].神煞對世`;§二 加「元神/忌神/仇神」判讀(六親生剋鏈固定取,讀其旺衰/動靜判用神後援與阻力)。`_slim_payload_for_ai`:送 AI 的 JSON 砍掉與對六爻重複的本卦/變卦爻陣列+顯示欄位(user_text 3452→2120 token,省 ~39%),**網頁用完整 payload 不動**。實測 AI 正確用元神/忌神判讀(妻財→元神子孫偏弱=後援不足、忌神兄弟偏旺=阻力明確)。
    - **成本實測(Sonnet 4.6)**:引擎算卦 0.41ms/0 token;AI 解讀 input~17k(system 13.7k 可快取+user 瘦身後~2.1k)、output~1.8k;每篇約 US$0.04(熱快取)~$0.09(冷)。瘦身省 input 但 output 才是大頭(占⅔)。
  - **大量驗證(2026-06-20)**:`tools/validate_classics.py`——完全獨立重算(不 import 引擎 helper、自帶規則表),**2 日期 × 64 卦 ×(靜/動1/動2/動3 = 42 組合)= 5376 卦,全部通過、0 錯誤**。覆蓋率證明非空轉:進神512/退神512、飛伏四象全覆蓋、化空2048/化墓1024/化絕1232、真假空/暗動日破/月破/入墓/三合成局半合虛拱 各觸發數百~數千次。9 項確定性計算全部與獨立重算一致。
  - **教訓 6**:驗證要「獨立重算」(自帶規則表、不調被測程式的 helper)才有意義,並用覆蓋率統計證明每個分支真的被觸發(避免 assert 空轉假通過)。
  - **教訓 5**:workflow schema 的 property key 必須 ASCII(中文 key 會 400);大研究任務值得用多代理 workflow,但命理規則仍須逐項人工複核(如本次 BUG 是讀碼才確認)。
- **prompt v1.11:查黃金策原典後補**(`39b6a2c`)。使用者提醒去查增刪卜易/黃金策原典(增刪卜易=野鶴的書)。查《黃金策總斷千金賦》得:「**空逢沖而有用**」(空亡逢沖起用)、「**用爻重疊,喜墓庫之收藏**」(兩現喜入墓)、「**空下伏神易於引拔/伏無提拔終徒爾,飛不推開亦枉然**」(印證 v1.10 伏神能出/難出規則正確)。據此 §二空亡加逢沖、兩現加逢墓、伏神補原典依據。**仍不寫**無原文者:兩現取空者、先看日月代用神。
  - **教訓 4**:命理規則的源頭是**黃金策(千金賦)→ 卜筮正宗 / 增刪卜易**;增刪卜易=野鶴老人著。查原典比查二手部落格可靠。
- **伏神/用神兩現補強 + 引擎算飛伏生剋(v1.10)**(`02201f8`)。查證多源(百度知道/知乎/易师汇)確認**飛伏四象**:伏剋飛=出暴(吉)、飛生伏=得長生(吉)、伏生飛=洩氣(凶)、飛剋伏=傷身(凶)。**引擎** `_fei_fu_relation()` + 伏神旺衰:payload `對六爻[].伏神` 補五行/旺衰/飛伏生剋,AI 只讀不自算。**prompt** §一/§5.1 加「伏神判讀」(四象吉凶+能出/難出條件);兩現補「動>旺(增刪原文)、空爻待出空應事」。
  - **教訓 3**:**改命理規則前先用多源交叉驗證**——這次先前引的易师汇摘要把「伏剋飛」誤寫成「受制」,多源比對才發現正解是「出暴=吉」,差點寫錯進引擎。
  - 保守:兩現「舍不空用旬空」、「先看日月代用神」無乾淨原文,不寫硬規則。
- **prompt v1.9:對照網路權威來源補強六親類象**(`5b1835c`)。對照 CSDN(六親意象)、加拿大風水網(用神原則):主表加「感情/婚姻:男占→妻財、女占→官鬼」;新增「六親類象速查表」(官鬼+上司/盜賊/鬼神、子孫+醫藥/學生/緝盜、妻財+員工/貨物、父母+工作單位/信件/雨具、兄弟+劫財/阻隔)。**對照結論:本地失物/疾病/出行 比簡化網表更細緻,維持不動**;只擴充類象廣度。
- **prompt v1.8:取用神易混消歧表 + 考試分流 + 出行**(`99cfb81`)。§5.1 加「常見易混消歧表」(買/賣/租/修、借錢/合夥、健康、官非/失物/尋人)。**考試分流**:國家考試/公職(求官職)→官鬼、證照/技能檢定→父母。**出行**:查網(增刪卜易派)後定為 世爻=用神、應爻=目的地、子孫=平安吉助、父母=車船行李、妻財=旅費。實測公務員高考→官鬼、證照→父母、開車出行→世爻,全對。
- **prompt v1.7:修取用神消歧**(`91e970a`)。使用者回報「購買汽車」被誤取妻財。病因:取用神表「買賣→妻財」與「車輛→父母」兩條撞車,AI 看到「買」就取妻財。修法:「買賣」限定為**買賣求利**、車輛/房屋標明含**自用購買**、加鐵則「**買自用物取『物』為用神(車/船/房/文書→父母),只有買來轉賣求利才取妻財**」。實測「買車自用」已正確取父母。
- **旺衰改由引擎算 + prompt v1.5/v1.6**(`d4025e3`、`e3722b3`)。
  - **後端 `_yao_wangshuai()`**:依十二長生算每爻對月令(×2)、日令的「綜合旺衰」(旺/偏旺/持平/偏弱/弱),寫進 payload `對六爻[].旺衰`;頂層加 `月令/日令`;`schema_version→2`。
  - prompt §二/§四 改成「**直接讀 `對六爻[].旺衰.綜合旺衰`,不自推**」——修掉「AI 自算五行旺衰會錯」(實測:巳火在午月被 AI 誤判為弱,引擎正確判偏旺;AI 還會捏造不存在的「月剋」欄位)。
  - **教訓 1**:**確定性的命理計算(旺衰、空亡、生剋)交給引擎、AI 只翻白話**,別讓 AI 自己算五行——會錯且會幻覺欄位。
  - **教訓 2**:**靠 prompt 壓「白話段落的絕對長度」收斂不了、逐次飄**(〇段叫它 4–6 句也壓不住)。要硬壓得改「固定條列模板(就 N 條、每條一句)」這種結構性限制。§五「禁止重列卦理詞」則較有效。
- **解卦 prompt v1.4:治冗長重複**(`f38460d`)。v1.1~1.3 放寬過頭,白話在〇總結/技術段/§五 重複三遍。確立分工:**白話只在〇段講透(4–6句),技術段一~四只給卦理判斷+極短點題、不再白話復述;§五 改 2–4 句純收束**。能力不減(空亡/旺衰/世應/鼓勵都在),只去重去贅。
  - 教訓:放寬「多解釋」時容易讓同一內容在多段重複 → 規則要寫「**各段分工、白話只講一次**」。
- 建本機背景檔(本檔)+ `deploy-verify` skill;App 另開 `/opt/hexagram-app/WORKLOG.md`。

### 2026-06-18
- **還原「卜卦問事」下拉手動輸入 tab**(web):當初 commit `0393805` 移除,用 git revert 還原;CSS 本就在。`481eb9a`
- **下拉模式改為管理者專用**:包 `{% if current_user.is_admin %}`,一般使用者只有擲卦;tab 切換 JS 改為面板存在才納入。`aafcc7d`
  - ⚠️ 此功能**僅 web、且自用**,刻意不上 App(見待辦)。
- **解卦 prompt 三輪優化**(手動 + 流年):
  - v1.1 白話更詳盡 + 總結正面鼓勵(誠實但建設)。`4c63b28`
  - v1.2 依吉凶/空亡/旺衰/問題加深。`2e3c101`
  - v1.3 世應依月令/日令判強弱(§二 給算法、§四 升級為「世應強弱與關係」)。`4f70b84`
- 5 個 commit 已 push 到 origin/main(`604a5c6..4f70b84`)。

## 五、待辦事項

> 詳細的長期 roadmap 另見 Claude 自動記憶 `hexagram-roadmap`。

- [ ] **App 卜卦問事補「下拉手動輸入」模式**(暫緩;使用者目前說先只要 web)。若要做:RN 用 Picker/按鈕選每爻(少陽/少陰/老陽/老陰),同步送出的 y0~y5。
- [ ] **社群登入** Google / Apple / Line(卡在開發者憑證)。
- [ ] **Email 進階**:驗證信 + 忘記密碼正式寄出(需設 SMTP;目前 `SMTP_HOST` 未設,信只進 log)。
  - 建議寄系統信走 **Resend / SES** 等 transactional 服務,**不要自架 mail server**(住宅 IP 會被當垃圾信)。後端 `_send_mail` 已是供應商無關,`.env` 填 SMTP 即可。
- [ ] **綠界金流**:目前儲值是測試按鈕(test_topup),待接綠界。
- [ ] **App 推播通知**(expo-notifications + Expo Push,需存 push token)。
