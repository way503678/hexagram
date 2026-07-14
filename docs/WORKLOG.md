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

### 2026-07-03 — CSRF 防護 + 註冊 Email 驗證信(贈點延後)
- **CSRF(自製無套件)**:session 惰性發 `csrf_token`(context processor 注入模板);`_csrf_protect` before_request 驗證 POST/PUT/PATCH/DELETE(表單 hidden 或 `X-CSRF-Token` header,compare_digest);**豁免**:Bearer 認證(App 不吃 cookie)、完全無 session cookie 的請求(無可冒用身分,curl/App 未登入呼叫不受影響)。11 個表單插 hidden、base.html 加 meta+`window.CSRF`、manual/member/admin-fortune 的 fetch 帶 header。三情境實測:無 cookie 200、有 session 無 token 403、帶 token 通過。
- **註冊驗證信**:users 加 `email_verified/verified_at`(**舊帳號 backfill TRUE**、新註冊顯式 FALSE,migration 冪等);註冊寄 HTML 按鈕驗證信(HMAC token 24h,`VERIFY_TTL_SECONDS`);**新會員贈點改為驗證完成才入帳**(`/verify` 首次 `set_email_verified` 才 add_points,防拋棄式信箱刷點);`/api/v1/auth/resend_verify` 重寄(需登入);web 會員中心加未驗證提示條+重寄鈕;`_public_user` 帶 email_verified(App 可顯示,App UI 待下次發版)。全流程實測:註冊 0 點→驗證 +3→重複驗證不重發;測試帳號已清。

### 2026-07-03 — 新增資安文件 docs/SECURITY.md
- 把歷來安全機制整理成單一文件:認證雙軌(JWT/session)、24h 時效、pwv 全裝置登出、登入鎖定、忘記密碼(HMAC/1h/一次性/防列舉)、SECRET_KEY fail-fast、機密管理、扣點原子、SQL 參數化、AI 輸入截斷、CORS 決策、**已知限制表**(無 rate limit/CSRF token/註冊驗證信、Resend key 待 rotate)與事件應對速查。**改安全相關程式前先讀;新增機制後回寫**。README 相關文件已加連結。

### 2026-07-12 — PostgreSQL 抽成獨立容器(finance-apps 退役)
- **背景**:舊共用 postgres 在 `/data/finance-apps`(還含 n8n/firefly/homarr)。改成獨立。
- **新架構**:`/opt/database`(獨立 postgres,建立網路 `appnet`,掛既有卷 `finance-apps_pg-data` external=資料原地不動)+ `/opt/apps`(firefly/n8n/n8n-runners/homarr 搬過來,連 appnet)。
- **hexagram 改動**:docker-compose 的外部網路 `finance-apps_default` → `appnet`(host 名 postgres 不變,連線字串不動)。切換時需 `down` 再 `up`(改 external 網路名 compose 不會自動重建,只改 name 會 start 舊容器抓到已刪網路而失敗)。
- **遷移法**:先 `pg_dumpall` 全備份(`/opt/database/backup/pre-migration-20260712.sql`,649K 含 5 庫)→ 停 hexagram/backup → down finance-apps → 起獨立 postgres(重用卷)→ 驗 5 庫+會員數在 → 起 hexagram 驗健康+對外 200 → 起 apps。**零資料遺失、hexagram 僅約 2-3 分鐘離線**。
- 文件同步:README/DEPLOY/RESUME 的「finance-apps 前置相依」全改為 `/opt/database` + `appnet`。
- 教訓:改 compose external 網路名一定要 down 再 up,不能只 up(舊容器抓舊網路 ID 會失敗)。

### 2026-07-03 — 改/重設密碼後全裝置自動登出(密碼版本指紋)
- 缺口:改/重設密碼後,舊 App token 與網頁 session 仍有效至 24h 上限。
- 修法(零狀態,無 session 表):`_pw_version(uid)`=密碼雜湊 sha256 前 8 碼。**token** 簽發帶 `pwv` claim,verify 時比對 DB 現值(無 pwv 的舊 token 一律失效);**web session** 登入寫入 `pwv`,`_resolve_current_user` 比對不符即 `session.clear()`。密碼一變 → 指紋變 → 所有裝置舊憑證自動失效。
- UX:登入中自行改密碼(`_change_password`)成功後刷新**本機** session pwv——自己不被登出、其他裝置全踢(GitHub 式)。App 端改密碼/重設 → 舊 token 401 → AuthContext 自動登出重登。
- 端到端驗證(真帳號、雜湊原樣還原):改密碼後舊 token=None、新簽有效、再變再失效。**部署副作用:現有全部登入者會被登出一次**(舊憑證無 pwv),一次性。
- 順帶:忘記密碼信連結曾出現 localhost(內部測試觸發 url_root 所致)→ `.env` 設 `PUBLIC_BASE_URL=https://hexagram.johnsonwebsites.cc`(compose 本有透傳),重設連結一律用公開網址。

### 2026-07-03 — Email 寄送正式上線(Resend + 自家網域)
- `.env` 填入 `RESEND_API_KEY`(僅寄信權限的受限 key)+ `MAIL_FROM=命果 MINGO <noreply@johnsonwebsites.cc>`;網域已在 Resend 驗證(DKIM/SPF 綠,Tokyo region,DNS 在 Cloudflare)。程式不用改(_send_mail 6/23 就緒)。
- 實測:系統 `_send_mail` 自家網域寄送成功;**忘記密碼全流程**(`/api/v1/auth/forgot` → 真寄重設信)通過。忘記密碼信、密碼變更通知、🌱回訪提醒 皆可正式寄送給任何會員。
- 註:重設連結 base 用 `PUBLIC_BASE_URL` env(未設)或 request.url_root(跟著請求網址,經公開網址操作即正確)。回訪提醒 Email 排程仍需設 `CRON_TOKEN` + 每日 curl dispatch(見 6/28 Phase 3)。待辦「Email 進階」可劃掉大半。

### 2026-07-03 — 準確度批次 v2.5:月令改四時旺相休囚死 + 日合 + 有異取異
- **網路查證**(增刪派多源一致):月令旺衰應論**四時旺相休囚死**(臨我旺/我生相/生我休/剋我囚/我剋死),**十二長生只用於日辰與動變爻,無月墓月絕之說**。我們引擎月令誤用十二長生 → 「金在巳月」誤判旺(正解:死,巳火剋金)、「土在四季月」誤判墓/衰(正解:當令旺)。
- **修 1(引擎)**:elements.py 加 `seasonal_state/seasonal_tier`;`_yao_wangshuai` 月令改四時、日令保留長生;payload `旺衰.月令` 改 `{地支,四時,旺衰}`(舊鍵「長生」移除,模板/App 無讀者)。翻轉矩陣:30 組差異、4 組方向翻轉(金丑/金巳/土寅/土戌)。**validate_classics 獨立重算同步(自帶四時表),5376 卦回歸 0 錯誤**。真假空/暗動沿用綜合旺衰自動跟進;入墓(臨墓/日墓)不涉月令不動;流年系統當值分析(長生)為另一設計,不動。
- **修 2(引擎)**:日辰六合 → payload 每爻加 `日合`(靜爻=合起:有力被拴待沖;動爻=合絆:暫不動待沖開,應期參考)。實測寅日亥動爻=合絆 ✓。應期候選原有「合住待沖」不動。
- **修 3(prompt)**:§一 兩現補「有異取異」(空/破/暗動之爻常為關鍵)——標明實戰參考、與增刪「動>旺」衝突時以原文為先。§一 兩現逢墓改讀「入墓欄/日令長生」(無月墓);§二 讀法與判準說明同步。版本 v2.5。
- 教訓:**確定性判準的「來源系統」也要對原典**——之前只驗「算得對不對」(長生表沒算錯),沒驗「該不該用長生」(月令根本不該用)。

### 2026-07-03 — 效能評測 + 二項修復(黃曆快取、靜態檔快取)
- **評測**(localhost 直測):引擎極快(排盤 0.4ms/prompt 1ms);**熱點=黃曆 `month_info` 836ms**(31 天×26.6ms 逐日重算),/almanac 與 API month 每次 ~845ms;**併發 8 人開黃曆 p50 飆 6.5 秒**(CPU bound+GIL)。流年 81ms、analyze_daily 15ms(低頻可接受)。傳輸層:style.css 57KB 竟是 `no-cache`(明明有 ?v= busting)、origin 無 gzip。資源健康(RAM 80MB)。
- **修 1:黃曆 lru_cache**(almanac.py):`day_info(400)`/`month_info(24)` — 純日期函數(擇日/紫白/節氣不變)安全快取;呼叫端(render/jsonify)皆只讀。**/almanac 846ms→~4ms;併發8 6531ms→12-24ms**。注意:快取 per-worker(gunicorn 2 процes),重建後每 worker 每月份首次仍 ~840ms(一次性)。**勿在呼叫端 mutate 回傳 dict**(會污染快取)。
- **修 2:靜態檔快取 1 年**(app.py `SEND_FILE_MAX_AGE_DEFAULT=365d`):模板全帶 `?v={{asset_version}}`(mtime),改版自動換 URL;style.css 從每頁重抓 57KB → 快取。對 tunnel(使用者瓶頸)體感最有感。
- 未做(記錄):gzip(要新套件 flask-compress,效益中,先觀察)、analyze_daily/fortune 快取(涉會員資料變更,低頻不值得)。內容正確性抽查 7/5=庚辰日 ✓。

### 2026-07-03 — 文件體檢對齊實況 + 清死碼(兩平台)
- 用兩個探查代理掃 web/App 文件 vs 實況,逐項核實後修:
- **後端**:README.md 整份重寫(舊名命卦排盤→命果 MINGO、補萬年曆/會員/API/almanac、路由改分群、移除已刪的 `/admin/login`、修死連結 PROCESS_SAFETY.md);HEXAGRAM_FILES.md 刪 `admin/login.html`(已刪、raw 會 404)+ 檔數改「快照會過時、以 git ls-files 為準」+ .env 機密改 ADMIN_EMAILS;DEPLOY.md 補「postgres 是外部 finance-apps 相依」警告;app.py docstring 路由總覽更新(刪不存在的 admin/login|logout)。
- **死相依**:`zhdate==0.1` 全專案零 import(農曆早改 sxtwl)→ 從 requirements 移除 + 清掉 Dockerfile 為它做的 `setuptools<58` 相容 hack。重建驗證 healthy。
- **安全**:`.env.example` 的 SECRET_KEY 佔位值加進 `_WEAK_SECRETS`(忘了換也擋)。
- **App**:README 重寫(SDK 56→54/RN 0.81、3-tab、AI 已上線)、AGENTS/WORKLOG 版本校正、WORKLOG「二、結構」改 3-tab、app.json adaptiveIcon 舊底色 #FFF8EF→#F1E9DC;theme.ts 清 8 個未用色票 + 3 個未用漸層(tsc 抓到 GradientCard 預設 variant="deep" 仍需 deep → 改預設為 "bright")。tsc 通過。

### 2026-07-03 — 解讀 prompt v2.4:新增【盤面解析】段(放【一句話】後)
- 使用者參考別家 app,想要一段「盤面卦理解說」放在【一句話】後面。
- §三之二 在【一句話】後加**【盤面解析】**:2–4 句用「術語+緊接白話翻譯」解說盤面結構(世應/六親/動化/空亡/生剋)並扣回問事,像「世爻持未土臨白虎(=環境穩定但束縛強)」。
- **這是全篇唯一可出現術語處**(v2.3 的「全白話」放寬為「除【盤面解析】外一律白話」);訊號一律照引擎、不自創,仍守不下絕對斷言/不代決定。
- 前端 renderMingo(web)/MingoReading(App)用正則通吃任意【標記】渲染成卡片,**不需改前端、不需發 APK**。驗證:段落順序 一句話→盤面解析→現在的你、容器已載、版本表未外洩。

### 2026-07-02 — 登入最長 24 小時,超過自動登出
- 新增 `SESSION_MAX_AGE_SECONDS`(env `SESSION_MAX_AGE_HOURS`,預設 24)。
- **App(token)**:`make_token` exp 改 24h;`verify_token` 加 `iat` 檢查——距今超過 24h 即失效(連舊的 30 天長效 token 一併登出)。移除舊 `TOKEN_TTL_DAYS`(30)。App 收 401 由 AuthContext 自動登出,**不需改 App、不需發 APK**。
- **Web(session)**:`PERMANENT_SESSION_LIFETIME=24h`;`_resolve_current_user` 查 `session['login_at']`,超過 24h(或缺)清 session 強制重登。
- 容器內實測:新 token 有效、25h 舊 token 失效、23h 有效;session 25h 過期、1h 有效、缺 login_at 過期。

### 2026-07-02 — 萬年曆彈窗日期改「年月日」格式
- 使用者:萬年曆 hover 小彈窗的日期由 `2026-07-05` 改為 `2026年7月5日`(pop-h)。
- **干支也改全柱**:pop-h 原只印日柱 `庚辰日` → 改 `丙午年甲午月庚辰日`(year_gz/month_gz/day_gz)。App `AlmanacScreen` 干支列本就顯示全柱,不用改。
- 兩平台對等:App `AlmanacScreen` 選日詳情標題國曆同步改年月日格式。
- 純顯示格式,web 已重建驗證;App 已改+tsc(未發 APK)。

### 2026-07-02 — 卜卦問事:擲滿 6 次後「重新擲卦」改「排盤」
- 擲滿 6 爻後不再顯示「重新擲卦」,改顯示「排盤 →」(type=submit,直接送出排盤)。移除 btnReset 及其 handler。
- 底部原本恆顯的「排盤」submit 改 `display:none`,只在管理員「下拉模式」由 mode 切換顯示(避免兩顆排盤)。擲卦模式一律用擲滿後出現的「排盤 →」。
- playwright 驗證:擲 6 次後 btnCast 隱藏、「排盤 →」顯示、無「重新擲卦」、6 爻皆擲。純前端。

### 2026-07-02 — 卜卦問事:加卜卦說明彈窗 + 擲卦鈕上移
- **說明彈窗**(manual.html,只在輸入頁):進頁彈出「本軟體為金錢卦卜卦方式/需自行手動擲卦共 6 次」+ 勾選框「今日不再顯示」+「確認」鈕。
- **確認前鎖住擲卦**:`window.__castLocked`,btnCast handler 開頭檢查;彈窗全螢幕遮罩,雙保險。按「確認」才解鎖。
- **今日不再顯示**:勾選後 `localStorage['mingo_manual_intro_hide']=今天日期`;當天再進頁不彈、直接可擲(隔日恢復)。
- **擲卦按鈕上移**:coin-controls 移到 coin-instructions(「從初爻開始…」)之前。
- playwright 驗證:彈窗顯示/確認前擲卦無效/確認後解鎖可擲/勾選後 reload 不再彈且可直接擲。純前端,不需改後端邏輯。

### 2026-07-01 — 解讀 prompt v2.3:移除【深入理論】段 → 輸出全程白話
- 使用者要求【深入理論】(術語條列)也不顯示。因它原是「唯一可出現術語處」,拿掉後改為**全篇一律白話、不出現任何專業術語**。
- §三之二 刪【深入理論】段;同步更新段首、整體鐵則、§四語氣定位(「術語+白話雙軌」→「一律白話」)。輸出段剩:【一句話】【現在的你】【這一卦在說】【為什麼是這一卦】【可以怎麼做】【可能的發展】【陪你一句】。
- 判讀規則與界線不變;前端 renderMingo 少一個標記自然不顯示,不需改。驗證:容器內 prompt 已無【深入理論】、含「全篇白話」、版本表未外洩。

### 2026-07-01 — 修起卦時間 bug:擲卦改用「當下時間」不再手選
- **Bug**:卜卦問事的年/月/日/時是**開頁當下**由伺服器 render,之後無 JS 更新 → 頁面開著擺到後面才擲卦,時間停在開頁那刻。使用者子時開頁、下午才擲 → 時柱誤為子時(引擎、時區都正確,是前端時間凍結)。
- **修法**(manual.html):擲卦模式**不再給時間選擇器**,改唯讀顯示「🕐 起卦時間:現在」;年月日時改隱藏欄位,JS 每秒 + 送出前填為**當下時間**(client now),後端直接用。結果頁不覆蓋(保留起卦時間供 AI 解讀重排用同一時間)。管理員「下拉模式」才顯示可編輯選擇器並停自動更新(自訂時間)。
- 驗證:playwright 確認新頁面唯讀顯示當下(20:36)、送出的 fld_h=20(當下時),picker 隱藏。引擎時柱本就正確(h→時支),此修解決前端凍結。

### 2026-07-01 — 解讀 prompt v2.2:移除【易經原文】段 + 再調直白
- 使用者要求:拿掉【易經原文】(卦辭)輸出段、語氣再直接。
- §三之二 刪【易經原文】段(段首收合說明同步移除);段首語氣「溫暖有陪伴感」→「有溫度但直接、不繞圈子」;【一句話】加「開門見山、先給答案」、偏阻直接點卡點;【現在的你】共情縮一句、快進重點;象內講白 加「開門見山」首要 bullet。
- 判讀規則與界線(不下絕對斷言/不代決定/醫療保守)不變。前端 renderMingo 依標記渲染,少一個【易經原文】標記即自然不顯示,不需改前端。
- 驗證:loader 確認【易經原文】已不在送 AI 內容、版本表未外洩;容器內 `_MANUAL_AI_PROMPT` 已載新版。

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
- [x] **Email 寄送**:2026-07-03 Resend + 自家網域上線,忘記密碼/密碼變更/回訪信皆真寄。剩:驗證信(註冊 email 驗證)未做、回訪排程需 CRON_TOKEN。
  - 建議寄系統信走 **Resend / SES** 等 transactional 服務,**不要自架 mail server**(住宅 IP 會被當垃圾信)。後端 `_send_mail` 已是供應商無關,`.env` 填 SMTP 即可。
- [ ] **綠界金流**:目前儲值是測試按鈕(test_topup),待接綠界。
- [ ] **App 推播通知**(expo-notifications + Expo Push,需存 push token)。

## 2026-07-14 內部端點:今日指引供 SELFTOOLS 首頁
- 新增 GET /api/v1/daily_internal(X-Internal-Key 驗證,env INTERNAL_API_KEY;公網 403)。
  依 y/m/d/h 生日參數算 analyze_daily,與會員版同引擎。供 selftools 首頁「生活摘要」內網呼叫。
- 驗證:無鑰 403 ✓、有鑰 200 ✓;SELFTOOLS 首頁運勢卡輸出與 App 截圖一致。
