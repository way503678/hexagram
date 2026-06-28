# -*- coding: utf-8 -*-
"""
命果 MINGO Flask 網頁介面

路由總覽:
  /                  首頁(landing page)
  /cast              時辰起卦(梅花易數)
  /manual            手動排卦(金錢卦/搖卦結果)
  /manual/ai_prompt  手動排卦 AI 解讀 prompt 組裝(管理員專用,POST)
  /admin/login       管理員登入
  /admin/logout      登出
  /admin/history     管理:姓名清單
  /admin/history/<name>                            管理:某人的命盤清單
  /admin/history/<name>/delete/<id>  (POST)        管理:刪除單筆命盤
  /admin/history/<name>/fortune                    管理:某命盤的流年分析
"""
import os
import json
import time
import hmac
import hashlib
import base64
import re
from functools import wraps
from datetime import datetime, timezone, timedelta

from flask import (
    Flask, request, render_template, session, redirect, url_for, abort,
    Response, jsonify, stream_with_context, g,
)
from werkzeug.security import generate_password_hash, check_password_hash

from hexagram_engine import (
    cast_hexagram, cast_hexagram_manual, analyze_chart_aspects,
)
from fortune_engine import analyze_fortune
from core_data import BRANCH_ELEMENT
import db

# 啟動時初始化 DB
db.init_db()

app = Flask(__name__)

# Session 設定:cookie 在瀏覽器關閉時自動失效
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "change-this-secret-in-production-please"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


@app.after_request
def _api_cors(resp):
    """為 /api/ 與 /manual/ai_reading 加上 CORS 標頭。

    原生 app 不受瀏覽器 CORS 限制,但 Expo web 預覽(localhost)會跨網域呼叫,
    需要這些標頭。開放 * 沒問題:排盤 API 免費且純運算,解盤仍需登入。
    """
    if request.path.startswith("/api/") or request.path == "/manual/ai_reading":
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return resp

# 管理員身分:由 ADMIN_EMAILS 環境變數列出(逗號分隔)。
#   名單內的 email 用一般帳號註冊/登入後,即自動擁有最高權限。
#   要新增/移除管理員只要改這個環境變數,不需要改程式或資料庫。
ADMIN_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("ADMIN_EMAILS", "").split(",")
    if e.strip()
}


def _email_is_admin(email):
    """email 是否在管理員名單內。"""
    return bool(email) and email.strip().lower() in ADMIN_EMAILS


# ============================================================
# 會員登入 token(JWT / HS256)
#   App 為跨網域呼叫的獨立程式,改用 Authorization: Bearer <token> 認身分,
#   不依賴瀏覽器 cookie session。token 用既有 SECRET_KEY 以 HMAC-SHA256 簽章,
#   不需額外套件。token 內只放 user id 與到期時間,驗章 + 未過期即視為有效。
# ============================================================
# token 有效天數(逾期須重新登入)
TOKEN_TTL_DAYS = int(os.environ.get("TOKEN_TTL_DAYS", "30"))
# 新會員註冊時贈送的點數(方便在 App 上實測解盤流程;設 0 可關閉)
NEW_USER_BONUS = int(os.environ.get("NEW_USER_BONUS", "3"))
# 密碼最短長度(政策:至少 8 碼、且英數混合)
_MIN_PASSWORD_LEN = 8
# 連續登入失敗達此次數即鎖定帳號(需管理員解鎖)
LOGIN_MAX_FAILS = int(os.environ.get("LOGIN_MAX_FAILS", "3"))
# 個資同意書 + 免責聲明的條文版本(改版時更新,會記在會員的 consent_version)
CONSENT_VERSION = os.environ.get("CONSENT_VERSION", "2026-06-17")
# 流年宜忌解讀(進階功能)每次扣的點數
FORTUNE_AI_COST = int(os.environ.get("FORTUNE_AI_COST", "1"))
# 解讀後「繼續聊」每則訊息扣的點數(教練式對話;0 = 免費)
CHAT_AI_COST = int(os.environ.get("CHAT_AI_COST", "1"))
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _token_secret():
    """token 簽章金鑰(跟著 SECRET_KEY 走;金鑰若改變,既有 token 全部失效)。"""
    return app.config["SECRET_KEY"].encode("utf-8")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user_id):
    """簽發一個會員 token(JWT/HS256),內含 uid 與到期時間。"""
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"uid": int(user_id), "iat": now, "exp": now + TOKEN_TTL_DAYS * 86400}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    sig = hmac.new(_token_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return signing_input + "." + _b64url(sig)


def verify_token(token):
    """驗證 token,成功回傳 user_id(int),失敗(簽章錯/過期/格式錯)回傳 None。"""
    try:
        signing_input, sig_b64 = token.rsplit(".", 1)
        expected = hmac.new(
            _token_secret(), signing_input.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64url(expected), sig_b64):
            return None
        _, payload_b64 = signing_input.split(".")
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return int(payload["uid"])
    except Exception:
        return None


# --- 重設密碼 token(無資料表;用 SECRET_KEY + 該帳號目前密碼雜湊 簽章) ---
# 一旦改了密碼,雜湊變了 → 舊連結自動失效(一次性)。預設 1 小時到期。
RESET_TTL_SECONDS = int(os.environ.get("RESET_TTL_SECONDS", "3600"))


def _reset_secret(pwhash):
    return (app.config["SECRET_KEY"] + "|pwreset|" + (pwhash or "")).encode("utf-8")


def make_reset_token(uid, pwhash):
    payload = {"uid": int(uid), "exp": int(time.time()) + RESET_TTL_SECONDS}
    si = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(_reset_secret(pwhash), si.encode("ascii"), hashlib.sha256).digest()
    return si + "." + _b64url(sig)


def verify_reset_token(token):
    """成功回傳 uid,失敗(過期/簽章錯/密碼已改/格式錯)回 None。"""
    try:
        si, sig_b64 = token.rsplit(".", 1)
        payload = json.loads(_b64url_decode(si))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        uid = int(payload["uid"])
        pwhash = db.get_password_hash(uid)
        if not pwhash:
            return None
        expected = hmac.new(_reset_secret(pwhash), si.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url(expected), sig_b64):
            return None
        return uid
    except Exception:
        return None


def _send_via_resend(to_email, subject, body):
    """走 Resend HTTP API 寄信(stdlib,無額外套件)。成功回 True。"""
    import json
    import urllib.request
    import urllib.error
    key = os.environ.get("RESEND_API_KEY")
    sender = os.environ.get("MAIL_FROM") or os.environ.get("RESEND_FROM", "")
    if not sender:
        app.logger.warning("Resend:未設定 MAIL_FROM(寄件人),改走 SMTP")
        return None
    payload = json.dumps({
        "from": sender,
        "to": [to_email],
        "subject": subject,
        "text": body,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Cloudflare 會擋預設的 Python-urllib UA(error 1010),帶一個正常 UA
            "User-Agent": "hexagram-mailer/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            app.logger.info("Resend 已送出 → %s (id=%s)", to_email, data.get("id"))
            return True
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        app.logger.warning("Resend 寄信失敗 HTTP %s:%s", e.code, detail)
        return False
    except Exception as e:
        app.logger.warning("Resend 寄信失敗 (%s: %s)", type(e).__name__, e)
        return False


def _send_mail(to_email, subject, body):
    """寄信(供應商無關)。優先用 Resend API,其次 SMTP;皆未設定則只寫 log 回 False。"""
    # 1) 有設 RESEND_API_KEY → 走 Resend HTTP API
    if os.environ.get("RESEND_API_KEY"):
        ok = _send_via_resend(to_email, subject, body)
        if ok is not None:       # None = 設定不全(缺寄件人),往下退回 SMTP
            return ok
    # 2) 退回標準 SMTP(含 Resend SMTP:smtp.resend.com)
    host = os.environ.get("SMTP_HOST")
    if not host:
        app.logger.warning("寄信未設定(無 RESEND_API_KEY 也無 SMTP_HOST);信件(僅 log) → %s | %s", to_email, subject)
        return False
    import smtplib
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ.get("MAIL_FROM") or os.environ.get("SMTP_USER", "")
    msg["To"] = to_email
    msg.set_content(body)
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=15) as s:
            s.starttls()
            user = os.environ.get("SMTP_USER")
            if user:
                s.login(user, os.environ.get("SMTP_PASS", ""))
            s.send_message(msg)
        return True
    except Exception as e:
        app.logger.warning("寄信失敗 (%s: %s)", type(e).__name__, e)
        return False


def _send_reset_email(to_email, link):
    # 開發用:未設寄信(Resend/SMTP 皆無)時把連結寫進 log,才有辦法測試重設流程
    if not os.environ.get("RESEND_API_KEY") and not os.environ.get("SMTP_HOST"):
        app.logger.warning("寄信未設定;重設連結(僅 log):%s", link)
    return _send_mail(
        to_email, "命果 MINGO — 重設密碼",
        "您好,\n\n請點以下連結重設密碼(1 小時內有效):\n"
        f"{link}\n\n若非您本人申請,請忽略本信(您的密碼不會被改動)。",
    )


def _send_password_changed_notice(to_email):
    """密碼變更/重設後的安全通知,讓本人能及早發現被盜。"""
    if not to_email:
        return
    _send_mail(
        to_email, "命果 MINGO — 您的密碼已變更",
        "您好,\n\n您的帳號密碼剛剛被變更(或透過忘記密碼重設)。\n"
        "若這是您本人操作,可忽略本信。\n"
        "若非您本人,代表帳號可能遭冒用,請立即重設密碼並檢查您的 Email 安全。",
    )


def _do_forgot(email):
    """email 存在就產生重設連結並寄信。不回傳是否存在(防帳號列舉)。"""
    email = (email or "").strip().lower()
    row = db.get_email_user(email)
    if row and row.get("password_hash"):
        token = make_reset_token(row["id"], row["password_hash"])
        base = os.environ.get("PUBLIC_BASE_URL") or request.url_root.rstrip("/")
        _send_reset_email(email, f"{base}/reset?token={token}")


def _user_id_from_request():
    """從 Authorization: Bearer <token> 取出已驗證的 user_id(沒有則 None)。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return verify_token(auth[7:].strip())
    return None


def _login_at_from_request():
    """本次登入時間:App 用 token 的 iat、網頁用 session['login_at']。
    回傳 ISO 字串或 None。"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            signing_input = auth[7:].strip().rsplit(".", 1)[0]
            _, payload_b64 = signing_input.split(".")
            payload = json.loads(_b64url_decode(payload_b64))
            iat = payload.get("iat")
            if iat:
                return datetime.fromtimestamp(int(iat), timezone.utc).isoformat()
        except Exception:
            pass
    return session.get("login_at")


def _log_question_event(user, data, chart_payload=None):
    """記一筆卜卦問事紀錄。只在「使用 AI」(產生 Prompt / AI 解盤)時呼叫。

    data 需含 y/m/d/h/yao_vals/aspect/question(與排盤 API 相同格式)。
    chart_payload:呼叫端若已算好卦象可傳入,避免重算;None 則自行計算。
    需登入會員才記;同會員 20 秒內相同問題+卦象會自動去重(見 db 層)。
    """
    if not user:
        return
    try:
        if chart_payload is None:
            chart_payload, _err = _compute_chart(data)
        chart = (chart_payload or {}).get("卦象") or {}
        yv = data.get("yao_vals")
        yao_str = "|".join(str(x) for x in yv) if isinstance(yv, (list, tuple)) else None
        db.log_divination_question(
            user_id=user["id"],
            user_email=user.get("email"),
            login_at=_login_at_from_request(),
            question=(data.get("question") or "").strip()[:500],
            ben_gua=(chart.get("本卦") or {}).get("卦名"),
            bian_gua=(chart.get("變卦") or {}).get("卦名"),
            moving_lines=(chart.get("動爻") or {}).get("描述"),
            yao_vals=yao_str,
            cast_dt=(chart_payload or {}).get("排盤時間"),
        )
    except Exception as e:  # 記錄失敗絕不影響主流程
        app.logger.warning("log question event failed (%s: %s)",
                           type(e).__name__, e)


def _public_user(user):
    """整理成可回傳給前端的會員資料(不含 password_hash;時間轉字串)。"""
    if not user:
        return None
    created = user.get("created_at")
    return {
        "id": user.get("id"),
        "auth_provider": user.get("auth_provider"),
        "display_name": user.get("display_name"),
        "email": user.get("email"),
        "points_balance": user.get("points_balance", 0),
        "is_admin": _email_is_admin(user.get("email")),
        "gender": user.get("gender"),
        "birth_y": user.get("birth_y"), "birth_m": user.get("birth_m"),
        "birth_d": user.get("birth_d"), "birth_h": user.get("birth_h"),
        "created_at": created.isoformat() if hasattr(created, "isoformat") else created,
    }


# ============================================================
# AI 解讀 prompt 載入(啟動時讀進記憶體)
# ============================================================
def _load_prompt_md(filename):
    """從 docs/<filename> 擷取「===== PROMPT 開始/結束 =====」之間的純 prompt 內容。"""
    candidates = [
        os.path.join(os.path.dirname(__file__), "docs", filename),
        "/app/docs/" + filename,
    ]
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                full = f.read()
            start_marker = "===== PROMPT 開始 ====="
            end_marker = "===== PROMPT 結束 ====="
            # 只比對「獨立成行」的 marker,避開說明文字裡同時提到兩個 marker 的句子
            lines = full.splitlines()
            si = ei = -1
            for i, ln in enumerate(lines):
                if si < 0 and ln.strip() == start_marker:
                    si = i
                elif si >= 0 and ln.strip() == end_marker:
                    ei = i
                    break
            if si >= 0 and ei > si:
                # 取兩個 marker「之間」的內容(不含 marker 本身)
                core = "\n".join(lines[si + 1: ei]).strip()
                return core
            # 沒有 marker 就回傳整檔
            return full.strip()
        except Exception as e:
            print(f"[AI prompt] 讀取失敗 {path}: {e}")
    return None


_MANUAL_AI_PROMPT = _load_prompt_md("AI_INTERPRETER_MANUAL_PROMPT_v1.md")
_FORTUNE_AI_PROMPT = _load_prompt_md("AI_FORTUNE_PROMPT_v1.md")
if _MANUAL_AI_PROMPT is None:
    print("[AI prompt] 警告:找不到手動排卦 prompt 檔,AI 解讀會回 500。")
if _FORTUNE_AI_PROMPT is None:
    print("[AI prompt] 警告:找不到流年 prompt 檔,流年解讀會回 500。")


def admin_required(view):
    """裝飾器:要求已登入且為管理員(email 在 ADMIN_EMAILS 名單內)。

    未登入 → 導去登入頁;已登入但非管理員 → 403。
    """
    @wraps(view)
    def wrapper(*a, **kw):
        user = current_user()
        if not user:
            return redirect(url_for("login_page", next=request.path))
        if not user.get("is_admin"):
            abort(403)
        return view(*a, **kw)
    return wrapper


_UNSET = object()


def current_user():
    """回傳目前登入會員 dict(含 points_balance、is_admin)或 None。

    同一個 request 內會快取(flask.g):一次請求常會多次呼叫(裝飾器 + 路由 +
    模板 context),快取後只查一次 DB,結果完全相同。
    """
    cached = getattr(g, "_cached_user", _UNSET)
    if cached is not _UNSET:
        return cached
    user = _resolve_current_user()
    g._cached_user = user
    return user


def _resolve_current_user():
    """實際解析目前登入會員。

    身分來源依序:
      1. Authorization: Bearer <token>(App / API 會員,Email/社群登入皆走這條)
      2. 網頁會員 session 的 user_id(cookie)
    管理員不另設帳號:回傳的 dict 會依 ADMIN_EMAILS 名單補上 is_admin 旗標。
    """
    def _augment(u):
        if u:
            u["is_admin"] = _email_is_admin(u.get("email"))
        return u

    # 1. App / API:Authorization: Bearer <token>
    uid = _user_id_from_request()
    if uid:
        u = db.get_user(uid)
        if u:
            return _augment(u)
    # 2. 網頁會員:登入後存在 session 的 user_id(cookie)
    sid = session.get("user_id")
    if sid:
        u = db.get_user(sid)
        if u:
            return _augment(u)
    return None


@app.context_processor
def _inject_current_user():
    """讓所有模板都能用 current_user(顯示登入狀態 / 會員選單)。"""
    return {"current_user": current_user()}


@app.context_processor
def _inject_asset_version():
    """靜態檔版本號(用 style.css 的 mtime),讓 CSS 連結在改版後自動繞過快取。
    順帶把流年解讀點數成本給模板顯示。"""
    try:
        v = int(os.path.getmtime(os.path.join(app.static_folder, "style.css")))
    except OSError:
        v = 1
    return {"asset_version": v, "fortune_ai_cost": FORTUNE_AI_COST}


def _get_field(name, default=""):
    """從 POST form 或 GET query 取單一欄位(POST 優先)。"""
    if request.method == "POST":
        return request.form.get(name, default)
    return request.args.get(name, default)


def _parse_dt_args():
    """從 form/query 取年月日時,缺者以現在補齊。"""
    y = _get_field("y", "").strip()
    m = _get_field("m", "").strip()
    d = _get_field("d", "").strip()
    h = _get_field("h", "").strip()
    now = datetime.now()
    default_y, default_m, default_d, default_h = now.year, now.month, now.day, now.hour
    return y, m, d, h, default_y, default_m, default_d, default_h


# ============================================================
# 首頁(landing page)
# ============================================================
@app.route("/", methods=["GET"])
def landing():
    return render_template("landing.html", mode="landing")


@app.route("/fortune", methods=["GET"])
def fortune_page():
    """公開流年分析:依出生 y/m/d/h + gender + 流年 year(免登入)。"""
    now = datetime.now()
    try:
        y_i = int(request.args["y"])
        m_i = int(request.args["m"])
        d_i = int(request.args["d"])
        h_i = int(request.args["h"])
    except (KeyError, TypeError, ValueError):
        return render_template(
            "admin/fortune.html", mode="fortune", fortune=None,
            error="缺少出生年月日時參數(y/m/d/h)",
            fortune_year=now.year, fortune_chart_args={"y": "", "m": "", "d": "", "h": ""},
            chart_gender=None, detail_name=None, public=True,
            fortune_form_action="/fortune",
        )
    try:
        year_i = int(request.args.get("year", now.year))
    except ValueError:
        year_i = now.year
    gender = (request.args.get("gender", "") or "").strip().upper()
    gender = db.norm_gender(gender)

    fortune = None
    error = None
    try:
        fortune = analyze_fortune(datetime(y_i, m_i, d_i, h_i, 0), year_i, gender=gender)
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    return render_template(
        "admin/fortune.html", mode="fortune",
        fortune=fortune, fortune_year=year_i,
        fortune_chart_args={"y": y_i, "m": m_i, "d": d_i, "h": h_i},
        chart_gender=gender, detail_name=None, public=True,
        fortune_form_action="/fortune", error=error,
    )


@app.route("/almanac", methods=["GET"])
def almanac_page():
    """萬年曆(紫白飛星):月曆視圖,公開。"""
    from divination import almanac
    now = datetime.now()
    try:
        y = int(request.args.get("y") or now.year)
        m = int(request.args.get("m") or now.month)
        if not (1 <= m <= 12 and 1900 <= y <= 2100):
            raise ValueError
    except (TypeError, ValueError):
        y, m = now.year, now.month
    data = almanac.month_info(y, m)
    prev_y, prev_m = (y - 1, 12) if m == 1 else (y, m - 1)
    next_y, next_m = (y + 1, 1) if m == 12 else (y, m + 1)
    return render_template(
        "almanac.html", mode="almanac", data=data, y=y, m=m,
        prev_y=prev_y, prev_m=prev_m, next_y=next_y, next_m=next_m,
        today=now.strftime("%Y-%m-%d"),
    )


# ============================================================
# 公開:時辰起卦
# ============================================================
@app.route("/cast", methods=["GET"])
def cast():
    y, m, d, h, default_y, default_m, default_d, default_h = _parse_dt_args()
    client_name = request.args.get("name", "").strip()
    gender = db.norm_gender(request.args.get("gender", "").strip().upper()) or ""

    if not (y or m or d or h):
        y_i, m_i, d_i, h_i = default_y, default_m, default_d, default_h
        has_explicit_input = False
    else:
        y_i = int(y) if y else default_y
        m_i = int(m) if m else default_m
        d_i = int(d) if d else default_d
        h_i = int(h) if h != "" else default_h
        has_explicit_input = True

    result = None
    error = None
    try:
        dt = datetime(y_i, m_i, d_i, h_i, 0)
        result = cast_hexagram(dt)
    except ValueError as e:
        error = f"日期時間格式錯誤({e})"
    except KeyError as e:
        error = f"查無資料:{e}"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    # 寫入 DB:要有姓名且使用者主動送出表單才寫
    is_view_only = request.args.get("view") == "1"
    if result is not None and has_explicit_input and client_name and not is_view_only:
        db.log_divination(client_name, y_i, m_i, d_i, h_i, gender=gender or None)

    return render_template(
        "cast.html",
        mode="solar",
        r=result,
        client_name=client_name,
        gender=gender,
        y=y or str(default_y), m=m or str(default_m),
        d=d or str(default_d), h=(h if h != "" else str(default_h)),
        default_y=default_y, default_m=default_m,
        default_d=default_d, default_h=default_h,
        error=error,
    )


# ============================================================
# 公開:手動排卦
# 同時接受 GET / POST:
#   - POST(表單送出):從 request.form 取參數,網址保持乾淨的 /manual
#   - GET(直接開頁):從 request.args 取參數,維持向下相容
# ============================================================
@app.route("/manual", methods=["GET", "POST"])
def manual():
    y, m, d, h, default_y, default_m, default_d, default_h = _parse_dt_args()

    # 性別 & 問事類別
    gender = db.norm_gender(_get_field("gender", "").strip().upper()) or ""
    aspect = _get_field("aspect", "all").strip().lower()
    if aspect not in ("all", "love", "health", "work", "wealth"):
        aspect = "all"

    # 所問之事(管理員先填、擲卦後保留供 AI 解讀使用)
    question = (_get_field("question", "") or "").strip()
    if len(question) > 500:
        question = question[:500]

    yao_vals = []
    has_yao_input = False
    for i in range(6):
        v = _get_field(f"y{i}", "")
        if v:
            has_yao_input = True
        yao_vals.append(v or "1,0")

    result = None
    aspects_result = None
    error = None
    if has_yao_input:
        try:
            lines  = []
            moving = []
            for i in range(6):
                parts = yao_vals[i].split(",")
                if len(parts) != 2:
                    raise ValueError(f"第{i+1}爻格式錯誤:{yao_vals[i]}")
                lines.append(int(parts[0]))
                moving.append(int(parts[1]))

            if y or m or d or h:
                y_i = int(y) if y else default_y
                m_i = int(m) if m else default_m
                d_i = int(d) if d else default_d
                h_i = int(h) if h != "" else default_h
                dt_obj = datetime(y_i, m_i, d_i, h_i, 0)
            else:
                dt_obj = datetime(default_y, default_m, default_d, default_h, 0)

            result = cast_hexagram_manual(lines, moving, dt_obj)

            # 四面向判讀
            aspects_result = analyze_chart_aspects(
                result, dt_obj,
                gender=gender or None,
                aspect_choice=aspect,
            )
        except ValueError as e:
            error = f"輸入格式錯誤({e})"
        except KeyError as e:
            error = f"查無資料:{e}"
        except Exception as e:
            error = f"{type(e).__name__}: {e}"

    # 注意:起卦(排盤)本身不記錄;只有實際「使用 AI」(產生 Prompt / AI 解盤)
    # 才會在對應端點寫紀錄,見 _log_question_event。
    return render_template(
        "manual.html",
        mode="manual",
        member=current_user(),
        r=result, yao_vals=yao_vals,
        aspects=aspects_result,
        gender=gender,
        aspect_choice=aspect,
        question=question,
        y=y or str(default_y), m=m or str(default_m),
        d=d or str(default_d), h=(h if h != "" else str(default_h)),
        default_y=default_y, default_m=default_m,
        default_d=default_d, default_h=default_h,
        error=error,
    )


# ============================================================
# 公開(僅管理員):手動排卦 AI 解讀 prompt 組裝
# ============================================================
# AI 解盤使用的模型(可由環境變數覆寫)
# 2026-06-20:Opus 4.8 → 改回 Sonnet 4.6。對打評估:取用神兩 model 皆 6/6 平手;
# 之前 Opus 領先的「元神、世應生剋」已搬進引擎(回歸測試證明),不再靠 model。
# 準確度兩者已等同 → 取 Sonnet 省約 4 成成本(只差一點文筆精煉度)。
_AI_READING_MODEL = os.environ.get("AI_READING_MODEL", "claude-sonnet-4-6")


def _compute_chart(data):
    """從 data 解析日期/六爻/問事類別 → 重排盤,組出可序列化的卦象 payload。

    回傳 (chart_payload, err):
      成功 → err 為 None;chart_payload 為含「卦象/旬空/對六爻」的 dict。
      失敗 → (None, (error_dict, status_code))。
    純確定性運算(不呼叫任何外部 API),供網頁解讀與 REST API 共用。
    """
    try:
        y_i = int(data.get("y") or datetime.now().year)
        m_i = int(data.get("m") or datetime.now().month)
        d_i = int(data.get("d") or datetime.now().day)
        h_i = int(data.get("h") or datetime.now().hour)
    except (TypeError, ValueError):
        return None, ({"error": "日期時間格式錯誤"}, 400)

    yao_vals = data.get("yao_vals") or []
    if len(yao_vals) != 6:
        return None, ({"error": "需要 6 個爻的資料"}, 400)

    try:
        lines = []
        moving = []
        for i, v in enumerate(yao_vals):
            parts = str(v).split(",")
            if len(parts) != 2:
                raise ValueError(f"第{i+1}爻格式錯誤:{v}")
            lines.append(int(parts[0]))
            moving.append(int(parts[1]))
    except (ValueError, TypeError) as e:
        return None, ({"error": f"爻格式錯誤:{e}"}, 400)

    aspect = (data.get("aspect") or "all").strip().lower()
    if aspect not in ("all", "love", "health", "work", "wealth"):
        aspect = "all"

    try:
        dt_obj = datetime(y_i, m_i, d_i, h_i, 0)
        chart = cast_hexagram_manual(lines, moving, dt_obj)
        chart_payload = _enrich_chart_payload(chart, dt_obj, aspect)
    except Exception as e:
        return None, ({"error": f"排盤失敗:{type(e).__name__}: {e}"}, 500)
    return chart_payload, None


def _yao_wangshuai(element, month_branch, day_branch):
    """依月令、日令算單一五行的旺衰(引擎確定性計算,讓 AI 免自推五行、不會算錯)。

    回傳:月令/日令各自的十二長生與三級旺衰,加「綜合旺衰」(月令權重加倍、日令次之)。
    綜合等級:旺 / 偏旺 / 持平 / 偏弱 / 弱。空亡、動爻化剋等另由既有訊號處理,不在此。
    """
    from divination.core.elements import twelve_phase, strength_tier
    if not element or not month_branch or not day_branch:
        return None
    m_phase, m_tier = twelve_phase(element, month_branch), strength_tier(element, month_branch)
    d_phase, d_tier = twelve_phase(element, day_branch), strength_tier(element, day_branch)
    _w = {"旺": 1, "中": 0, "弱": -1}
    score = _w.get(m_tier, 0) * 2 + _w.get(d_tier, 0)  # 月令為主(×2)、日令次之
    overall = ("旺" if score >= 2 else "偏旺" if score == 1 else
               "持平" if score == 0 else "偏弱" if score == -1 else "弱")
    return {
        "月令": {"地支": month_branch, "長生": m_phase, "旺衰": m_tier},
        "日令": {"地支": day_branch, "長生": d_phase, "旺衰": d_tier},
        "綜合旺衰": overall,
    }


def _fei_fu_relation(fu_element, fei_element):
    """飛神(本爻)與伏神的生剋關係 + 古法名稱與吉凶(確定性,讓 AI 免自推、不記錯)。

    四象(《卜筮正宗》):伏剋飛=出暴(吉,能出)、飛生伏=得長生(吉,得助)、
    伏生飛=洩氣(凶,難出)、飛剋伏=傷身(凶,最難出);比和=得助(吉)。
    註:此僅飛伏生剋一項,伏神能否真出尚須合看伏神旺衰、飛神空破休囚、日辰沖飛等。
    """
    from divination.core.elements import element_relation
    if not fu_element or not fei_element:
        return None
    rel = element_relation(fu_element, fei_element)  # 從「伏神」角度看「飛神」
    table = {
        "我剋": ("伏剋飛", "出暴", "吉"),   # 伏神剋飛神
        "生我": ("飛生伏", "得長生", "吉"),  # 飛神生伏神
        "我生": ("伏生飛", "洩氣", "凶"),   # 伏神生飛神
        "剋我": ("飛剋伏", "傷身", "凶"),   # 飛神剋伏神
        "比和": ("飛伏比和", "比和", "吉"),
    }
    if rel not in table:
        return None
    rel_name, classic, jixiong = table[rel]
    return {"關係": rel_name, "古名": classic, "吉凶": jixiong}


# 五行墓庫地支 — 入墓偵測用。**與引擎十二長生表一致**:土寄火(火土同論)
# → 金墓丑、木墓未、水墓辰、火墓戌、土墓戌。不可改用水土同論(辰),否則與旺衰矛盾。
_MU_BRANCH = {"金": "丑", "木": "未", "水": "辰", "火": "戌", "土": "戌"}

# 地支六合 + 對沖(應期推算用)
_ZHI_ORDER = "子丑寅卯辰巳午未申酉戌亥"
_LIUHE = {"子": "丑", "丑": "子", "寅": "亥", "亥": "寅", "卯": "戌", "戌": "卯",
          "辰": "酉", "酉": "辰", "巳": "申", "申": "巳", "午": "未", "未": "午"}


def _chong_zhi(branch):
    """回傳地支的對沖支(相隔 6 位);非地支回空字串。"""
    return _ZHI_ORDER[(_ZHI_ORDER.index(branch) + 6) % 12] if branch in _ZHI_ORDER else ""


def _yingqi_candidates(zhi, states, day_branch):
    """依用神爻當下狀態,給「候選應期日」(地支 + 緣由)。增刪卜易·應期總注章。

    確定性:只列「逢值/逢沖/出空/填實/合/沖墓」等候選日地支,實際以哪個為準
    仍須配合卦象(屬判讀),故回傳候選清單供 AI 擇取,不下定論。
    """
    if not zhi:
        return []
    out = []
    chong = _chong_zhi(zhi)

    def add(b, why):
        if b and not any(c["應日地支"] == b for c in out):
            out.append({"應日地支": b, "緣由": why})

    rumu = states.get("入墓") or []
    if states.get("空亡"):
        add(zhi, "出空:值本支之日")
        add(chong, "沖空填實之日")
    elif states.get("月破"):
        add(zhi, "填實:值本支之日(或出本月)")
    elif rumu:
        if "臨墓" in rumu:
            add(chong, "沖開墓庫之日")
        if "日墓" in rumu:
            add(_chong_zhi(day_branch), "沖開日墓之日")
    elif states.get("動爻"):
        add(_LIUHE.get(zhi), "合住之日(動逢合則待沖而應)")
        add(zhi, "動爻值日")
    else:  # 靜而無病
        add(zhi, "用神值日")
        add(chong, "沖用神(暗動)之日")
    return out


def _sanhe_signals(yao_branches):
    """掃卦中六爻地支,偵測三合局/半合/虛拱待補(純資訊,不下吉凶)。

    成局=三支齊;半合=有帝旺支+另一支(真半合);虛拱=生墓兩支缺帝旺(待補帝旺支)。
    待補支可作應期(該支值日或動出而成局)。增刪卜易·六合章。
    """
    from divination.core.elements import _SANHE_HUAI
    bset = set(b for b in yao_branches if b)
    out = []
    for group, wang in _SANHE_HUAI.items():
        present = [z for z in group if z in bset]
        if len(present) < 2:
            continue
        missing = [z for z in group if z not in bset]
        if len(present) == 3:
            kind = "成局"
        elif wang in present:
            kind = "半合(有帝旺)"
        else:
            kind = "虛拱(待帝旺支)"
        out.append({
            "組": group, "局五行": BRANCH_ELEMENT.get(wang, ""),
            "類型": kind, "已現": present, "待補": missing,
        })
    return out


def _enrich_chart_payload(chart, dt_obj, aspect):
    """卦象 + 排盤時間 → 算 aspects/旬空/對六爻,組出可序列化 payload。

    手動排卦與時辰起卦共用,確保 app 兩種模式拿到的卦象結構一致。
    可能丟例外(由呼叫端決定錯誤回應)。
    """
    aspects = analyze_chart_aspects(
        chart, dt_obj, gender=None, aspect_choice=aspect,
    )

    # 旬空(空亡):由日干支查表得出,純確定值,直接餵給 AI 免自算
    _GAN = "甲乙丙丁戊己庚辛壬癸"
    _ZHI = "子丑寅卯辰巳午未申酉戌亥"
    _gz = chart.get("日干支", "")
    xun_kong = []
    if len(_gz) >= 2 and _gz[0] in _GAN and _gz[1] in _ZHI:
        _base = (_ZHI.index(_gz[1]) - _GAN.index(_gz[0])) % 12
        xun_kong = [_ZHI[(_base + 10) % 12], _ZHI[(_base + 11) % 12]]
    _kong_set = set(xun_kong)

    # 月令、日令的地支(判旺衰用):月支取四柱月柱、日支取日干支
    _month_branch = ((chart.get("四柱") or {}).get("月") or "  ")[1:2]
    _day_branch = _gz[1:2]

    # 月破:爻地支正是「月支的對沖」者(沖=地支相隔 6 位)。純干支可定。
    _yuepo_branch = _ZHI[(_ZHI.index(_month_branch) + 6) % 12] if _month_branch in _ZHI else ""
    # 日辰所沖之支(暗動/日破偵測用)
    _ribo_branch = _ZHI[(_ZHI.index(_day_branch) + 6) % 12] if _day_branch in _ZHI else ""

    from divination.core.yongshen import get_dong_direction
    from divination.core.elements import (
        twelve_phase as _twelve_phase,
        element_relation as _elrel,
        branch_relation as _brel,
    )

    # 世爻基準(算「對世關係」用):用神對世、世應之間都相對世爻,交引擎算免 AI 自推
    _shi = next((x for x in (aspects.get("對六爻", []) or []) if x.get("世")), None)
    _shi_ele = (_shi or {}).get("五行", "")
    _shi_zhi = (_shi or {}).get("地支", "")
    _SK2SHI = {"我生": "生世", "我剋": "剋世", "生我": "世生", "剋我": "世剋", "比和": "比和"}
    _HC2SHI = {"相合": "合世", "相沖": "沖世"}

    # 神煞(元神/忌神/仇神,相對世爻):引擎已在本卦爻算好,併入對六爻,
    # 之後本卦/變卦的爻陣列即可從 AI payload 砍掉(對六爻為超集)。
    _shensha = {}
    for _by in ((chart.get("本卦") or {}).get("爻") or []):
        _ss = _by.get("神煞") or ""
        if _ss:
            _shensha[_by.get("爻序index")] = _ss

    liu_yao = []
    for _e in (aspects.get("對六爻", []) or []):
        _e2 = dict(_e)
        _e2["空亡"] = _e.get("地支") in _kong_set
        _e2["月破"] = bool(_yuepo_branch) and _e.get("地支") == _yuepo_branch
        _ss = _shensha.get(_e.get("爻序index"))
        if _ss:
            _e2["神煞對世"] = _ss  # 元神=生世 / 忌神=剋世 / 仇神=生忌神(相對世爻)
        # 對世關係(生世/剋世/世生/世剋/比和 + 合世/沖世):引擎算,AI 只讀不自推
        if not _e.get("世") and _shi_ele:
            _dui_shi = {}
            _sk = _SK2SHI.get(_elrel(_e.get("五行"), _shi_ele), "")
            if _sk:
                _dui_shi["生剋"] = _sk
            _hc = _HC2SHI.get(_brel(_e.get("地支"), _shi_zhi), "")
            if _hc:
                _dui_shi["合沖"] = _hc
            if _dui_shi:
                _e2["對世"] = _dui_shi
        # 旺衰交給引擎算(十二長生,確定性),AI 只翻白話、不自推五行
        _ws = _yao_wangshuai(_e.get("五行"), _month_branch, _day_branch)
        if _ws:
            _e2["旺衰"] = _ws

        # ---- 確定性狀態(增刪卜易/黃金策;batch 3-6)----
        _tier = (_ws or {}).get("綜合旺衰", "")
        _is_dong = bool(_e.get("動爻"))
        _zhi = _e.get("地支")
        # B2 真空/假空:旺或動為假空(待出空仍有用),休囚靜為真空
        if _e2["空亡"]:
            _e2["空亡性質"] = "假空" if (_tier in ("旺", "偏旺") or _is_dong) else "真空"
        # E1 暗動/日破:靜爻被日辰沖 → 旺=暗動(雖靜實動)、衰=日破(沖散無用)
        if (not _is_dong) and _ribo_branch and _zhi == _ribo_branch:
            _e2["日沖"] = "暗動" if _tier in ("旺", "偏旺", "持平") else "日破"
        # H1 入墓:臨墓(自臨墓庫支)、日墓(日辰為其墓庫)
        _mu = _MU_BRANCH.get(_e.get("五行"))
        if _mu:
            _rumu = []
            if _zhi == _mu:
                _rumu.append("臨墓")
            if _day_branch == _mu:
                _rumu.append("日墓")
            if _rumu:
                _e2["入墓"] = _rumu
        # D/I 動化方向(批1修正版)+ 爻反吟(動而化沖,主反覆)
        if _is_dong:
            _dir = get_dong_direction(_e)
            if _dir and _dir != "靜":
                _e2["動化方向"] = _dir
            _bian = (_e.get("動爻出去") or {}).get("地支")
            if _bian and _zhi in _ZHI and _bian == _ZHI[(_ZHI.index(_zhi) + 6) % 12]:
                _e2["動化反吟"] = True
            # G2 化空/化墓/化絕(看變爻地支對本爻五行的狀態)
            if _bian:
                _hua = []
                if _bian in _kong_set:
                    _hua.append("化空")
                _bph = _twelve_phase(_e.get("五行"), _bian)
                if _bph == "墓":
                    _hua.append("化墓")
                elif _bph == "絕":
                    _hua.append("化絕")
                if _hua:
                    _e2["動化變爻狀態"] = _hua
        # L 應期候選(依本爻狀態給候選日地支 + 緣由,供 AI 擇取)
        _e2["應期候選"] = _yingqi_candidates(_zhi, _e2, _day_branch)
        # 伏神:引擎補上五行、旺衰、與飛神(本爻)的生剋(出暴/長生/洩氣/傷身)
        _fei_ele = _e.get("五行")  # 本爻即飛神
        _fu_list = _e.get("伏神") or []
        if _fu_list:
            _new_fu = []
            for _fu in _fu_list:
                _f2 = dict(_fu)
                _fu_ele = BRANCH_ELEMENT.get(_fu.get("地支"), "")
                if _fu_ele:
                    _f2["五行"] = _fu_ele
                    _f2["空亡"] = _fu.get("地支") in _kong_set
                    _f2["月破"] = bool(_yuepo_branch) and _fu.get("地支") == _yuepo_branch
                    _fws = _yao_wangshuai(_fu_ele, _month_branch, _day_branch)
                    if _fws:
                        _f2["旺衰"] = _fws
                    _ff = _fei_fu_relation(_fu_ele, _fei_ele)
                    if _ff:
                        _f2["飛伏生剋"] = _ff
                _new_fu.append(_f2)
            _e2["伏神"] = _new_fu
        liu_yao.append(_e2)

    return {
        "schema_version": 2,
        "排盤時間": dt_obj.strftime("%Y-%m-%d %H:00"),
        "問事類別": aspect,
        "卦象": chart,
        "月令": {"地支": _month_branch, "五行": BRANCH_ELEMENT.get(_month_branch, "")},
        "日令": {"地支": _day_branch, "五行": BRANCH_ELEMENT.get(_day_branch, "")},
        "月破地支": _yuepo_branch,
        "三合": _sanhe_signals([e.get("地支") for e in liu_yao]),
        "旬空": xun_kong,
        "對六爻": liu_yao,
    }


def _slim_payload_for_ai(payload):
    """產生送 AI 的精簡卦象 JSON(只瘦身,不改網頁用的原 payload)。

    砍掉與「對六爻」100% 重複的本卦/變卦爻陣列(神煞已併入對六爻),
    以及顯示用欄位(卦辭/公曆/農曆/時辰/起卦法)。保留卦名、卦宮、四柱、
    卦變總論、月令日令、三合、旬空、對六爻等全部判讀資料。約省 1,360 token。
    """
    import copy
    p = copy.deepcopy(payload)
    ch = p.get("卦象") or {}
    for g in ("本卦", "變卦"):
        if isinstance(ch.get(g), dict):
            ch[g].pop("爻", None)
            ch[g].pop("卦辭", None)
    for k in ("公曆", "農曆", "時辰", "起卦法"):
        ch.pop(k, None)
    p.pop("schema_version", None)
    p.pop("排盤時間", None)
    return p


# ============================================================
# 每日運勢(六爻終身卦流日):命卦對「今日干支」算,世爻為軸,純規則、零 AI。
# 定位為「每日參考」,非鐵口斷語(忠於六爻法則 + 誠實標參考)。
# 判斷標準(查證來源,見 CLASSICS / 六爻六大規律):
#   - 日辰為一日之主宰:生扶世爻=順、刑沖克害=逆
#   - 用神/世爻旺衰:旺相吉、休囚空破弱
#   - 各六親被日辰沖/剋 → 該生活面向今日被觸動;六神定其性質
# ============================================================
_LIUSHEN_HINT = {
    "青龍": "偏正向、喜慶、人緣財喜",
    "朱雀": "口舌、文書、訊息與爭論",
    "勾陳": "遲滯、拖延、田土房產、慢性糾纏",
    "螣蛇": "反覆、虛驚、心緒不寧、怪異瑣事",
    "白虎": "意外、衝突、血光、開刀傷病、口角",
    "玄武": "暗事、遺失、盜竊、曖昧、心思不定",
}
_LIUQIN_ASPECT = {
    "妻財": "錢財、收入、開銷",
    "官鬼": "工作、壓力、人際是非",
    "父母": "長輩、文件合約、車子房子、奔波",
    "子孫": "身體健康、心情、孩子晚輩",
    "兄弟": "朋友同輩、花費、競爭",
}


def analyze_daily(ming_chart, today_dt):
    """以命卦(終身卦)對「今日干支」算每日運勢——六爻流日、世爻為軸、純規則。

    回傳 dict:今日干支、本命世爻今日狀態、總評(白話)、面向提醒、定位語。
    """
    from divination.core.elements import element_relation, branch_relation
    _GAN = "甲乙丙丁戊己庚辛壬癸"
    _ZHI = "子丑寅卯辰巳午未申酉戌亥"

    # 今日干支:用今日起一張卦,只為取四柱/日干支(純確定值)
    tchart = cast_hexagram(today_dt)
    _sz = tchart.get("四柱") or {}
    t_month = (_sz.get("月") or "  ")[1:2]
    t_daygz = tchart.get("日干支", "")
    t_day = t_daygz[1:2]
    t_day_ele = BRANCH_ELEMENT.get(t_day, "")

    # 今日旬空
    t_kong = set()
    if len(t_daygz) >= 2 and t_daygz[0] in _GAN and t_daygz[1] in _ZHI:
        _b = (_ZHI.index(t_daygz[1]) - _GAN.index(t_daygz[0])) % 12
        t_kong = {_ZHI[(_b + 10) % 12], _ZHI[(_b + 11) % 12]}

    yao = (ming_chart.get("本卦") or {}).get("爻") or []
    shi = next((y for y in yao if y.get("世")), None)

    # 全程白話,不露任何術語(世爻/日辰/六親/旺衰/干支一律翻成口語)
    overall, status = [], ""
    if shi:
        s_ele, s_zhi = shi.get("五行"), shi.get("地支")
        s_ws = (_yao_wangshuai(s_ele, t_month, t_day) or {}).get("綜合旺衰", "")
        rel = element_relation(s_ele, t_day_ele)  # 從世看今日:生我=今日助你…
        hc = branch_relation(s_zhi, t_day)
        _SHI_REL = {
            "生我": "今天外在的助力比較多,容易遇到幫忙、有貴人,做事順、心情也比較穩。",
            "我生": "今天你比較會付出、為別人忙,容易累一點,也要留意說話、別惹口舌。",
            "剋我": "今天壓力和阻力偏多,容易卡關、覺得累,放慢腳步、別硬撐就好。",
            "我剋": "今天你想主動掌控、把事情往前推,動力不錯,但別跟人硬碰、太過強勢。",
            "比和": "今天大致平穩,自己狀態還可以,留意一下同輩或合作之間的拉扯。",
        }
        if _SHI_REL.get(rel):
            overall.append(_SHI_REL[rel])
        if hc == "相沖":
            overall.append("今天比較動盪、容易奔波或心緒不寧,計畫可能有變動,順著走、別強求。")
        elif hc == "相合":
            overall.append("今天容易被人或事牽絆、放不太開,或有合作、牽連的事情。")
        # 整體狀態(把旺衰翻成白話,放最前面當一句總綱)
        if s_zhi in t_kong:
            status = "今天比較使不上力、提不起勁,適合緩一緩、別急著衝。"
        elif s_ws in ("弱", "偏弱"):
            status = "今天精神和底氣比較弱,適合養精蓄銳、別逞強。"
        elif s_ws in ("旺", "偏旺"):
            status = "今天整體狀態不錯,精神和底氣都在,可以好好把握。"
        else:
            status = "今天整體狀態平穩。"

    # 各面向:今天比較容易出狀況的生活面向(被沖或被剋的六親),全白話
    aspects, seen = [], set()
    for y in yao:
        if y.get("世"):
            continue
        lq, z, ele, ls = y.get("六親"), y.get("地支"), y.get("五行"), y.get("六神", "")
        hc = branch_relation(z, t_day)
        touched = (hc == "相沖") or (element_relation(ele, t_day_ele) == "剋我")
        if touched and lq not in seen:
            seen.add(lq)
            hint = _LIUSHEN_HINT.get(ls, "")
            aspects.append(
                f"「{_LIUQIN_ASPECT.get(lq, lq)}」方面今天比較容易有狀況"
                + (f",留意{hint}。" if hint else ",可以多留意一下。")
            )

    return {
        "日期": today_dt.strftime("%Y/%m/%d"),
        "整體狀態": status,
        "今日提醒": overall,
        "面向提醒": aspects,
        "定位": "這是依命盤推算的每日參考,給你一個方向,不是鐵口直斷;最終怎麼走,還是看你自己。",
        # 內部除錯用(不顯示給使用者)
        "_debug": {"今日干支": t_daygz, "世爻": (shi or {}).get("六親")},
    }


def _build_manual_reading(data):
    """從 POST data 解析、重排盤、組出 (系統規則文字, 問事+卦象JSON文字, 卦象payload)。

    回傳 (system_text, user_text, chart_payload, err):
      成功 → err 為 None;另外回傳 chart_payload 供呼叫端重用(免再算一次)。
      失敗 → (None, None, None, (error_dict, status_code))。
    驗證順序不變(先檢查所問之事,再排盤)。
    """
    if _MANUAL_AI_PROMPT is None:
        return None, None, None, ({"error": "伺服器未載入 prompt 檔案,請聯絡管理員"}, 500)

    question = (data.get("question") or "").strip()
    if not question:
        return None, None, None, ({"error": "請輸入所問之事"}, 400)
    if len(question) > 500:
        return None, None, None, ({"error": "所問之事超過 500 字"}, 400)

    chart_payload, err = _compute_chart(data)
    if err:
        return None, None, None, err

    # 送 AI 的 JSON 用精簡版(省 token、減雜訊);回傳的 chart_payload 仍為完整版(網頁/紀錄用)
    chart_json_str = json.dumps(
        _slim_payload_for_ai(chart_payload), ensure_ascii=False, separators=(",", ":")
    )
    user_text = (
        "【所問之事】\n" + question
        + "\n\n【卦象 JSON】\n```json\n" + chart_json_str + "\n```\n"
    )
    return _MANUAL_AI_PROMPT, user_text, chart_payload, None


def _prompt_and_charge(user, data):
    """產生 AI 解讀 Prompt:驗證 → 扣 1 點 → 記錄 → 回 prompt。web 與 api 共用。
    回傳 (body_dict, status_code);成功 body = {"prompt", "balance"}。"""
    system_text, user_text, chart_payload, err = _build_manual_reading(data)
    if err:
        return err  # (error_dict, status_code)
    ok, bal, msg = db.try_deduct_point(user["id"], 1, "prompt")
    if not ok:
        if msg == "insufficient":
            return ({"error": "點數不足,請先儲值",
                     "balance": user.get("points_balance", 0)}, 402)
        return ({"error": "系統忙線,請稍後再試"}, 503)
    _log_question_event(user, data, chart_payload=chart_payload)  # 使用 AI → 記錄
    return ({"prompt": system_text + "\n\n---\n\n" + user_text, "balance": bal}, 200)


# ============================================================
# 流年宜忌解讀(進階、扣點):引擎算四面向斷語 → AI 翻成白話宜忌
# ============================================================
def _build_fortune_reading(data):
    """從 data(出生 y/m/d/h + year + gender)算流年,組出 (系統規則, 流年JSON文字, err)。

    把引擎的「流年 + 四面向 + 12 流月四面向斷語」抽成精簡 JSON 餵給 AI;
    AI 只把這些既有判斷翻成白話宜忌(見 docs/AI_FORTUNE_PROMPT_v1.md)。
    """
    if _FORTUNE_AI_PROMPT is None:
        return None, None, ({"error": "伺服器未載入流年 prompt 檔案,請聯絡管理員"}, 500)
    try:
        y = int(data.get("y")); m = int(data.get("m"))
        d = int(data.get("d")); h = int(data.get("h"))
    except (TypeError, ValueError):
        return None, None, ({"error": "缺少出生年月日時(y/m/d/h)"}, 400)
    try:
        year = int(data.get("year") or datetime.now().year)
    except (TypeError, ValueError):
        year = datetime.now().year
    gender = db.norm_gender((data.get("gender") or "").strip().upper())
    try:
        result = analyze_fortune(datetime(y, m, d, h, 0), year, gender=gender)
    except Exception as e:
        return None, None, ({"error": f"流年分析失敗:{type(e).__name__}: {e}"}, 500)

    fy = result.get("流年", {}) or {}
    aspects = result.get("四面向", {}) or {}
    month_range = {mm.get("月名"): mm.get("區間") for mm in result.get("流月", []) or []}
    months = {}
    for mname, asp in (aspects.get("流月", {}) or {}).items():
        months[mname] = {"區間": month_range.get(mname, ""), **asp}

    payload = {
        "流年": {
            "西元": fy.get("西元"), "干支": fy.get("干支"),
            "卦名": fy.get("卦名") or (fy.get("本卦", {}) or {}).get("卦名"),
            "對世爻": fy.get("對世爻"), "對世爻合沖": fy.get("對世爻合沖"),
        },
        "性別": {"M": "男", "F": "女"}.get(gender, "未提供"),
        "四面向": aspects.get("流年", {}),
        "流月": months,
    }
    user_text = (
        "【流年盤與四面向斷語(請依此產生白話宜忌,勿自行新增命理)】\n```json\n"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + "\n```\n"
    )
    return _FORTUNE_AI_PROMPT, user_text, None


def _fortune_prompt_and_charge(user, data):
    """流年「產生 Prompt」:算流年 → 扣點 → 回 prompt。web 與 api 共用。"""
    system_text, user_text, err = _build_fortune_reading(data)
    if err:
        return err
    ok, bal, msg = db.try_deduct_point(user["id"], FORTUNE_AI_COST, "fortune")
    if not ok:
        if msg == "insufficient":
            return ({"error": "點數不足,請先儲值",
                     "balance": user.get("points_balance", 0)}, 402)
        return ({"error": "系統忙線,請稍後再試"}, 503)
    return ({"prompt": system_text + "\n\n---\n\n" + user_text, "balance": bal}, 200)


# ============================================================
# REST API (給 iOS app;JSON 進出。排盤確定性、免費、免登入)
# ============================================================
@app.route("/api/v1/health", methods=["GET"])
def api_health():
    """健康檢查 / app 連線測試。"""
    return jsonify({"status": "ok", "service": "hexagram", "version": 1})


# ============================================================
# 會員登入 API(App / Web 共用;回傳 token,後續請求帶 Bearer token)
#   /api/v1/auth/register  Email 註冊 → 回 token + 會員資料
#   /api/v1/auth/login     Email 登入 → 回 token + 會員資料
#   /api/v1/auth/me        憑 token 取目前會員資料
#   日後社群登入(Google/Apple/Line)各自加一個端點,驗證該家身分後
#   呼叫 db.get_or_create_user(provider, sub, ...) + make_token() 即可。
# ============================================================
# --- 註冊 / 登入共用核心(web 與 api 同一套,避免兩份各自維護) ---
def _password_error(password):
    """密碼政策檢查:至少 _MIN_PASSWORD_LEN 碼、且需英數混合。回傳 error_msg 或 None。"""
    p = password or ""
    if len(p) < _MIN_PASSWORD_LEN:
        return f"密碼至少需 {_MIN_PASSWORD_LEN} 個字"
    if not (re.search(r"[A-Za-z]", p) and re.search(r"\d", p)):
        return "密碼需英數混合(同時包含英文字母與數字)"
    return None


def _validate_credentials(email, password):
    """Email/密碼基本驗證。回傳 error_msg 或 None(通過)。"""
    if not _EMAIL_RE.match((email or "").strip().lower()):
        return "Email 格式不正確"
    return _password_error(password)


def _create_member(email, password, display_name):
    """建立 Email 會員 + 新會員贈點 + 記錄同意版本。
    回傳 (status, user|None):('ok', user) / ('exists', None) / ('error', None)。
    呼叫端負責平台專屬前置檢查(密碼再確認 / 勾選同意 / agreed)。"""
    pw_hash = generate_password_hash(password)
    status, user = db.create_email_user(
        (email or "").strip().lower(), pw_hash, display_name or None,
        consent_version=CONSENT_VERSION,
    )
    if status != "ok" or not user:
        return (status, None)
    # 新會員贈點(方便實測);失敗不影響註冊
    if NEW_USER_BONUS > 0:
        ok, _ = db.add_points(user["id"], NEW_USER_BONUS, "welcome_bonus")
        if ok:
            user = db.get_user(user["id"]) or user
    return ("ok", user)


def _login_member(email, password):
    """驗證 Email + 密碼。回傳 (user|None, status):
      status: "ok"(成功) / "locked"(帳號已鎖) / "bad"(帳號或密碼錯)。
    連續失敗達 LOGIN_MAX_FAILS 次會自動鎖定;成功則清失敗計數。
    """
    email = (email or "").strip().lower()
    if not email or not password:
        return (None, "bad")
    row = db.get_email_user(email)
    if not row or not row.get("password_hash"):
        return (None, "bad")
    if row.get("locked"):
        return (None, "locked")
    if not check_password_hash(row["password_hash"], password):
        now_locked = db.register_login_failure(row["id"], LOGIN_MAX_FAILS)
        return (None, "locked" if now_locked else "bad")
    if row.get("failed_logins"):
        db.reset_login_failures(row["id"])
    return (db.get_user(row["id"]) or row, "ok")


def _parse_birthday(get):
    """生日驗證(web/api 共用)。get(name) 回傳該欄原始值。

    回傳 (birth_tuple|None, errcode|None);errcode ∈ {'format','incomplete','invalid_date'}。
    四欄(年/月/日/時)要嘛全給合理值、要嘛全留空。錯誤訊息由呼叫端依 errcode 決定。
    """
    def _opt(name, lo, hi):
        v = get(name)
        if v is None or str(v).strip() == "":
            return None
        try:
            n = int(str(v).strip())
        except (TypeError, ValueError):
            return "ERR"
        return n if lo <= n <= hi else "ERR"

    vals = [_opt("birth_y", 1900, 2100), _opt("birth_m", 1, 12),
            _opt("birth_d", 1, 31), _opt("birth_h", 0, 23)]
    if "ERR" in vals:
        return None, "format"
    filled = [v is not None for v in vals]
    if any(filled) and not all(filled):
        return None, "incomplete"
    if all(filled):
        try:
            datetime(vals[0], vals[1], vals[2], vals[3], 0)
        except ValueError:
            return None, "invalid_date"
        return tuple(vals), None
    return None, None


@app.route("/api/v1/auth/register", methods=["POST"])
def api_auth_register():
    """Email 註冊。請求 {email, password, display_name?, agreed}。成功回 {token, user}。

    agreed 須為 true(代表已同意個資同意書 + 免責聲明),否則拒絕。
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or "").strip() or None

    err = _validate_credentials(email, password)
    if err:
        return jsonify({"error": err}), 400
    if not data.get("agreed"):
        return jsonify({"error": "請先同意個資使用同意書與免責聲明"}), 400

    status, user = _create_member(email, password, display_name)
    if status == "exists":
        return jsonify({"error": "這個 Email 已經註冊過了"}), 409
    if status != "ok" or not user:
        return jsonify({"error": "系統忙線,請稍後再試"}), 503

    token = make_token(user["id"])
    return jsonify({"token": token, "user": _public_user(user)})


@app.route("/api/v1/auth/login", methods=["POST"])
def api_auth_login():
    """Email 登入。請求 {email, password}。成功回 {token, user}。"""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not email or not password:
        return jsonify({"error": "請輸入 Email 與密碼"}), 400

    user, status = _login_member(email, password)
    if status == "locked":
        return jsonify({"error": "帳號已鎖定(連續登入失敗過多),請聯絡管理員解鎖"}), 403
    if not user:
        # 不分「帳號不存在」與「密碼錯」,避免洩漏哪些 email 已註冊
        return jsonify({"error": "Email 或密碼不正確"}), 401

    token = make_token(user["id"])
    return jsonify({"token": token, "user": _public_user(user)})


@app.route("/api/v1/auth/me", methods=["GET"])
def api_auth_me():
    """憑 Bearer token 取目前登入會員資料(含最新點數)。"""
    user = current_user()
    if not user:
        return jsonify({"error": "未登入或登入已逾期"}), 401
    return jsonify({"user": _public_user(user)})


@app.route("/api/v1/member/ledger", methods=["GET"])
def api_member_ledger():
    """目前會員的點數異動紀錄(新到舊)。"""
    user = current_user()
    if not user:
        return jsonify({"error": "未登入或登入已逾期"}), 401
    rows = db.list_ledger(user["id"])
    ledger = [{
        "delta": r["delta"],
        "balance_after": r["balance_after"],
        "reason": r["reason"],
        "ref": r["ref"],
        "created_at": r["created_at"].isoformat()
            if hasattr(r["created_at"], "isoformat") else r["created_at"],
    } for r in rows]
    return jsonify({"ledger": ledger})


@app.route("/api/v1/member/profile", methods=["POST"])
def api_member_profile():
    """更新會員資料(暱稱 + 生日)。請求 {display_name?, birth_y/m/d/h}。回 {user}。

    生日四欄要嘛全給(合理值)、要嘛全留空(null)。
    """
    user = current_user()
    if not user:
        return jsonify({"error": "未登入或登入已逾期"}), 401
    data = request.get_json(silent=True) or {}
    display_name = (data.get("display_name") or "").strip() or None
    gender = (data.get("gender") or "").strip().upper()
    gender = db.norm_gender(gender)

    birth, ecode = _parse_birthday(lambda n: data.get(n))
    if ecode:
        msg = {"format": "生日格式不正確",
               "incomplete": "生日請完整填寫年/月/日/時,或全部留空",
               "invalid_date": "這個生日日期不存在"}[ecode]
        return jsonify({"error": msg}), 400

    db.update_user_profile(user["id"], display_name=display_name,
                           gender=gender, birth=birth)
    updated = db.get_user(user["id"]) or user
    return jsonify({"user": _public_user(updated)})


# --- 修改密碼 / 刪除帳號 共用核心(web 與 api 同一套) ---
def _verify_current_password(user, password):
    """驗證登入會員輸入的「目前密碼」是否正確。"""
    row = db.get_email_user((user.get("email") or "").strip().lower())
    return bool(row and row.get("password_hash")
                and check_password_hash(row["password_hash"], password or ""))


def _change_password(user, current_pw, new_pw, new_pw2):
    """改密碼:驗目前密碼 → 檢查新密碼政策 + 兩次一致 → 更新。回傳 error_msg 或 None。"""
    if not _verify_current_password(user, current_pw):
        return "目前密碼不正確"
    if new_pw != new_pw2:
        return "兩次輸入的新密碼不一致"
    perr = _password_error(new_pw)
    if perr:
        return perr
    if not db.update_password(user["id"], generate_password_hash(new_pw)):
        return "系統忙線,請稍後再試"
    _send_password_changed_notice(user.get("email"))  # 安全通知
    return None


def _delete_account(user, password):
    """刪除帳號:需驗密碼。回傳 error_msg 或 None(成功時已刪)。"""
    if not _verify_current_password(user, password):
        return "密碼不正確"
    if not db.delete_user(user["id"]):
        return "系統忙線,請稍後再試"
    return None


@app.route("/api/v1/member/password", methods=["POST"])
def api_member_password():
    """修改密碼。請求 {current_password, new_password, new_password2}。"""
    user = current_user()
    if not user:
        return jsonify({"error": "未登入或登入已逾期"}), 401
    data = request.get_json(silent=True) or {}
    err = _change_password(user, data.get("current_password") or "",
                           data.get("new_password") or "",
                           data.get("new_password2") or "")
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True})


@app.route("/api/v1/member/delete", methods=["POST"])
def api_member_delete():
    """刪除帳號。請求 {password}。"""
    user = current_user()
    if not user:
        return jsonify({"error": "未登入或登入已逾期"}), 401
    data = request.get_json(silent=True) or {}
    err = _delete_account(user, data.get("password") or "")
    if err:
        return jsonify({"error": err}), 400
    return jsonify({"ok": True})


@app.route("/api/v1/member/questions", methods=["GET"])
def api_member_questions():
    """我的卜卦紀錄(只回自己的)。"""
    user = current_user()
    if not user:
        return jsonify({"error": "未登入或登入已逾期"}), 401
    rows = db.list_user_questions(user["id"])
    items = [{
        "id": r["id"],
        "created_at": r["created_at"].isoformat()
            if hasattr(r["created_at"], "isoformat") else r["created_at"],
        "question": r["question"], "ben_gua": r["ben_gua"],
        "bian_gua": r["bian_gua"], "moving_lines": r["moving_lines"],
    } for r in rows]
    return jsonify({"questions": items})


@app.route("/api/v1/chart", methods=["POST"])
def api_chart():
    """排盤:日期時間 + 六爻 → 卦象 JSON(確定性、免費、免登入)。

    請求 JSON:
      {"y":2026,"m":6,"d":15,"h":16,
       "yao_vals":["1,0","0,0","1,1","0,1","1,0","0,0"],
       "aspect":"all"}
      yao_vals:由初爻到上爻共 6 個,每項 "陰陽,動否"
               (陰陽 1=陽 0=陰;動否 1=動 0=不動)。
      y/m/d/h 省略時以伺服器當下時間補上。
    回傳:含「卦象 / 旬空 / 對六爻」的 chart_payload。
    """
    data = request.get_json(silent=True) or {}
    payload, err = _compute_chart(data)
    if err:
        body, code = err
        return jsonify(body), code
    return jsonify(payload)


@app.route("/api/v1/cast", methods=["POST"])
def api_cast():
    """時辰起卦:給定日期時間 → 依時辰自動起卦(免費、免登入)。

    請求 JSON:{"y":2026,"m":6,"d":15,"h":16,"aspect":"all"}(省略時間以當下補)。
    回傳:與 /api/v1/chart 相同結構的 chart_payload(卦象/旬空/對六爻)。
    """
    data = request.get_json(silent=True) or {}
    try:
        y_i = int(data.get("y") or datetime.now().year)
        m_i = int(data.get("m") or datetime.now().month)
        d_i = int(data.get("d") or datetime.now().day)
        h_i = int(data.get("h") or datetime.now().hour)
    except (TypeError, ValueError):
        return jsonify({"error": "日期時間格式錯誤"}), 400

    aspect = (data.get("aspect") or "all").strip().lower()
    if aspect not in ("all", "love", "health", "work", "wealth"):
        aspect = "all"

    try:
        dt_obj = datetime(y_i, m_i, d_i, h_i, 0)
        chart = cast_hexagram(dt_obj)
        payload = _enrich_chart_payload(chart, dt_obj, aspect)
    except Exception as e:
        return jsonify({"error": f"起卦失敗:{type(e).__name__}: {e}"}), 500

    # 姓名/性別:有填姓名就存進歷史紀錄(與網頁 /cast 一致;失敗不影響回應)
    name = (data.get("name") or "").strip()
    gender = (data.get("gender") or "").strip().upper()
    if name:
        try:
            db.log_divination(name, y_i, m_i, d_i, h_i,
                              gender=db.norm_gender(gender))
        except Exception as e:
            app.logger.warning("log_divination failed (%s: %s)",
                               type(e).__name__, e)
    return jsonify(payload)


@app.route("/api/v1/almanac/month", methods=["GET"])
def api_almanac_month():
    """萬年曆整月資料(免費、免登入)。?y=2026&m=6"""
    from divination import almanac
    try:
        y = int(request.args.get("y") or datetime.now().year)
        m = int(request.args.get("m") or datetime.now().month)
        if not (1 <= m <= 12) or not (1900 <= y <= 2100):
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "年月格式錯誤"}), 400
    return jsonify(almanac.month_info(y, m))


@app.route("/api/v1/almanac/day", methods=["GET"])
def api_almanac_day():
    """萬年曆單日資料(免費、免登入)。?y=2026&m=6&d=16"""
    from divination import almanac
    try:
        y = int(request.args.get("y") or datetime.now().year)
        m = int(request.args.get("m") or datetime.now().month)
        d = int(request.args.get("d") or datetime.now().day)
        datetime(y, m, d)  # 驗證合法日期
    except (TypeError, ValueError):
        return jsonify({"error": "日期格式錯誤"}), 400
    return jsonify(almanac.day_info(y, m, d))


@app.route("/api/v1/daily", methods=["GET"])
def api_daily():
    """今日指引(命盤對今日,純引擎、零 AI)。需登入且已設生日。
    回傳 analyze_daily 結果;未設生日回 {needs_birthday: true}。"""
    user = current_user()
    if not user:
        return jsonify({"error": "請先登入會員"}), 401
    if not all(user.get(k) is not None for k in ("birth_y", "birth_m", "birth_d", "birth_h")):
        return jsonify({"needs_birthday": True}), 200
    try:
        birth_dt = datetime(int(user["birth_y"]), int(user["birth_m"]),
                            int(user["birth_d"]), int(user["birth_h"]))
        ming = cast_hexagram(birth_dt)
        daily = analyze_daily(ming, datetime.now())
    except Exception as e:  # noqa: BLE001
        app.logger.warning("api_daily 失敗: %s", e)
        return jsonify({"error": "今日指引計算失敗"}), 500
    daily.pop("_debug", None)  # 不外露內部術語
    return jsonify(daily), 200


@app.route("/api/v1/fortune", methods=["GET"])
def api_fortune():
    """流年分析(免費、免登入):?y&m&d&h&gender&year。

    依出生 y/m/d/h + 性別,分析目標 year 的流年 + 12 流月 + 白話斷語。
    """
    now = datetime.now()
    try:
        y_i = int(request.args["y"])
        m_i = int(request.args["m"])
        d_i = int(request.args["d"])
        h_i = int(request.args["h"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "缺少出生年月日時(y/m/d/h)"}), 400
    try:
        year_i = int(request.args.get("year", now.year))
    except ValueError:
        year_i = now.year
    gender = (request.args.get("gender", "") or "").strip().upper()
    gender = db.norm_gender(gender)
    try:
        fortune = analyze_fortune(datetime(y_i, m_i, d_i, h_i, 0), year_i, gender=gender)
    except Exception as e:
        return jsonify({"error": f"流年分析失敗:{type(e).__name__}: {e}"}), 500
    return jsonify(fortune)


@app.route("/api/v1/prompt", methods=["POST"])
def api_prompt():
    """組裝 AI 解讀 Prompt(規則 + 所問之事 + 卦象 JSON),供使用者複製到自己的 AI。

    請求 JSON:與 /api/v1/chart 相同,另加 question(所問之事,必填)。
    需登入會員,扣 1 點(不呼叫 Claude,只是把可攜帶 prompt 組好回傳)。
    回傳:{"prompt": "...", "balance": n}。
    """
    user = current_user()
    if not user:
        return jsonify({"error": "請先登入會員"}), 401
    body, code = _prompt_and_charge(user, request.get_json(silent=True) or {})
    return jsonify(body), code


def _call_claude_reading(system_text, user_text):
    """呼叫 Claude(預設 Sonnet 4.6)即時產生解讀。

    system_text(規則)當作可快取 system;user_text(問事+JSON)當 user 訊息。
    成功回傳解讀文字;失敗丟例外(由呼叫端決定退點)。
    """
    import anthropic
    client = anthropic.Anthropic()  # 讀環境變數 ANTHROPIC_API_KEY
    resp = client.messages.create(
        model=_AI_READING_MODEL,
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},  # 規則固定,開快取省 token
        }],
        messages=[{"role": "user", "content": user_text}],
    )
    text = "\n".join(
        b.text for b in resp.content if getattr(b, "type", "") == "text"
    ).strip()
    if not text:
        raise RuntimeError("AI 回傳空內容")
    return text


def _stream_claude_reading(system_text, user_text):
    """串流版:逐段 yield Claude(預設 Sonnet 4.6)的解讀文字。

    與 _call_claude_reading 相同的 system(可快取規則)/user(問事+JSON),
    但用 messages.stream 邊生成邊吐 token,讓前端即時顯示、不必枯等整篇。
    生成失敗丟例外(由呼叫端決定退點)。
    """
    import anthropic
    client = anthropic.Anthropic()  # 讀環境變數 ANTHROPIC_API_KEY
    with client.messages.stream(
        model=_AI_READING_MODEL,
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},  # 規則固定,開快取省 token
        }],
        messages=[{"role": "user", "content": user_text}],
    ) as stream:
        for chunk in stream.text_stream:
            if chunk:
                yield chunk


def _stream_reading_response(uid, system_text, user_text, bal,
                            refund_points, refund_ref):
    """共用的 SSE 串流解讀回應:逐段吐 Claude 文字,失敗自動退點。

    事件:delta(逐段文字)/ done(附最新餘額)/ error(已退點)。
    扣點請由呼叫端先做好,bal 為扣完後餘額;失敗時退回 refund_points 點。
    """
    def _sse(event, payload):
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def generate():
        got_any = False
        try:
            for chunk in _stream_claude_reading(system_text, user_text):
                got_any = True
                yield _sse("delta", {"t": chunk})
            if not got_any:
                raise RuntimeError("AI 回傳空內容")
            yield _sse("done", {"balance": bal})
        except Exception as e:  # 串流途中任何失敗都退點
            db.add_points(uid, refund_points, "refund", ref=refund_ref)
            app.logger.warning("AI reading stream failed (%s: %s)",
                               type(e).__name__, e)
            yield _sse("error", {"error": "解讀產生失敗,已退還點數,請稍後再試"})

    headers = {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # 若前方有 nginx,關閉其緩衝以確保即時串流
    }
    return Response(stream_with_context(generate()), headers=headers)


@app.route("/manual/ai_prompt", methods=["POST"])
def manual_ai_prompt():
    """組裝可攜帶 prompt(規則 + 所問之事 + 卦象 JSON),供會員複製貼到自己的 AI。
    需登入,扣 1 點。"""
    user = current_user()
    if not user:
        return jsonify({"error": "請先登入會員"}), 401
    body, code = _prompt_and_charge(user, request.get_json(silent=True) or {})
    return jsonify(body), code


@app.route("/manual/ai_reading", methods=["POST"])
def manual_ai_reading():
    """AI 解盤:扣 1 點 → 串流(SSE)即時產生解讀。任何失敗都自動退點。

    回應為 text/event-stream,事件:
      event: delta  data:{"t": "..."}     逐段解讀文字
      event: done   data:{"balance": n}   生成完成、附最新餘額
      event: error  data:{"error": "..."} 生成失敗(已退點)
    扣點等前置檢查若失敗,仍回傳一般 JSON + 對應狀態碼(前端據 Content-Type 區分)。
    """
    user = current_user()
    if not user:
        return jsonify({"error": "請先登入會員"}), 401

    data = request.get_json(silent=True) or {}
    system_text, user_text, chart_payload, err = _build_manual_reading(data)
    if err:
        body, code = err
        return jsonify(body), code

    # 先原子扣點(餘額不足直接擋)
    ok, bal, msg = db.try_deduct_point(user["id"], 1, "divination")
    if not ok:
        if msg == "insufficient":
            return jsonify({
                "error": "點數不足,請先儲值",
                "balance": user.get("points_balance", 0),
            }), 402
        return jsonify({"error": "系統忙線,請稍後再試"}), 503

    _log_question_event(user, data, chart_payload=chart_payload)  # 使用 AI(解盤)→ 記錄
    return _stream_reading_response(user["id"], system_text, user_text, bal,
                                    1, "ai_reading_failed")


# ============================================================
# 流年宜忌解讀端點(進階、扣點;web 與 app 共用同一組 API)
# ============================================================
@app.route("/api/v1/fortune/prompt", methods=["POST"])
def api_fortune_prompt():
    """流年「產生 Prompt」:扣點、回傳可貼到自己 AI 的流年宜忌 prompt。"""
    user = current_user()
    if not user:
        return jsonify({"error": "請先登入會員"}), 401
    body, code = _fortune_prompt_and_charge(user, request.get_json(silent=True) or {})
    return jsonify(body), code


@app.route("/api/v1/fortune/reading", methods=["POST"])
def api_fortune_reading():
    """流年「AI 解讀」:扣點 → 串流(SSE)即時產生白話宜忌。失敗自動退點。"""
    user = current_user()
    if not user:
        return jsonify({"error": "請先登入會員"}), 401
    data = request.get_json(silent=True) or {}
    system_text, user_text, err = _build_fortune_reading(data)
    if err:
        body, code = err
        return jsonify(body), code
    ok, bal, msg = db.try_deduct_point(user["id"], FORTUNE_AI_COST, "fortune")
    if not ok:
        if msg == "insufficient":
            return jsonify({"error": "點數不足,請先儲值",
                            "balance": user.get("points_balance", 0)}), 402
        return jsonify({"error": "系統忙線,請稍後再試"}), 503
    return _stream_reading_response(user["id"], system_text, user_text, bal,
                                    FORTUNE_AI_COST, "fortune_reading_failed")


def _reading_and_charge(user, data):
    """即時 AI 解讀(非串流,供 App 用):驗證 → 扣 1 點 → 呼叫 Claude → 回完整解讀。
    失敗自動退點。回傳 (body_dict, status_code);成功 body = {"reading","balance"}。"""
    system_text, user_text, chart_payload, err = _build_manual_reading(data)
    if err:
        return err
    ok, bal, msg = db.try_deduct_point(user["id"], 1, "divination")
    if not ok:
        if msg == "insufficient":
            return ({"error": "點數不足,請先儲值",
                     "balance": user.get("points_balance", 0)}, 402)
        return ({"error": "系統忙線,請稍後再試"}, 503)
    _log_question_event(user, data, chart_payload=chart_payload)  # 使用 AI → 記錄
    try:
        reading = _call_claude_reading(system_text, user_text)
        if not (reading or "").strip():
            raise RuntimeError("AI 回傳空內容")
    except Exception as e:  # noqa: BLE001
        db.add_points(user["id"], 1, "refund", ref="reading_failed")
        app.logger.warning("AI reading failed (%s: %s)", type(e).__name__, e)
        return ({"error": "解讀產生失敗,已退還點數,請稍後再試"}, 502)
    return ({"reading": reading, "balance": bal}, 200)


@app.route("/api/v1/reading", methods=["POST"])
def api_reading():
    """即時 AI 解讀(命果 MINGO 教練式,非串流):扣 1 點 → 回完整解讀文字。
    請求 JSON 同 /api/v1/prompt(含 question)。回傳 {"reading","balance"}。"""
    user = current_user()
    if not user:
        return jsonify({"error": "請先登入會員"}), 401
    body, code = _reading_and_charge(user, request.get_json(silent=True) or {})
    return jsonify(body), code


# ---- 解讀後「繼續聊」:把卦象 + 解讀帶進多輪對話(人生教練)----
_CHAT_TURN_INSTRUCTION = (
    "\n\n---\n以上是這次卜卦的規則、所問之事與卦象。你已先依規則產出過一段完整解讀"
    "(見下一則 assistant 訊息)。接下來是使用者的**追問對話**:請以「懂易經的人生教練」"
    "身分,**自然、簡短地回應**(2–5 句,口語、有陪伴感),不必再重跑九段格式。"
    "務必守住:**不下會成/不會成、不替使用者做決定**;若被逼問結論,描述卦象顯示什麼、"
    "把決定權交還對方。只在必要時引用卦象,以陪對方把選擇想清楚為目標。"
)


def _build_chat(data):
    """組多輪對話的 (system_text, messages, err)。
    data 需含:解讀請求欄位(question/y/m/d/h/yao_vals)+ reading(先前解讀)
    + history(先前對話 [{role,content}]) + message(這次的話)。"""
    message = (data.get("message") or "").strip()
    if not message:
        return None, None, ({"error": "請輸入訊息"}, 400)
    if len(message) > 1000:
        return None, None, ({"error": "訊息過長(上限 1000 字)"}, 400)
    system_text, user_text, _payload, err = _build_manual_reading(data)
    if err:
        return None, None, err
    reading = (data.get("reading") or "").strip()
    if not reading:
        return None, None, ({"error": "缺少先前解讀內容"}, 400)

    messages = [
        {"role": "user", "content": user_text + _CHAT_TURN_INSTRUCTION},
        {"role": "assistant", "content": reading},
    ]
    # 帶入先前追問對話(限最近 12 則,避免過長)
    for turn in (data.get("history") or [])[-12:]:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    return system_text, messages, None


def _call_claude_chat(system_text, messages):
    """多輪對話呼叫 Claude;回傳回覆文字,失敗丟例外。"""
    import anthropic
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=_AI_READING_MODEL,
        max_tokens=1024,
        system=[{
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=messages,
    )
    text = "\n".join(
        b.text for b in resp.content if getattr(b, "type", "") == "text"
    ).strip()
    if not text:
        raise RuntimeError("AI 回傳空內容")
    return text


@app.route("/api/v1/chat", methods=["POST"])
def api_chat():
    """解讀後的追問對話(教練式,非串流):每則扣 CHAT_AI_COST 點,失敗退點。
    回傳 {"reply","balance"}。"""
    user = current_user()
    if not user:
        return jsonify({"error": "請先登入會員"}), 401
    system_text, messages, err = _build_chat(request.get_json(silent=True) or {})
    if err:
        body, code = err
        return jsonify(body), code
    bal = user.get("points_balance", 0)
    if CHAT_AI_COST > 0:
        ok, bal, msg = db.try_deduct_point(user["id"], CHAT_AI_COST, "chat")
        if not ok:
            if msg == "insufficient":
                return jsonify({"error": "點數不足,請先儲值",
                                "balance": user.get("points_balance", 0)}), 402
            return jsonify({"error": "系統忙線,請稍後再試"}), 503
    try:
        reply = _call_claude_chat(system_text, messages)
    except Exception as e:  # noqa: BLE001
        if CHAT_AI_COST > 0:
            db.add_points(user["id"], CHAT_AI_COST, "refund", ref="chat_failed")
        app.logger.warning("AI chat failed (%s: %s)", type(e).__name__, e)
        return jsonify({"error": "回覆產生失敗,已退還點數,請稍後再試"}), 502
    return jsonify({"reply": reply, "balance": bal}), 200


# ============================================================
# 🌱 成長反思(Phase 3):最有感一句 → 本週小目標 → 下週回訪(站內 + Email)
# ============================================================
_GOAL_SYSTEM = (
    "你是命果 MINGO 的人生教練。使用者剛做完一次卜卦解讀,說出他最有感的一句話/感受。"
    "請把它轉成『這週可以做到的一件很小的事』——具體、溫和、可執行、過程導向"
    "(釐清 / 觀察 / 練習 / 反思型),**不替他做人生決定**(不可出現離職/分手/投資等決定)。"
    "只回一句話(40 字內),直接給這件小事,不要任何前後綴或引號。"
)


def _craft_growth_goal(question, feeling):
    """用 Claude 把「最有感的一句」轉成本週一件小事。失敗回 None(由呼叫端 fallback)。"""
    try:
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=_AI_READING_MODEL,
            max_tokens=160,
            system=[{"type": "text", "text": _GOAL_SYSTEM}],
            messages=[{"role": "user", "content":
                       f"所問之事:{question or '(未填)'}\n最有感的:{feeling}\n"
                       "請給這週的一件小事:"}],
        )
        text = "\n".join(b.text for b in resp.content
                         if getattr(b, "type", "") == "text").strip()
        return text or None
    except Exception as e:  # noqa: BLE001
        app.logger.warning("craft goal failed (%s: %s)", type(e).__name__, e)
        return None


@app.route("/api/v1/reflection", methods=["POST"])
def api_reflection_create():
    """建立成長反思:{question?, feeling, goal?}。未給 goal 則由 AI 生成本週小事。
    免費(屬陪伴功能)。回傳 {id, goal}。"""
    user = current_user()
    if not user:
        return jsonify({"error": "請先登入會員"}), 401
    data = request.get_json(silent=True) or {}
    feeling = (data.get("feeling") or "").strip()
    if not feeling:
        return jsonify({"error": "請寫下你最有感的一句"}), 400
    if len(feeling) > 500:
        return jsonify({"error": "內容過長(上限 500 字)"}), 400
    question = (data.get("question") or "").strip()[:500]
    goal = (data.get("goal") or "").strip()
    if not goal:
        goal = _craft_growth_goal(question, feeling) or \
            "這週,當你又想起這件事時,先停三個深呼吸,問自己:我現在真正想要的是什麼?"
    rid = db.create_reflection(user["id"], question, feeling, goal, remind_days=7)
    if rid is None:
        return jsonify({"error": "儲存失敗,請稍後再試"}), 503
    return jsonify({"id": rid, "goal": goal}), 200


@app.route("/api/v1/reflections/due", methods=["GET"])
def api_reflections_due():
    """到回訪時間、尚未回顧的反思(站內提醒用)。"""
    user = current_user()
    if not user:
        return jsonify({"error": "請先登入會員"}), 401
    items = db.list_due_reflections(user["id"])
    for it in items:  # datetime → ISO 字串
        for k in ("created_at", "remind_at"):
            if it.get(k):
                it[k] = it[k].isoformat()
    return jsonify({"reflections": items}), 200


@app.route("/api/v1/reflection/done", methods=["POST"])
def api_reflection_done():
    """使用者回顧完成 → 標記 done。{id}。"""
    user = current_user()
    if not user:
        return jsonify({"error": "請先登入會員"}), 401
    rid = (request.get_json(silent=True) or {}).get("id")
    if not rid:
        return jsonify({"error": "缺少 id"}), 400
    ok = db.mark_reflection_reviewed(user["id"], rid)
    return jsonify({"ok": ok}), (200 if ok else 404)


@app.route("/api/v1/reflections/dispatch_reminders", methods=["POST"])
def api_reflections_dispatch():
    """寄出到期的「下週回訪」Email 提醒(供每日排程/管理員呼叫)。
    授權:管理員登入,或帶 X-Cron-Token 比對環境變數 CRON_TOKEN。"""
    token = request.headers.get("X-Cron-Token", "")
    cron_token = os.environ.get("CRON_TOKEN", "")
    user = current_user()
    authed = (user and _email_is_admin(user.get("email"))) or \
             (cron_token and token == cron_token)
    if not authed:
        return jsonify({"error": "未授權"}), 403
    sent, failed = 0, 0
    for r in db.list_reminders_to_send(limit=200):
        name = r.get("display_name") or "朋友"
        body = (
            f"{name},你好:\n\n上週你在命果做了一次卜卦,當時最有感的是:\n"
            f"「{r.get('feeling')}」\n\n你給自己設了一件小事:\n"
            f"✦ {r.get('goal')}\n\n這週過得如何?有沒有試著做做看?\n"
            "回到命果,我陪你一起看看這件事帶來了哪些變化。\n\n— 命果 MINGO"
        )
        if _send_mail(r["email"], "命果 MINGO — 這週,還記得你給自己的那件小事嗎?", body):
            db.mark_reflection_reminded(r["id"])
            sent += 1
        else:
            failed += 1
    return jsonify({"sent": sent, "failed": failed}), 200


# ============================================================
# 會員頁面:會員資料 + 剩餘點數 + 點數異動紀錄
# ============================================================
@app.route("/member", methods=["GET"])
def member():
    user = current_user()
    if not user:
        return redirect(url_for("login_page", next="/member"))
    ledger = db.list_ledger(user["id"])
    # 每日運勢(命卦對今日):有完整生日才算;純引擎、零 AI
    daily, ming_name = None, None
    if all(user.get(k) is not None for k in ("birth_y", "birth_m", "birth_d", "birth_h")):
        try:
            birth_dt = datetime(int(user["birth_y"]), int(user["birth_m"]),
                                int(user["birth_d"]), int(user["birth_h"]))
            ming = cast_hexagram(birth_dt)
            ming_name = ming.get("本卦", {}).get("卦名")
            daily = analyze_daily(ming, datetime.now())
        except Exception as e:  # noqa: BLE001
            app.logger.warning("每日運勢計算失敗: %s", e)
    due_reflections = db.list_due_reflections(user["id"])  # 🌱 到期回訪
    return render_template("member.html", mode="member", user=user, ledger=ledger,
                           daily=daily, ming_name=ming_name,
                           due_reflections=due_reflections)


@app.route("/member/profile", methods=["GET", "POST"])
def member_profile():
    """修改會員資料:暱稱 + 生日(命盤排卦用)。"""
    user = current_user()
    if not user:
        return redirect(url_for("login_page", next="/member/profile"))

    if request.method == "POST":
        display_name = (request.form.get("display_name") or "").strip() or None
        gender = (request.form.get("gender") or "").strip().upper()
        gender = db.norm_gender(gender)
        # 生日(可留空;要填就四個都要合理)
        birth, ecode = _parse_birthday(lambda n: request.form.get(n))
        if ecode:
            msg = {"format": "生日格式不正確",
                   "incomplete": "生日請完整填寫年/月/日/時,或全部留空",
                   "invalid_date": "這個生日日期不存在,請確認"}[ecode]
            return render_template("member_profile.html", mode="member",
                                   user=user, error=msg)

        db.update_user_profile(user["id"], display_name=display_name,
                               gender=gender, birth=birth)
        return redirect(url_for("member"))

    return render_template("member_profile.html", mode="member", user=user)


@app.route("/member/history", methods=["GET"])
def member_history():
    """我的卜卦紀錄(會員看自己的)。"""
    user = current_user()
    if not user:
        return redirect(url_for("login_page", next="/member/history"))
    records = db.list_user_questions(user["id"])
    return render_template("member_history.html", mode="member",
                           user=user, records=records)


@app.route("/member/password", methods=["GET", "POST"])
def member_password():
    """修改密碼。"""
    user = current_user()
    if not user:
        return redirect(url_for("login_page", next="/member/password"))
    if request.method == "POST":
        err = _change_password(user,
                               request.form.get("current_password") or "",
                               request.form.get("new_password") or "",
                               request.form.get("new_password2") or "")
        if err:
            return render_template("member_password.html", mode="member", error=err)
        return render_template("member_password.html", mode="member", success=True)
    return render_template("member_password.html", mode="member")


@app.route("/member/delete", methods=["GET", "POST"])
def member_delete():
    """刪除帳號(需確認密碼)。"""
    user = current_user()
    if not user:
        return redirect(url_for("login_page", next="/member/delete"))
    if request.method == "POST":
        err = _delete_account(user, request.form.get("password") or "")
        if err:
            return render_template("member_delete.html", mode="member", error=err)
        session.clear()
        return redirect(url_for("landing"))
    return render_template("member_delete.html", mode="member")


# ============================================================
# 會員:網頁登入 / 註冊 / 登出(session-based,與 App 的 token 並行)
#   後端驗證共用 db.create_email_user / db.get_email_user,與 App 同一套帳號。
# ============================================================
@app.route("/register", methods=["GET", "POST"])
def register_page():
    """網頁 Email 註冊。成功後寫入 session 並導向會員中心。"""
    if current_user():
        return redirect(url_for("member"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        password2 = request.form.get("password2") or ""
        display_name = (request.form.get("display_name") or "").strip() or None

        def _err(msg):
            return render_template(
                "register.html", mode="register", error=msg, email=email
            )

        err = _validate_credentials(email, password)
        if err:
            return _err(err)
        if password != password2:
            return _err("兩次輸入的密碼不一致")
        if not (request.form.get("agree_privacy") and request.form.get("agree_disclaimer")):
            return _err("請先閱讀並勾選個資使用同意書與免責聲明")

        status, user = _create_member(email, password, display_name)
        if status == "exists":
            return _err("這個 Email 已經註冊過了")
        if status != "ok" or not user:
            return _err("系統忙線,請稍後再試")

        session.permanent = True
        session["user_id"] = user["id"]
        session["login_at"] = datetime.now(timezone.utc).isoformat()
        return redirect(url_for("member"))

    return render_template("register.html", mode="register")


@app.route("/login", methods=["GET", "POST"])
def login_page():
    """網頁 Email 登入。成功後寫入 session 並導向 next(預設會員中心)。"""
    if current_user():
        return redirect(url_for("member"))
    next_url = request.values.get("next", "/member")
    if not next_url.startswith("/"):
        next_url = "/member"

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user, status = _login_member(email, password)
        if status == "locked":
            return render_template(
                "login.html", mode="login",
                error="帳號已鎖定(連續登入失敗過多),請聯絡管理員解鎖",
                email=email, next_url=next_url,
            )
        if not user:
            return render_template(
                "login.html", mode="login",
                error="Email 或密碼不正確", email=email, next_url=next_url,
            )
        session.permanent = True
        session["user_id"] = user["id"]
        session["login_at"] = datetime.now(timezone.utc).isoformat()
        return redirect(next_url)

    return render_template("login.html", mode="login", next_url=next_url)


@app.route("/forgot", methods=["GET", "POST"])
def forgot_page():
    """忘記密碼:輸入 Email → 寄重設連結。不論存在與否都回相同訊息。"""
    if current_user():
        return redirect(url_for("member"))
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        _do_forgot(email)
        return render_template("forgot.html", mode="login", sent=True, email=email)
    return render_template("forgot.html", mode="login")


@app.route("/reset", methods=["GET", "POST"])
def reset_page():
    """憑信中 token 設定新密碼。"""
    token = (request.values.get("token") or "").strip()
    uid = verify_reset_token(token)
    if not uid:
        return render_template("reset.html", mode="login", invalid=True)
    if request.method == "POST":
        new_pw = request.form.get("new_password") or ""
        if new_pw != (request.form.get("new_password2") or ""):
            return render_template("reset.html", mode="login", token=token,
                                   error="兩次輸入的密碼不一致")
        perr = _password_error(new_pw)
        if perr:
            return render_template("reset.html", mode="login", token=token, error=perr)
        db.update_password(uid, generate_password_hash(new_pw))  # 改完舊 token 自動失效
        db.set_user_locked(uid, False)  # 重設密碼即一併解鎖(本人證明了 Email 控制權)
        u = db.get_user(uid)
        if u:
            _send_password_changed_notice(u.get("email"))  # 安全通知:讓本人能發現被盜
        return render_template("reset.html", mode="login", done=True)
    return render_template("reset.html", mode="login", token=token)


@app.route("/api/v1/auth/forgot", methods=["POST"])
def api_auth_forgot():
    """App 忘記密碼:寄重設連結(連結走網頁)。一律回成功訊息,防帳號列舉。"""
    data = request.get_json(silent=True) or {}
    _do_forgot((data.get("email") or "").strip().lower())
    return jsonify({"ok": True})


@app.route("/logout", methods=["GET", "POST"])
def member_logout():
    """登出:清掉登入 session。"""
    session.clear()
    return redirect(url_for("landing"))


# ============================================================
# 管理:會員管理(需 ADMIN_EMAILS 名單內的帳號登入)
# ============================================================
@app.route("/admin/members", methods=["GET"])
@admin_required
def admin_members():
    """會員清單:可看每位會員的點數,並手動加點。"""
    users = db.list_users()
    added = request.args.get("added")          # 剛加點成功的 user_id(顯示提示)
    unlocked = request.args.get("unlocked")    # 剛解鎖的 user_id(顯示提示)
    return render_template(
        "admin/members.html", mode="admin_members",
        users=users, added=added, unlocked=unlocked,
    )


@app.route("/admin/members/<int:user_id>/add_points", methods=["POST"])
@admin_required
def admin_member_add_points(user_id):
    """手動幫某會員加點(可正可負;負數為扣回)。事由記為 admin_adjust。"""
    try:
        amount = int(request.form.get("amount", "0"))
    except (TypeError, ValueError):
        amount = 0
    if amount == 0:
        return redirect("/admin/members")
    # 防呆:單次調整上限,避免手滑打太多
    amount = max(-100000, min(100000, amount))
    admin = current_user()
    db.add_points(user_id, amount, "admin_adjust",
                  ref=(admin.get("email") if admin else None))
    return redirect(f"/admin/members?added={user_id}")


@app.route("/admin/members/<int:user_id>/unlock", methods=["POST"])
@admin_required
def admin_member_unlock(user_id):
    """管理員解鎖帳號(清失敗計數 + 解除鎖定)。"""
    db.set_user_locked(user_id, False)
    return redirect(f"/admin/members?unlocked={user_id}")


# ============================================================
# 管理:卜卦問事紀錄(需 ADMIN_EMAILS 名單內的帳號登入)
# ============================================================
@app.route("/admin/questions", methods=["GET"])
@admin_required
def admin_questions():
    """卜卦問事紀錄查詢:會員、登入時間、卜卦時間、問題、卦象結果。支援關鍵字 + 日期區間。"""
    search = (request.args.get("q") or "").strip()
    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()
    records = db.list_divination_questions(
        search=search or None, start=start or None, end=end or None,
    )
    return render_template(
        "admin/questions.html", mode="admin_questions",
        records=records, search=search, start=start, end=end,
    )


@app.route("/admin/questions/<int:qid>", methods=["GET"])
@admin_required
def admin_question_detail(qid):
    """單筆卜卦問事明細:用存下的原始六爻 + 起卦時間重建完整卦象。"""
    rec = db.get_divination_question(qid)
    if not rec:
        abort(404)
    chart = None
    prompt_text = None
    if rec.get("yao_vals"):
        try:
            lines, moving = [], []
            for part in rec["yao_vals"].split("|"):
                a, b = part.split(",")
                lines.append(int(a))
                moving.append(int(b))
            dt_obj = None
            if rec.get("cast_dt"):
                try:
                    dt_obj = datetime.strptime(rec["cast_dt"], "%Y-%m-%d %H:%M")
                except ValueError:
                    dt_obj = None
            chart = cast_hexagram_manual(lines, moving, dt_obj)

            # 用存下的資料即時重組「當時的 AI Prompt」(不額外佔空間)
            if dt_obj is not None:
                data = {
                    "y": dt_obj.year, "m": dt_obj.month,
                    "d": dt_obj.day, "h": dt_obj.hour,
                    "yao_vals": rec["yao_vals"].split("|"),
                    "aspect": "all",
                    "question": rec.get("question") or "",
                }
                system_text, user_text, _cp, perr = _build_manual_reading(data)
                if not perr:
                    prompt_text = system_text + "\n\n---\n\n" + user_text
        except Exception as e:
            app.logger.warning("rebuild chart/prompt failed (%s: %s)",
                               type(e).__name__, e)
    return render_template(
        "admin/question_detail.html", mode="admin_questions",
        rec=rec, r=chart, prompt_text=prompt_text,
    )


# ============================================================
# 管理:歷史紀錄(需 ADMIN_EMAILS 名單內的帳號登入)
# ============================================================
@app.route("/admin/history", methods=["GET"])
@admin_required
def admin_history():
    clients = db.list_clients()
    return render_template(
        "admin/history_list.html",
        mode="admin_list", clients=clients,
    )


@app.route("/admin/history/<path:name>", methods=["GET"])
@admin_required
def admin_history_detail(name):
    charts = db.list_charts_by_name(name)
    for ch in charts:
        msg = (
            f"確定刪除以下命盤紀錄?\n\n"
            f"  姓名:{ch['name']}\n"
            f"  日期:{ch['year']}-{ch['month']:02d}-{ch['day']:02d} {ch['hour']:02d}時\n\n"
            f"此動作無法復原。"
        )
        ch['confirm_msg'] = json.dumps(msg, ensure_ascii=False)

    flash_msg = request.args.get("flash", "")
    flash_kind = request.args.get("flash_kind", "")
    return render_template(
        "admin/history_detail.html",
        mode="admin_detail", detail_name=name, charts=charts,
        flash_msg=flash_msg, flash_kind=flash_kind,
    )


@app.route("/admin/history/<path:name>/delete/<int:chart_id>", methods=["POST"])
@admin_required
def admin_history_delete(name, chart_id):
    success, deleted, info = db.delete_chart_by_id(chart_id)
    if success and deleted > 0:
        msg = f"已刪除:{info}"
        kind = "ok"
    elif success and deleted == 0:
        msg = f"找不到要刪除的紀錄({info})"
        kind = "warn"
    else:
        msg = f"刪除失敗:{info}"
        kind = "err"

    from urllib.parse import urlencode, quote
    qs = urlencode({"flash": msg, "flash_kind": kind})
    return redirect(f"/admin/history/{quote(name)}?{qs}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
