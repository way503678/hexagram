# 命果 MINGO — 設計系統(Design System / 單一真實來源)

> App 與 Web **共用同一套設計語言**(色票、字體、圓角、元件命名一致),只是版型隨螢幕做 RWD 調整。
> 本文件為唯一基準。改風格先改這裡,再同步到 `hexagram-app/src/theme.ts` 與 `hexagram/static/style.css`。
> ⚠️ **舊風格已廢除**:原本 Web 的「朱紅 + 水墨書卷風」(深紅 `#8b0000`、宣紙米黃、印章、金線)與 App 舊紫米色票,**一律移除**,不再沿用。命理判讀用的功能色(五行/世應/動爻/紫白/擇日吉凶)不在此限,維持正確性。

## 品牌
- 名稱:**命果 MINGO**(中文「命果」+ 英文 wordmark「MINGO」大寫、字距 4–8)。
- 調性:溫暖、平靜、療癒、引導內心。暖米色底 + 靜謐藍紫主色 + 微光金點綴,大圓角、柔和陰影、漸層、星點裝飾。
- 標語:看懂變化・走向更好的自己 / Know the change, walk your path.

## 色票(Design Tokens)
| 用途 | Token | Hex |
|------|-------|-----|
| 主色(深墨紫) | `primaryDark` | `#2C2942` |
| 主色(靜謐紫) | `primary` | `#6F5E9B` |
| 強調(漸層淺端) | `accent` | `#8A79B3` |
| 點綴(微光金) | `gold` | `#E9B34A` |
| 背景(暖米) | `bgLight` | `#F1E9DC`(漸層主調) |
| 卡片白 | `surface` | `#FFFFFF` |
| 標題文字 | `text` | `#2C2942`(= primaryDark) |
| 內文文字 | `body` | `#5D5675` |
| 次要文字 | `textMuted` | `#6B6385` |
| 弱化標籤 / latin | `faint` | `#8C84A6` |
| 導覽未選 | `navIdle` | `#9A93AD` |
| 分隔線 | `borderSoft` | `rgba(120,104,160,0.16)` |

漸層:
- 頁面背景(上→下暖米,180deg):`#F5EFE4 → #F1E9DC → #E9E0D2`
- 主按鈕(135deg):`#8A79B3 → #6F5E9B`
- 霧面卡(160deg):`rgba(255,253,250,.85) → rgba(232,226,240,.78)`
- 深紫卡:`#6F5E9B → #2C2942`

## 圓角 / 間距
- radius:`sm 14` / `md 18` / `btn 22` / `card/lg 26` / `pill 999`
- spacing:`xs 4` / `sm 8` / `md 16` / `lg 24` / `xl 32`
- 陰影:卡片 `0 14px 34px rgba(95,82,135,.2)`;按鈕 `0 6px 16px rgba(111,94,155,.35)`
  - (Web `--shadow-soft` 全站通用版略淡:`0 10px 30px rgba(95,82,135,.14)`)

## 字體 / 排版
- 中文:思源黑體 **Noto Sans TC**(400/500/700/900),標題與內文皆用,**不另用襯線**。
- latin 標語 / MINGO 字樣:**Cormorant Garamond 500**(App 走 `@expo-google-fonts/cormorant-garamond`、Web 走 Google Fonts `<link>`);大寫 + `letterSpacing` 6–8。
- 字級:問候 30/900 · 區段標題 26/900 · 卡片標題 17/900 · 內文 15/500 · 次要 14/500 · 導覽標籤 11/700。

## 共用元件(命名 App ↔ Web 一致)
| 元件 | 說明 |
|------|------|
| `GradientCard` | 可指定漸層方向/色票的圓角卡(App: expo-linear-gradient;Web: CSS linear-gradient) |
| `SectionCard` | 白底圓角卡(soft 陰影) |
| `PillTag` | 膠囊分類標籤(選中態填色) |
| `PrimaryButton` / `GhostButton` | 主要 / 次要按鈕,樣式一致 |
| `IconRow` | 左 icon + 標題 + 右值(幸運方向/色/數字) |
| `StarDecor` | 星點 / 火花裝飾(點綴) |
| `HexagramGlyph` | 卦象六爻圖(6 位 0/1,陰爻斷、陽爻連) |
| `ScreenHeader` | 返回鍵 + 置中標題 + 右側 icon |

## 平台對應
- **App**:tokens 放 `src/theme.ts`(MINGO 區段);維持 React Navigation + StyleSheet(不改 Expo Router/NativeWind)。
- **Web**:tokens 放 `static/style.css` 的 `:root` CSS 變數;Flask/Jinja 模板沿用。
- RWD 斷點(Web,Tailwind 預設):base<640 / sm≥640 / md≥768(雙欄) / lg≥1024(置中 max-w-6xl) / xl≥1280。

## 功能色(命理用,**不受換膚影響**,務必保留)
五行(木綠/火紅/土褐/金黃/水藍)、世(綠)應(藍)動爻(朱)、紫白飛星九色、擇日吉凶(大吉…大凶)、天干五行色。這些是判讀依據,維持既有定義。
