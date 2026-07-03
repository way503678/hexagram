# 命卦排盤 — 檔案清單與 raw URL

**Repo**:https://github.com/way503678/hexagram
**Branch**:main
**Raw URL base**:`https://raw.githubusercontent.com/way503678/hexagram/main/`
**GitHub 網頁 base**:`https://github.com/way503678/hexagram/blob/main/`

---

## 使用方式

### 跟 Claude 開工
複製下方「全檔清單」或挑你要的檔,貼到對話開頭,例如:

```
來改健康規則:
https://raw.githubusercontent.com/way503678/hexagram/main/divination/aspects/health.py
https://raw.githubusercontent.com/way503678/hexagram/main/fortune_engine.py
```

### 在 GitHub 網頁編輯
把上面 raw URL 的 `raw.githubusercontent.com` 換成 `github.com`、把 `/main/` 換成 `/blob/main/`,或直接從 repo 首頁點進去。

---

## 全檔清單

> ⚠️ **此清單為快照、會過時**(2026-07-03 校對過一輪)。實際檔案以 repo 為準:`git ls-files`。
> raw URL 規則固定:`https://raw.githubusercontent.com/way503678/hexagram/main/<路徑>`,
> 清單沒列到的檔案照這個規則組 URL 即可。

### Python 核心(根目錄,7 檔)

| 檔案 | raw URL |
|---|---|
| app.py | https://raw.githubusercontent.com/way503678/hexagram/main/app.py |
| db.py | https://raw.githubusercontent.com/way503678/hexagram/main/db.py |
| core_data.py | https://raw.githubusercontent.com/way503678/hexagram/main/core_data.py |
| hexagram_data.py | https://raw.githubusercontent.com/way503678/hexagram/main/hexagram_data.py |
| hexagram_engine.py | https://raw.githubusercontent.com/way503678/hexagram/main/hexagram_engine.py |
| fortune_data.py | https://raw.githubusercontent.com/way503678/hexagram/main/fortune_data.py |
| fortune_engine.py | https://raw.githubusercontent.com/way503678/hexagram/main/fortune_engine.py |

### divination/ 模組(11 檔)

#### divination/ 根目錄

| 檔案 | raw URL |
|---|---|
| __init__.py | https://raw.githubusercontent.com/way503678/hexagram/main/divination/__init__.py |

#### divination/aspects/(四面向判讀,5 檔)

| 檔案 | raw URL |
|---|---|
| __init__.py | https://raw.githubusercontent.com/way503678/hexagram/main/divination/aspects/__init__.py |
| health.py | https://raw.githubusercontent.com/way503678/hexagram/main/divination/aspects/health.py |
| love.py | https://raw.githubusercontent.com/way503678/hexagram/main/divination/aspects/love.py |
| wealth.py | https://raw.githubusercontent.com/way503678/hexagram/main/divination/aspects/wealth.py |
| work.py | https://raw.githubusercontent.com/way503678/hexagram/main/divination/aspects/work.py |

#### divination/core/(核心邏輯,7 檔)

| 檔案 | raw URL |
|---|---|
| __init__.py | https://raw.githubusercontent.com/way503678/hexagram/main/divination/core/__init__.py |
| elements.py | https://raw.githubusercontent.com/way503678/hexagram/main/divination/core/elements.py |
| hidden.py(伏神) | https://raw.githubusercontent.com/way503678/hexagram/main/divination/core/hidden.py |
| signals.py | https://raw.githubusercontent.com/way503678/hexagram/main/divination/core/signals.py |
| traits.py | https://raw.githubusercontent.com/way503678/hexagram/main/divination/core/traits.py |
| trigger.py | https://raw.githubusercontent.com/way503678/hexagram/main/divination/core/trigger.py |
| yongshen.py(用神) | https://raw.githubusercontent.com/way503678/hexagram/main/divination/core/yongshen.py |

### 模板 templates/(9 檔)

| 檔案 | raw URL |
|---|---|
| base.html | https://raw.githubusercontent.com/way503678/hexagram/main/templates/base.html |
| landing.html(首頁) | https://raw.githubusercontent.com/way503678/hexagram/main/templates/landing.html |
| cast.html(時辰起卦) | https://raw.githubusercontent.com/way503678/hexagram/main/templates/cast.html |
| manual.html(手動排卦) | https://raw.githubusercontent.com/way503678/hexagram/main/templates/manual.html |
| _hexagram_table.html(卦表) | https://raw.githubusercontent.com/way503678/hexagram/main/templates/_hexagram_table.html |
| admin/history_list.html | https://raw.githubusercontent.com/way503678/hexagram/main/templates/admin/history_list.html |
| admin/history_detail.html | https://raw.githubusercontent.com/way503678/hexagram/main/templates/admin/history_detail.html |
| admin/fortune.html(流年) | https://raw.githubusercontent.com/way503678/hexagram/main/templates/admin/fortune.html |

### 靜態檔 static/(1 檔)

| 檔案 | raw URL |
|---|---|
| style.css | https://raw.githubusercontent.com/way503678/hexagram/main/static/style.css |

### 文件 docs/(1 檔,新增 2026-05-26)

| 檔案 | raw URL |
|---|---|
| AI_INTERPRETER_MANUAL_PROMPT_v1.md(手動排卦 AI 解讀 prompt) | https://raw.githubusercontent.com/way503678/hexagram/main/docs/AI_INTERPRETER_MANUAL_PROMPT_v1.md |

### 部署相關(根目錄,8 檔)

| 檔案 | raw URL |
|---|---|
| Dockerfile | https://raw.githubusercontent.com/way503678/hexagram/main/Dockerfile |
| docker-compose.yml | https://raw.githubusercontent.com/way503678/hexagram/main/docker-compose.yml |
| requirements.txt | https://raw.githubusercontent.com/way503678/hexagram/main/requirements.txt |
| .dockerignore | https://raw.githubusercontent.com/way503678/hexagram/main/.dockerignore |
| .gitignore | https://raw.githubusercontent.com/way503678/hexagram/main/.gitignore |
| .env.example | https://raw.githubusercontent.com/way503678/hexagram/main/.env.example |
| README.md | https://raw.githubusercontent.com/way503678/hexagram/main/README.md |
| DEPLOY.md | https://raw.githubusercontent.com/way503678/hexagram/main/DEPLOY.md |

---

## 不在 GitHub 的檔案(僅伺服器有)

這些檔案存在於 `/opt/hexagram/`,但 `.gitignore` 擋掉或未追蹤,**Claude 抓不到,需要時你自己貼內容**:

| 檔案 | 位置 | 內容 |
|---|---|---|
| `.env` | `/opt/hexagram/.env` | 真實機密(SECRET_KEY, ADMIN_EMAILS, ANTHROPIC_API_KEY, RESEND_API_KEY) |
| `deploy.sh` | `/opt/hexagram/deploy.sh` | 自動部署腳本 |
| cron 設定 | `crontab -l` | 每分鐘觸發 deploy.sh |

---

## 常用情境快速複製

### 改健康規則

```
來改健康規則:
https://raw.githubusercontent.com/way503678/hexagram/main/divination/aspects/health.py
https://raw.githubusercontent.com/way503678/hexagram/main/fortune_engine.py
```

### 改感情規則

```
來改感情規則:
https://raw.githubusercontent.com/way503678/hexagram/main/divination/aspects/love.py
https://raw.githubusercontent.com/way503678/hexagram/main/fortune_engine.py
```

### 改首頁設計

```
來改首頁:
https://raw.githubusercontent.com/way503678/hexagram/main/templates/landing.html
https://raw.githubusercontent.com/way503678/hexagram/main/static/style.css
```

### 改路由 / 後端邏輯

```
來改路由:
https://raw.githubusercontent.com/way503678/hexagram/main/app.py
```

### 改卦表顯示

```
來改卦表:
https://raw.githubusercontent.com/way503678/hexagram/main/templates/_hexagram_table.html
https://raw.githubusercontent.com/way503678/hexagram/main/hexagram_engine.py
```

### 改 DB schema

```
來改 DB:
https://raw.githubusercontent.com/way503678/hexagram/main/db.py
```

### 改伏神 / 用神邏輯

```
來改伏神用神:
https://raw.githubusercontent.com/way503678/hexagram/main/divination/core/hidden.py
https://raw.githubusercontent.com/way503678/hexagram/main/divination/core/yongshen.py
https://raw.githubusercontent.com/way503678/hexagram/main/fortune_engine.py
```

### 改手動排卦 AI 解讀

```
來改手動排卦 AI 解讀:
https://raw.githubusercontent.com/way503678/hexagram/main/docs/AI_INTERPRETER_MANUAL_PROMPT_v1.md
https://raw.githubusercontent.com/way503678/hexagram/main/templates/manual.html
https://raw.githubusercontent.com/way503678/hexagram/main/app.py
```

---

## 維護注意事項

### 新增檔案後要更新這份 markdown

如果未來在 repo 加了新檔(例如 `divination/aspects/career.py`),記得:

1. 把新檔的 raw URL 加進這份清單
2. 上傳新版到 Project Knowledge(替換舊版)

### 刪除檔案後也要更新

從 repo 刪檔後,把對應 URL 從這份清單拿掉,避免 Claude 抓到 404。

### 確認某檔案存不存在

瀏覽器打開 raw URL,看得到內容 = 存在;404 = 不存在或路徑錯。

---

## 補充:伺服器自動部署狀態

- **GitHub repo**:public,可直接 web_fetch
- **伺服器 cron**:每分鐘跑 `/opt/hexagram/deploy.sh`
- **部署 log**:`/var/log/hexagram-deploy.log`
- **流程**:Commit GitHub → 1 分鐘內伺服器自動 `git pull` + `docker compose up -d --build`

---

*產生於 2026-05-26,當新增/刪除檔案時請手動更新此檔。*
*最後更新:2026-05-26 加入 docs/ 目錄與手動排卦 AI 解讀檔案。*
