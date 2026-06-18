---
name: deploy-verify
description: 改完 hexagram 後端(程式 / 模板 / prompt)後,安全地重建容器並驗證上線。當被要求「部署」「重建」「讓改動生效」「上線」,或剛改完 app.py / templates / docs 的 prompt 檔需要驗證時使用。
---

# hexagram 後端：部署 + 驗證流程

hexagram 後端跑在 Docker(容器名 `hexagram`、埠 `8080`、工作目錄 `/opt/hexagram`)。
**prompt 與模板在程式啟動時載入,所以任何改動都要重建容器才生效。**
標準流程:**改完 → 先做靜態檢查 → 重建 → 等 healthy → 驗證載入 → commit**。

## 0. 關鍵事實

- 容器名 `hexagram`,本機網址 `http://localhost:8080`。
- 另有 sidecar `hexagram-db-backup`(每日備份),部署時**只重建 hexagram**:`docker compose up -d --build hexagram`。
- prompt 檔:`docs/AI_INTERPRETER_MANUAL_PROMPT_v1.md`(手動解卦)、`docs/AI_FORTUNE_PROMPT_v1.md`(流年宜忌)。
  - 真正送進 AI 的內容,是 `===== PROMPT 開始 =====` 與 `===== PROMPT 結束 =====` 兩個 marker **之間**的文字。
  - loader(`app._load_prompt_md`)只認**獨立成行**的 marker,所以檔頭說明文字裡提到 marker 字串沒關係。
  - **版本表 / 設計說明放在 marker 之外**,才不會被送進 AI。

## 1. 靜態檢查(依改了什麼)

**改了 Jinja 模板(`templates/*.html`)**:
```bash
cd /opt/hexagram
python3 -c "from jinja2 import Environment, FileSystemLoader; \
Environment(loader=FileSystemLoader('templates')).parse(open('templates/<檔名>').read()); print('語法 OK')"
```

**改了 prompt(`docs/*.md`)** — 確認新內容會被擷取、版本表不外洩:
```bash
cd /opt/hexagram
python3 - <<'PY'
def load(fn):
    lines=open('docs/'+fn,encoding='utf-8').read().splitlines()
    si=ei=-1
    for i,ln in enumerate(lines):
        if si<0 and ln.strip()=="===== PROMPT 開始 =====": si=i
        elif si>=0 and ln.strip()=="===== PROMPT 結束 =====": ei=i; break
    return "\n".join(lines[si+1:ei]).strip()
p=load("AI_INTERPRETER_MANUAL_PROMPT_v1.md")
print("新內容在 prompt 內:", "<你剛加的關鍵字>" in p)
print("版本表外洩:", "| v" in p and "2026-" in p)   # 應為 False
PY
```

## 2. 重建 + 等健康

```bash
cd /opt/hexagram
docker compose up -d --build hexagram
for i in $(seq 1 12); do
  s=$(docker inspect -f '{{.State.Health.Status}}' hexagram 2>/dev/null)
  [ "$s" = healthy ] && { echo healthy; break; }; sleep 2
done
```

## 3. 驗證載入(依改了什麼)

**模板** — 抓頁面確認改動真的在(必要時帶登入狀態;admin-only 區塊未登入抓不到屬正常):
```bash
curl -s http://localhost:8080/<路由> | grep -c '<預期字串>'
```

**prompt** — 進容器確認運作中載入的就是新版、版本表沒外洩:
```bash
docker exec hexagram python -c "
import app
m=app._MANUAL_AI_PROMPT or ''; f=app._FORTUNE_AI_PROMPT or ''
print('manual 含新內容:', '<關鍵字>' in m)
print('版本表外洩:', 'v1.' in m)   # 應為 False
"
```

## 4. commit（使用者要求才 commit / push）

- 直接 commit 到 `main`(此專案慣例,個人 repo)。
- commit message 用中文、貼合既有風格,結尾加:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **push 只在使用者明確說要**:`git push origin main`。

## 完成後

把「做了什麼 + 結論」追加到 `docs/WORKLOG.md` 的工作日誌,並更新待辦(這份是開新對話固定要讀的背景檔)。
