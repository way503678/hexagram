# -*- coding: utf-8 -*-
"""
命卦排盤 Flask 網頁介面

路由總覽:
  /                  首頁(landing page)
  /cast              時辰起卦(梅花易數)
  /manual            手動排卦(金錢卦/搖卦結果)
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
from datetime import datetime

from flask import (
    Flask, request, render_template, session, redirect, url_for, abort,
    Response,
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

# 管理員密碼:以環境變數設定。預設 "admin",部署時務必改掉。
_ADMIN_PASSWORD_PLAIN = os.environ.get("ADMIN_PASSWORD", "admin")
_ADMIN_PASSWORD_HASH = generate_password_hash(_ADMIN_PASSWORD_PLAIN)


def login_required(view):
    """裝飾器:要求已登入。否則導去登入頁。"""
    @wraps(view)
    def wrapper(*a, **kw):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*a, **kw)
    return wrapper


def _parse_dt_args():
    """從 query string 取年月日時,缺者以現在補齊。"""
    y = request.args.get("y", "").strip()
    m = request.args.get("m", "").strip()
    d = request.args.get("d", "").strip()
    h = request.args.get("h", "").strip()
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
# ============================================================
@app.route("/manual", methods=["GET"])
def manual():
    y, m, d, h, default_y, default_m, default_d, default_h = _parse_dt_args()

    # 性別 & 問事類別
    gender = request.args.get("gender", "").strip().upper()
    if gender not in ("M", "F"):
        gender = ""
    aspect = request.args.get("aspect", "all").strip().lower()
    if aspect not in ("all", "love", "health", "work", "wealth"):
        aspect = "all"

    yao_vals = []
    has_yao_input = False
    for i in range(6):
        v = request.args.get(f"y{i}", "")
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
        r=result, yao_vals=yao_vals,
        aspects=aspects_result,
        gender=gender,
        aspect_choice=aspect,
        y=y or str(default_y), m=m or str(default_m),
        d=d or str(default_d), h=(h if h != "" else str(default_h)),
        default_y=default_y, default_m=default_m,
        default_d=default_d, default_h=default_h,
        error=error,
    )


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
            next_url = request.form.get("next", "/admin/history")
            if not next_url.startswith("/"):
                next_url = "/admin/history"
            return redirect(next_url)
        return render_template(
            "admin/login.html", mode="admin_login", error="密碼不正確"
        )

    next_url = request.args.get("next", "/admin/history")
    return render_template(
        "admin/login.html", mode="admin_login", next_url=next_url
    )


@app.route("/admin/logout", methods=["GET"])
def admin_logout():
    session.pop("is_admin", None)
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
