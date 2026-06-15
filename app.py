# -*- coding: utf-8 -*-
"""
命卦排盤 Flask 網頁介面

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
from functools import wraps
from datetime import datetime, timezone, timedelta

from flask import (
    Flask, request, render_template, session, redirect, url_for, abort,
    Response, jsonify, stream_with_context,
)
from werkzeug.security import generate_password_hash, check_password_hash

from hexagram_engine import (
    cast_hexagram, cast_hexagram_manual, analyze_chart_aspects,
)
from fortune_engine import analyze_fortune
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
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

# 管理員 idle timeout(分鐘):超過此時間未活動則自動登出
ADMIN_IDLE_TIMEOUT_MINUTES = int(os.environ.get("ADMIN_IDLE_TIMEOUT_MINUTES", "15"))

# 管理員密碼:以環境變數設定。預設 "admin",部署時務必改掉。
_ADMIN_PASSWORD_PLAIN = os.environ.get("ADMIN_PASSWORD", "admin")
_ADMIN_PASSWORD_HASH = generate_password_hash(_ADMIN_PASSWORD_PLAIN)


# ============================================================
# AI 解讀 prompt 載入(啟動時讀進記憶體)
# ============================================================
def _load_manual_prompt():
    """讀取手動排卦 AI 解讀 prompt v1。

    從 docs/AI_INTERPRETER_MANUAL_PROMPT_v1.md 中擷取
    「===== PROMPT 開始 =====」到「===== PROMPT 結束 =====」之間的純 prompt 內容。
    """
    candidates = [
        os.path.join(os.path.dirname(__file__), "docs",
                     "AI_INTERPRETER_MANUAL_PROMPT_v1.md"),
        "/app/docs/AI_INTERPRETER_MANUAL_PROMPT_v1.md",
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


_MANUAL_AI_PROMPT = _load_manual_prompt()
if _MANUAL_AI_PROMPT is None:
    print("[AI prompt] 警告:找不到 docs/AI_INTERPRETER_MANUAL_PROMPT_v1.md,"
          "AI 解讀功能會回傳 500。")


def _now_utc_iso():
    """目前 UTC 時間的 ISO 字串(可序列化進 session)。"""
    return datetime.now(timezone.utc).isoformat()


def _is_session_expired():
    """檢查管理員 session 是否已逾時(超過 ADMIN_IDLE_TIMEOUT_MINUTES 未活動)。"""
    last_iso = session.get("last_active")
    if not last_iso:
        return True
    try:
        last_dt = datetime.fromisoformat(last_iso)
    except ValueError:
        return True
    now = datetime.now(timezone.utc)
    return (now - last_dt) > timedelta(minutes=ADMIN_IDLE_TIMEOUT_MINUTES)


def login_required(view):
    """裝飾器:要求已登入,並檢查 idle timeout。"""
    @wraps(view)
    def wrapper(*a, **kw):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        if _is_session_expired():
            session.clear()
            return redirect(url_for("admin_login", next=request.path, timeout=1))
        session["last_active"] = _now_utc_iso()
        return view(*a, **kw)
    return wrapper


def current_user():
    """回傳目前登入會員 dict(含 points_balance)或 None。

    ★ 暫時實作:管理員 session 對應到一個 'admin' 測試會員。
      日後接上正式登入(LINE/Google/Email...)後,只要改這個函式的取得來源,
      其餘扣點 / 會員頁 / AI 解盤都不用動。
    """
    if session.get("is_admin"):
        return db.get_or_create_user("admin", "admin", display_name="管理員(測試)")
    return None


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


# ============================================================
# 公開:時辰起卦
# ============================================================
@app.route("/cast", methods=["GET"])
def cast():
    y, m, d, h, default_y, default_m, default_d, default_h = _parse_dt_args()
    client_name = request.args.get("name", "").strip()
    gender = request.args.get("gender", "").strip().upper()
    if gender not in ("M", "F"):
        gender = ""

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
    gender = _get_field("gender", "").strip().upper()
    if gender not in ("M", "F"):
        gender = ""
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

    liu_yao = []
    for _e in (aspects.get("對六爻", []) or []):
        _e2 = dict(_e)
        _e2["空亡"] = _e.get("地支") in _kong_set
        liu_yao.append(_e2)

    return {
        "schema_version": 1,
        "排盤時間": dt_obj.strftime("%Y-%m-%d %H:00"),
        "問事類別": aspect,
        "卦象": chart,
        "旬空": xun_kong,
        "對六爻": liu_yao,
    }


def _build_manual_reading(data):
    """從 POST data 解析、重排盤、組出 (系統規則文字, 問事+卦象JSON文字)。

    回傳 (system_text, user_text, err):
      成功 → err 為 None;system_text 為規則(適合當可快取的 system),
             user_text 為「所問之事 + 卦象 JSON」(每次不同)。
      失敗 → (None, None, (error_dict, status_code))。
    """
    if _MANUAL_AI_PROMPT is None:
        return None, None, ({"error": "伺服器未載入 prompt 檔案,請聯絡管理員"}, 500)

    question = (data.get("question") or "").strip()
    if not question:
        return None, None, ({"error": "請輸入所問之事"}, 400)
    if len(question) > 500:
        return None, None, ({"error": "所問之事超過 500 字"}, 400)

    chart_payload, err = _compute_chart(data)
    if err:
        return None, None, err

    chart_json_str = json.dumps(
        chart_payload, ensure_ascii=False, separators=(",", ":")
    )
    user_text = (
        "【所問之事】\n" + question
        + "\n\n【卦象 JSON】\n```json\n" + chart_json_str + "\n```\n"
    )
    return _MANUAL_AI_PROMPT, user_text, None


# ============================================================
# REST API (給 iOS app;JSON 進出。排盤確定性、免費、免登入)
# ============================================================
@app.route("/api/v1/health", methods=["GET"])
def api_health():
    """健康檢查 / app 連線測試。"""
    return jsonify({"status": "ok", "service": "hexagram", "version": 1})


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
    return jsonify(payload)


@app.route("/api/v1/prompt", methods=["POST"])
def api_prompt():
    """組裝 AI 解讀 Prompt(規則 + 所問之事 + 卦象 JSON),供使用者複製到自己的 AI。

    請求 JSON:與 /api/v1/chart 相同,另加 question(所問之事,必填)。
    免費、免登入、不呼叫 Claude(只是把可攜帶 prompt 組好回傳)。
    回傳:{"prompt": "..."}。
    """
    data = request.get_json(silent=True) or {}
    system_text, user_text, err = _build_manual_reading(data)
    if err:
        body, code = err
        return jsonify(body), code
    full_prompt = system_text + "\n\n---\n\n" + user_text
    return jsonify({"prompt": full_prompt})


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


@app.route("/manual/ai_prompt", methods=["POST"])
@login_required
def manual_ai_prompt():
    """組裝可攜帶 prompt(規則 + 所問之事 + 卦象 JSON),供管理員複製貼到自己的 AI。"""
    data = request.get_json(silent=True) or {}
    system_text, user_text, err = _build_manual_reading(data)
    if err:
        body, code = err
        return jsonify(body), code
    full_prompt = system_text + "\n\n---\n\n" + user_text
    return jsonify({"prompt": full_prompt})


@app.route("/manual/ai_reading", methods=["POST"])
@login_required
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
    system_text, user_text, err = _build_manual_reading(data)
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

    uid = user["id"]

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
        except Exception as e:  # 串流途中任何失敗都退回剛扣的 1 點
            db.add_points(uid, 1, "refund", ref="ai_reading_failed")
            app.logger.warning("AI reading stream failed (%s: %s)",
                               type(e).__name__, e)
            yield _sse("error", {
                "error": "解讀產生失敗,已退還 1 點,請稍後再試",
            })

    headers = {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # 若前方有 nginx,關閉其緩衝以確保即時串流
    }
    return Response(stream_with_context(generate()), headers=headers)


# ============================================================
# 會員頁面:會員資料 + 剩餘點數 + 點數異動紀錄
# ============================================================
@app.route("/member", methods=["GET"])
@login_required
def member():
    user = current_user()
    ledger = db.list_ledger(user["id"]) if user else []
    return render_template("member.html", mode="member", user=user, ledger=ledger)


@app.route("/member/test_topup", methods=["POST"])
@login_required
def member_test_topup():
    """[暫時/測試用] 管理員幫自己加 10 測試點數。綠界儲值串好後移除。"""
    user = current_user()
    if not user:
        return jsonify({"error": "未登入"}), 401
    ok, bal = db.add_points(user["id"], 10, "test_topup")
    if not ok:
        return jsonify({"error": "加點失敗"}), 500
    return jsonify({"balance": bal})


# ============================================================
# 管理:登入 / 登出
# ============================================================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if check_password_hash(_ADMIN_PASSWORD_HASH, password):
            session.permanent = False
            session["is_admin"] = True
            session["last_active"] = _now_utc_iso()
            next_url = request.form.get("next", "/admin/history")
            if not next_url.startswith("/"):
                next_url = "/admin/history"
            return redirect(next_url)
        return render_template(
            "admin/login.html", mode="admin_login", error="密碼不正確"
        )

    # GET:檢查是否從逾時跳轉而來
    next_url = request.args.get("next", "/admin/history")
    timeout = request.args.get("timeout") == "1"
    return render_template(
        "admin/login.html", mode="admin_login",
        next_url=next_url,
        timeout=timeout,
        timeout_minutes=ADMIN_IDLE_TIMEOUT_MINUTES,
    )


@app.route("/admin/logout", methods=["GET"])
def admin_logout():
    session.clear()
    return redirect(url_for("landing"))


# ============================================================
# 管理:歷史紀錄
# ============================================================
@app.route("/admin/history", methods=["GET"])
@login_required
def admin_history():
    clients = db.list_clients()
    return render_template(
        "admin/history_list.html",
        mode="admin_list", clients=clients,
    )


@app.route("/admin/history/<path:name>", methods=["GET"])
@login_required
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
@login_required
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


@app.route("/admin/history/<path:name>/fortune", methods=["GET"])
@login_required
def admin_fortune(name):
    try:
        y_i = int(request.args.get("y", ""))
        m_i = int(request.args.get("m", ""))
        d_i = int(request.args.get("d", ""))
        h_i = int(request.args.get("h", ""))
    except (TypeError, ValueError):
        return render_template(
            "admin/fortune.html",
            mode="admin_fortune", detail_name=name,
            error="缺少命盤年月日時參數(y/m/d/h)",
            fortune=None,
            fortune_chart_args={"y": "", "m": "", "d": "", "h": ""},
            fortune_year=datetime.now().year,
        )

    try:
        year_i = int(request.args.get("year", datetime.now().year))
    except ValueError:
        year_i = datetime.now().year

    fortune = None
    error = None
    chart_gender = db.get_chart_gender(name, y_i, m_i, d_i, h_i)
    try:
        chart_dt = datetime(y_i, m_i, d_i, h_i, 0)
        fortune = analyze_fortune(chart_dt, year_i, gender=chart_gender)
    except ValueError as e:
        error = f"日期或流年格式錯誤({e})"
    except KeyError as e:
        error = f"查無資料:{e}"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    return render_template(
        "admin/fortune.html",
        mode="admin_fortune",
        detail_name=name,
        fortune=fortune,
        fortune_year=year_i,
        fortune_chart_args={"y": y_i, "m": m_i, "d": d_i, "h": h_i},
        chart_gender=chart_gender,
        error=error,
    )


@app.route("/admin/history/<path:name>/fortune/export", methods=["GET"])
@login_required
def admin_fortune_export(name):
    """匯出該流年盤的完整 AI 解讀資料(JSON)。"""
    try:
        y_i = int(request.args.get("y", ""))
        m_i = int(request.args.get("m", ""))
        d_i = int(request.args.get("d", ""))
        h_i = int(request.args.get("h", ""))
        year_i = int(request.args.get("year", datetime.now().year))
    except (TypeError, ValueError):
        abort(400, "缺少參數(y/m/d/h/year)")

    chart_gender = db.get_chart_gender(name, y_i, m_i, d_i, h_i)
    try:
        chart_dt = datetime(y_i, m_i, d_i, h_i, 0)
        fortune = analyze_fortune(chart_dt, year_i, gender=chart_gender)
    except Exception as e:
        abort(500, f"{type(e).__name__}: {e}")

    # 姓名隱碼:保留第一個字,其餘用 *
    if name:
        masked_name = name[0] + "*" * (len(name) - 1) if len(name) > 1 else name
    else:
        masked_name = "(unknown)"

    payload = {
        "schema_version": 1,
        "命主": {
            "姓名(隱碼)": masked_name,
            "性別": chart_gender,
            "出生": f"{y_i:04d}-{m_i:02d}-{d_i:02d} {h_i:02d}:00",
        },
        "流年年份": year_i,
        "原命盤": fortune.get("原命盤"),
        "流年": fortune.get("流年"),
        "流月": fortune.get("流月"),
        "斷語": fortune.get("斷語"),
        "四面向": fortune.get("四面向"),
    }

    body = json.dumps(payload, ensure_ascii=False, indent=2)
    return Response(
        body,
        mimetype="application/json; charset=utf-8",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
