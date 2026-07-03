# 社群登入規劃 — Google / Apple(命果 MINGO App)

> 狀態:**規劃中,未動程式**。決策:**Android 為主 → 先做 Google;Apple 等上 iOS 再做**。
> 後端 repo `/opt/hexagram`、App repo `/opt/hexagram-app`。App package/bundle = `com.hexagram.app`。

## 0. 結論:後端架構已備好,只缺「驗社群 token → 簽我們的 JWT」

`users` 表本來就為社群登入設計:
- `UNIQUE(auth_provider, auth_id)`、`password_hash` 註解明寫「社群登入留空」。
- 已有入口 `db.get_or_create_user(auth_provider, auth_id, display_name, email)`。
- Email 流程 = `get_or_create_user('email', …)` → `make_token(uid)` → 回 `{token, user}`。

**社群登入只要新增驗證路由,完全重用 `get_or_create_user` + `make_token`。** 不動現有 Email 流程。

---

## 1. Google 登入(先做,Android)

### 1a. 要申請的憑證(這是最大關卡 — 目前都還沒有)

1. **Google Cloud 專案**:https://console.cloud.google.com → 建專案(或用現有)。
2. **OAuth 同意畫面**(OAuth consent screen):User Type 選 External;填 App 名稱「命果 MINGO」、support email;scopes 只要 `email`、`profile`、`openid`;測試階段把自己的 Google 帳號加進 Test users。
3. **建 OAuth client ID**(APIs & Services → Credentials → Create credentials → OAuth client ID),要建 **兩個**:
   - **Web application** client → 拿到的 **Web client ID** 給「後端驗 `aud`」用,也是 App 端 `webClientId`。
   - **Android** client → 填:
     - Package name:`com.hexagram.app`
     - **SHA-1 憑證指紋**(見下)
4. **SHA-1 怎麼拿**(我們用 EAS 託管簽章金鑰):
   ```bash
   cd /opt/hexagram-app
   EXPO_TOKEN=… npx eas-cli credentials   # 選 Android → 看 Keystore → 複製 SHA-1 Fingerprint
   ```
   ⚠️ **preview 與 production 用不同 keystore = 不同 SHA-1**。兩個 build profile 都要用的話,**兩組 SHA-1 都要加進同一個 Android OAuth client**,否則某一種 build 的 Google 登入會回 `DEVELOPER_ERROR`。

> 產出:`GOOGLE_WEB_CLIENT_ID`(後端 .env + App webClientId)、Android client(綁 package + SHA-1)。

### 1b. 後端(憑證到位後做)— 新增一條路由

- `POST /api/v1/auth/google`,收 `{ id_token }`:
  1. 驗證 id_token:打 Google `https://oauth2.googleapis.com/tokeninfo?id_token=…`(**stdlib urllib,免新套件**,跟 Resend 那套風格一致;記得帶 `User-Agent`,Cloudflare 經驗)。
  2. 檢查回傳 `aud == GOOGLE_WEB_CLIENT_ID`、`iss` 為 `accounts.google.com`、未過期。
  3. `db.get_or_create_user('google', payload['sub'], payload.get('name'), payload.get('email'))`。
  4. `token = make_token(user['id'])` → 回 `{token, user}`(跟 login 一模一樣)。
- env 加 `GOOGLE_WEB_CLIENT_ID`;docker-compose 透傳。
- (進階可改本地驗章對 `https://www.googleapis.com/oauth2/v3/certs`,省一次外連;先用 tokeninfo 最簡。)

### 1c. App(憑證到位後做)

- 套件二選一:
  - **`@react-native-google-signin/google-signin`**(推薦):原生帳號選擇彈窗、UX 最好;需 **dev/preview build**(我們本來就用 EAS,OK,Expo Go 測不了)。加 config plugin + `webClientId`。
  - `expo-auth-session/providers/google`:純 JS、走瀏覽器,設定較輕但 UX 普通。
- `api.ts` 加 `loginGoogle(idToken)` → `POST /api/v1/auth/google` → 回 `AuthResult`。
- `AuthContext` 加 `loginGoogle`,存 token 邏輯跟現有 `login` 共用。
- `WelcomeScreen`(落地頁)同意後的入口加一顆「用 Google 繼續」按鈕(社群登入 → 直接登入/註冊合一)。

---

## 2. Apple 登入(等真的上 iOS App Store 再做)

- 套件 `expo-apple-authentication`,**只在真 iOS 機 + dev build** 能測。
- 憑證:**Apple Developer Program($99/年)**、開 Sign in with Apple capability、Service ID;需 Mac/iOS 環境。
- **強制規則**:iOS App 上架且提供任何第三方登入(如 Google),Apple **要求**必須同時提供 Sign in with Apple。純 Android 不受此限 → 所以現在先不做。
- 後端對稱:`POST /api/v1/auth/apple` 收 `identityToken`(本身是 JWT),對 `https://appleid.apple.com/auth/keys` 驗章、檢查 `aud == com.hexagram.app`、`iss == https://appleid.apple.com`,取 `sub`(+首次登入才有的 email)→ `get_or_create_user('apple', sub, …)` → `make_token`。
- 注意:Apple 只在**第一次**授權回傳 email/姓名,之後不再給 → 首次就要存起來。

---

## 3. 待辦順序(ponytail:先做能解鎖、不花錢的)

1. [ ] (你)申請 Google OAuth 憑證(§1a)+ 從 EAS 拿 SHA-1。
2. [ ] (後端)`/api/v1/auth/google` 驗證路由 + `GOOGLE_WEB_CLIENT_ID` env。
3. [ ] (App)google-signin 套件 + `loginGoogle` + 落地頁按鈕 → 出含 Google 登入的 dev/preview APK 實測。
4. [ ] (之後上 iOS 時)Apple 登入 §2。

## 4. 順帶記下的小事(非本任務)
- `app.json` 沒設 `scheme`;若走 `expo-auth-session` 需要加。google-signin 原生不強制。
- `app.json` `android.adaptiveIcon.backgroundColor` 還是舊米白 `#FFF8EF`,可順手對齊新暖米。
