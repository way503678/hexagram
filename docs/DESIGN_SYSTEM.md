# 命果 MINGO — 設計系統(Design System / 單一真實來源)

> App 與 Web **共用同一套設計語言**(色票、字體、圓角、元件命名一致),只是版型隨螢幕做 RWD 調整。
> 本文件為唯一基準。改風格先改這裡,再同步到 `hexagram-app/src/theme.ts` 與 `hexagram/static/style.css`。
> ⚠️ **舊風格已廢除**:原本 Web 的「朱紅 + 水墨書卷風」(深紅 `#8b0000`、宣紙米黃、印章、金線)與 App 舊紫米色票,**一律移除**,不再沿用。命理判讀用的功能色(五行/世應/動爻/紫白/擇日吉凶)不在此限,維持正確性。

## 品牌
- 名稱:**命果 MINGO**(中文「命果」+ 英文 wordmark「MINGO」大寫、字距 4–8)。
- 調性:溫暖、正向、柔和、現代命理生活感。低飽和紫色系、米白底、大圓角、柔和陰影、漸層、星點裝飾。
- 標語:看懂變化・走向更好的自己 / Know the change, walk your path.

## 色票(Design Tokens)
| 用途 | Token | Hex |
|------|-------|-----|
| 主色(深紫藍) | `primaryDark` | `#2B2D42` |
| 次色(中紫) | `primary` | `#5E548E` |
| 強調(亮紫) | `accent` | `#A78BFA` |
| 點綴(金黃) | `gold` | `#F6BD60` |
| 背景(米白) | `bgLight` | `#F7F4EE` |
| 卡片白 | `surface` | `#FFFFFF` |
| 主文字 | `text` | `#2B2D42`(= primaryDark) |
| 次要文字 | `textMuted` | `#8E8AA3` |
| 分隔線 | `borderSoft` | `#E8E4DC` |

漸層:
- 深紫卡:`#5E548E → #2B2D42`
- 亮紫卡:`#A78BFA → #5E548E`
- 淺底:`#F7F4EE → #FFFFFF`

## 圓角 / 間距
- radius:`sm 12` / `md 16` / `lg 20` / `pill 999`
- spacing:`xs 4` / `sm 8` / `md 16` / `lg 24` / `xl 32`
- 陰影(soft):柔和、低透明度,例 `0 6px 20px rgba(43,45,66,0.08)`

## 字體 / 排版
- 中文標題:纖細襯線(Noto Serif TC Light)。
- 英文品牌字 MINGO:大寫 + `letterSpacing` 4–8。
- 內文:無襯線(Noto Sans TC)。
- 字級:標題 28 / 卦名 32 / 區塊標題 18 / 內文 15 / 次要 13。

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
