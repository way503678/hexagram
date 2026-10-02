# 命果 MINGO — 資安機制說明(SECURITY.md)

> 本文件記錄系統實作的安全機制、設計理由與已知限制。
> **改動任何安全相關程式前先讀這份**;新增機制後回寫本文件。
> 最後更新:2026-10-02(各機制皆已實測驗證,見 WORKLOG 對應日期)。

---

## 一、認證與會話(Authentication / Session)

### 1. 登入憑證(雙軌)
| 管道 | 憑證 | 實作 |
|------|------|------|
| App / API | **JWT(HS256)** `Authorization: Bearer` | `make_token` / `verify_token`(app.py,stdlib hmac 自簽,無外部套件) |
| 網頁 | **Flask session cookie** | `session["user_id"] + login_at + pwv` |

JWT payload:`{uid, iat, exp, pwv}`。簽章金鑰 = `SECRET_KEY`(見 §四)。

### 2. 登入時效:最長 24 小時(2026-07-02)
- 常數 `SESSION_MAX_AGE_SECONDS`(env `SESSION_MAX_AGE_HOURS`,預設 24)。
- **token**:`exp` 簽 24h,且 `verify_token` 另檢查 `iat` 距今 ≤ 24h(舊制長效 token 一併失效)。
- **session**:`PERMANENT_SESSION_LIFETIME=24h` + 每請求檢查 `login_at`(`_session_expired`),超時或缺值即 `session.clear()`。

### 3. 密碼版本指紋 pwv — 改/重設密碼即全裝置登出(2026-07-03)
- `_pw_version(uid)` = 密碼雜湊 sha256 前 8 碼。
- token 簽發帶 `pwv` claim、verify 時比對 DB 現值;session 登入時寫入、`_resolve_current_user` 比對,不符即清除。
- **效果:密碼一變(自行變更或忘記密碼重設),所有裝置舊憑證下一請求立即失效**。零狀態設計,無需 session 黑名單表。
- UX:登入中自行改密碼者刷新**本機** session pwv(自己不登出、其他裝置全踢)。App 收 401 由 AuthContext 自動登出。

### 4. 管理員
- **無獨立管理員帳密**:一般 `/login` + `ADMIN_EMAILS` 環境變數名單判定 `is_admin`(`_email_is_admin`)。
- 管理端點以 `admin_required` 保護;下拉排卦模式等管理功能僅 admin 渲染。

---

## 二、密碼與帳號保護

### 1. 密碼儲存與政策
- 儲存:werkzeug `generate_password_hash`(pbkdf2,加鹽)。**明文不落地、不進 log**。
- 政策:至少 8 碼、英數混合(`_password_error`,前後端皆驗)。

### 2. 登入失敗鎖定(brute-force 防護)
- **連續失敗 3 次**(env `LOGIN_MAX_FAILS`)自動鎖定(`users.locked/locked_at`,`register_login_failure` 以單句 SQL 原子遞增+判鎖)。
- 鎖定後**先於密碼檢查**擋下(正確密碼也進不去)。
- 解鎖:本人走忘記密碼重設(重設成功即解鎖 = 證明信箱控制權),或管理員後台解鎖。
- 登入成功且未鎖 → `reset_login_failures` 歸零。

### 3. 忘記密碼(重設信)
- 重設 token:HMAC 簽章(`SECRET_KEY + "|pwreset|" + 目前密碼雜湊`),**1 小時有效**(env `RESET_TTL_SECONDS`)。
- **一次性**:簽章綁「目前密碼雜湊」,密碼一改舊連結自動作廢。
- **防帳號列舉**:`/api/v1/auth/forgot` 與網頁版一律回成功訊息,不透露帳號是否存在。
- 連結 base:`PUBLIC_BASE_URL` env 優先(已設 `https://hexagram.johnsonwebsites.cc`),避免內部觸發產生 localhost 連結。
- 重設成功:一併解鎖帳號 + 寄「密碼變更通知」;pwv 機制使全裝置登出。
- 自助入口:App 落地首頁與登入頁、Web 首頁與登入頁皆提供「忘記密碼／帳號解鎖」；鎖定訊息直接引導本人走此流程,不需聯絡管理員。

### 4. Session cookie 屬性
- `SESSION_COOKIE_HTTPONLY=True`(JS 讀不到)、`SESSION_COOKIE_SAMESITE=Lax`(CSRF 緩解)。
- HTTPS 由 Cloudflare Tunnel 終結(對外一律 https)。

---

## 三、金鑰與機密管理

### 1. SECRET_KEY fail-fast(2026-06-30)
- 未設定、或等於已知弱值/佔位值(`_WEAK_SECRETS`,含 docker-compose 與 `.env.example` 的佔位)→ **啟動即 RuntimeError 拒絕服務**,絕不默默用弱金鑰。
- 產生方式:`python -c "import secrets;print(secrets.token_hex(32))"`。
- SECRET_KEY 一換 = 所有 token/session/重設連結全部失效(輪替金鑰即全站登出)。

### 2. 機密存放
- 全部在 `.env`(**已在 .gitignore,不進 git**),docker-compose 以 `${VAR:-}` 透傳。
- 現役機密:`SECRET_KEY`、`ADMIN_EMAILS`、`ANTHROPIC_API_KEY`、`RESEND_API_KEY`、`CRON_TOKEN`(排程用,未啟用)。
- Resend key 使用**僅寄信權限**的受限 key(最小權限)。⚠️ 待辦:2026-07-03 該 key 曾出現在對話紀錄,穩定後應 rotate。

---

## 四、資料與交易保護

### 1. SQL
- 全面參數化查詢(psycopg2 `%s`),無字串拼接 SQL。

### 2. 點數(果實)交易
- 扣點**原子**:`UPDATE users SET points_balance = points_balance - %s WHERE id=%s AND points_balance >= %s`(db.try_deduct_point)——單句條件更新,併發不會超扣。
- 每筆增減寫入 `point_ledger`(稽核帳本,餘額異動的真相來源);AI 解讀失敗自動退點(refund)。
- 卜卦流程採同筆紀錄:`/api/v1/chart` 起卦成功先存 `divination_questions.chart_payload` 並回傳 `record_id`;Prompt／AI 只允許更新「屬於目前會員」的該筆紀錄。
- 尚未帶 `record_id` 的舊版 App 以「會員＋問題＋六爻＋排盤時間」在 24 小時內精確找回同一次起卦；避免超過舊制 20 秒去重窗後，重看 AI 被誤認成新紀錄而再次扣點。
- Prompt 由 `get_or_charge_prompt` 在**同一 DB 交易**中鎖定紀錄與會員、檢查既有內容、條件扣 1 點、保存 `prompt_text`、寫帳本；任一步失敗皆不回傳新 Prompt。未過期內容再取用回 `existing`，不重複扣點。
- AI 解讀先以 `reserve_ai_reading` 鎖定同筆紀錄並預扣；併發第二次請求回 `in_progress`。每次 reservation 有一次性 token，保存與退款都必須 token 相符，避免舊逾時請求誤完成或誤退新請求。生成／保存失敗由 `refund_ai_reading` 原子清除 reservation 並最多退一次。
- 程序崩潰或資料庫短暫中斷若留下未完成 reservation，會員下一次讀取帳號時會自動清理超過 15 分鐘的預扣並寫入退款帳本；即使當下退款失敗，也不會永久卡住果實。
- 付費 AI 的 Web SSE 會先在伺服器完整生成並成功保存，之後才送出任何解讀文字；保存失敗時只回錯誤並退款，不會形成「已拿到部分／完整內容又退款」。回應中斷時內容已在歷史，可免費取回。
- 會員歷史與付費內容回應一律 `Cache-Control: private, no-store` 並依 `Authorization, Cookie` 區分，避免瀏覽器／CDN／共享代理誤快取造成跨會員內容外洩。
- 歷史詳情 `/api/v1/member/questions/<id>` 僅依 `user_id` 讀取，不呼叫任何扣點函式；因此查看卦象、AI 說明或複製已購 Prompt 都不會新增帳本。

### 3. 個資
- 蒐集/利用依 `legal.json`(單一來源)條文;註冊記 `consent_at/consent_version`。
- 會員可自行刪除帳號(`/member/delete`、`/api/v1/member/delete`)。
- Email 服務走 Resend(自家已驗證網域 johnsonwebsites.cc,SPF/DKIM 齊)。
- `chart_payload` 與問題保留在同一筆卜卦紀錄；Prompt／AI 全文分欄保存 30 天，到期清空全文但保留卦象與稽核紀錄。

---

## 五、輸入與 API 防護

- **AI 輸入截斷**:所問之事上限 500 字(前後端皆截),控制 prompt 注入面與成本。
- **AI 端點**:需登入(401)+ 扣點(經濟性節流);prompt 由後端組裝,引擎確定性資料 AI 只讀。
- **CORS**:`/api/*` 開 `Access-Control-Allow-Origin: *` —— 設計決策:排盤 API 免費且純運算、無狀態變更風險;會員/AI 端點另有 Bearer token 保護(cookie 不跨域送出,Lax)。
- 生日/日期等輸入皆型別驗證(`_parse_birthday`、`_compute_chart` 逐項驗)。

---

## 六、已知限制與待辦(誠實記錄)

| 項目 | 狀態 | 備註 |
|------|------|------|
| Rate limiting(登入/forgot/AI) | ❌ 未做 | 現靠登入鎖定+扣點節流;公開端點(forgot 寄信)無頻率限制,濫用可耗寄信額度 → 建議之後加 |
| Resend key rotation | ⏳ 待做 | key 曾入對話紀錄(2026-07-03) |
| 註冊 Email 驗證信 | ✅ 2026-07-03 | HMAC token(24h)、HTML 按鈕信;**新會員贈點延至驗證完成才入帳**(防拋棄式信箱刷點,`set_email_verified` 首次才發);舊帳號 backfill 已驗證;`/verify` + `/api/v1/auth/resend_verify`(重寄);web 會員中心有未驗證提示條 |
| CSRF token(表單) | ✅ 2026-07-03 | 自製(無套件):session 發 token、`_csrf_protect` before_request 驗證(表單 hidden / X-CSRF-Token header);豁免 Bearer 認證與無 session cookie 請求(無可冒用身分)。SameSite=Lax 為第二層 |
| 回訪提醒排程 `CRON_TOKEN` | ⏳ 未啟用 | dispatch 端點已含授權檢查(管理員或 X-Cron-Token) |
| App 端 token 存放 | ✅ | expo-secure-store(Keystore/Keychain) |

---

## 七、事件應對速查

- **懷疑金鑰外洩**:換 `SECRET_KEY`(全站登出)→ rotate `RESEND_API_KEY`/`ANTHROPIC_API_KEY` → 檢查 `point_ledger` 異常。
- **單一帳號被盜**:管理員後台鎖定該帳號(locked)→ 使用者走忘記密碼重設(重設即解鎖 + 全裝置登出)。
- **強制某人全裝置登出**:改其密碼雜湊(pwv 變即全失效),或請本人重設密碼。
