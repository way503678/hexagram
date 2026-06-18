# 命卦排盤專案 — 工作紀錄 / 背景速覽

> **用途**:開新對話時固定先讀這份,快速接上專案背景、已完成事項與待辦。
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

1. **白話詳盡、卦理精簡**:給外行人看的白話要講透(舉例、講因果);卦理判斷本身用條列短句。
2. **誠實但建設地鼓勵**:卦象吉凶**強度照引擎、不淡化不誇大**;只改語氣與收尾——阻力翻成「可留意/可準備/可著力之處」,結尾給正面、賦能的鼓勵。**不是美化卦象**。
3. **依吉凶展開、扣著問題**:越明顯吉/凶就多解釋;每個重點回扣「對你問的這件事代表什麼」,把同一問題講深,不延伸別話題。
4. **空亡/旺衰白話化**:空亡≈時機未到、力量未到位,待出空填實才使得上力。
5. **世應/用神依月令、日令判強弱**:月令=`四柱.月`地支、日令=`四柱.日`地支;月令為主、日令次之。
6. **不下成敗斷言、不代決定、不超出問事**;性別關係詞中性化。
7. **版本表寫在 `===== PROMPT 開始/結束 =====` marker 之外**(不會被送進 AI);loader 只認「獨立成行」的 marker。

## 四、工作日誌(新到舊)

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
