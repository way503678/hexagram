# 重開機後啟動指南(RESUME)

> 最後更新:2026-06-28 晚。重開機後照這份把服務跑起來、接續未完成的事。

## 一、Docker 服務(重點:有兩個 compose 專案,要照順序起)

這台主機上跑著兩組 docker compose:

| 專案 | 目錄 | 容器 |
|---|---|---|
| **database** | `/opt/database` | **postgres**(18-alpine,獨立)— 建立共用網路 `appnet`、掛卷 `finance-apps_pg-data` |
| **apps** | `/opt/apps` | n8n、n8n-runners、firefly-iii、homarr(連 postgres,在 appnet) |
> 2026-07-12 起 postgres 已升 18 且**全部工具集中在這一顆**(database 分隔:hexagram/n8n/stock/fx/mops/flights);flight-tracker 不再有自己的 db。舊 17 卷已移除,SQL 備份在 /opt/database/backup/。

| **hexagram** | `/opt/hexagram` | hexagram(命果後端)、hexagram-db-backup |

> 2026-07-12 起 postgres 已從 finance-apps 抽成獨立 `/opt/database`(舊 `/data/finance-apps` 已退役)。
> 共用網路名改為 **`appnet`**、host 名維持 `postgres`;資料卷沿用 `finance-apps_pg-data`(內含 firefly/n8n/mops/hexagram)。

**重要關聯**:hexagram 連的是 `/opt/database` 的 postgres(外部網路 `appnet`,host 名 `postgres`)。**先起 database(postgres + appnet),再起 hexagram**。

### 啟動順序
```bash
# 1) 先起獨立 postgres(建立 appnet 網路)
cd /opt/database && docker compose up -d

# 2) 再起 hexagram 後端 + 其他 app
cd /opt/hexagram && docker compose up -d
cd /opt/apps && docker compose up -d

# 3) 驗證
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/        # 預期 200
```
> 多數 restart policy 是 `unless-stopped`,開機通常會自動拉起;若沒有就照上面手動起。

### 停止(收工用)
```bash
cd /opt/hexagram && docker compose stop          # 只停命果後端
# postgres 視需要:cd /opt/database && docker compose stop
```

## 二、程式碼狀態(都已 commit + push,工作區乾淨)

| Repo | 路徑 | 最新 commit |
|---|---|---|
| 後端 + Web | `/opt/hexagram` | `625bcf3`(加 /api/v1/daily) |
| App(RN/Expo) | `/opt/hexagram-app` | `246a5b3`(v3 build 修正:圖示去 @3x) |

- 線上後端 `https://hexagram.johnsonwebsites.cc` **已含今天所有新功能**(daily/reading/chat/reflection/果實)——App 連的是它,不是 localhost。
- 本機 Docker(localhost:8080)是給 Web 測試用;App 不靠它。

## 三、Android App 打包(EAS)— 未完成,接續這裡

- EAS 專案:`@johnsonku/hexagram-app`(projectId 已寫進 app.json)。
- eas-cli 用 `npx -y eas-cli@latest`(未全域安裝)。需要 `EXPO_TOKEN`(見下)。
- **Build D = v3 暖紫金版,送出時 in progress**(跑在 EAS 雲端,重開機不影響)。
  - 頁面:https://expo.dev/accounts/johnsonku/projects/hexagram-app/builds/d86c7052-088f-49f6-a041-3aa4cff8b905
  - 查狀態 / 取 APK:
    ```bash
    cd /opt/hexagram-app
    export EXPO_TOKEN=<你的token>
    npx -y eas-cli@latest build:list --limit 1 --non-interactive | grep -iE "Status|Application Archive URL"
    ```
  - 重新打包(若要):`npx -y eas-cli@latest build -p android --profile preview --non-interactive --no-wait`
- 已建好的舊 APK(功能完整,但**不是 v3 視覺**)備用:
  `https://expo.dev/artifacts/eas/oHHczgsLmbT_ZldPuHZD41tw1ST6QFcwZCt42zC-Bws.apk`

### ⚠️ EXPO_TOKEN
打包用的 Expo access token 不存在 repo(安全)。重開機後若要再打包/查 build,需重新提供;**確認 build D OK 後建議到 expo.dev → Account settings → Access tokens 撤銷舊的**。

## 四、目前進度 / 待續

- ✅ 解卦改人生教練式(Mingo 1.0,prompt v2.0)+ 繼續聊 + 🌱成長反思,兩平台都做完。
- ✅ App MVP v1.0:果實改名、3-tab(中央凸起)、首頁今日指引、黃曆卡、Splash 同意書。
- ✅ App 視覺套 **Production Resources v3**(暖紫金、新 App icon、tile 圖示、山景、背景)。
- ⏳ **Build D(v3)** 等建完驗收。
- **待辦(暫緩,使用者指示)**:6 遊客模式(+AI 每日 5 次,待討論)、7 Apple/Google 登入(待憑證)、購買果實(待綠界金流);Email 回訪每日排程(需設 `CRON_TOKEN` + 打 `/api/v1/reflections/dispatch_reminders`);App icon 圓形遮罩若被裁可做去背前景圖;Web 是否跟進 v3 暖紫金色票。
- 開新對話先讀:後端 `docs/WORKLOG.md`、App `hexagram-app/WORKLOG.md`。
