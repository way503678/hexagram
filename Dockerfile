# syntax=docker/dockerfile:1.6
# ==========================================================
# 命卦排盤 - Dockerfile（單階段，並處理 zhdate 0.1 舊套件相容性）
# ==========================================================
FROM python:3.12-slim
ENV LANG=C.UTF-8 \
    TZ=Asia/Taipei \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# zhdate 0.1 是 2019 舊套件（用 use_2to3），新版 setuptools 拒裝
# 先降版 setuptools 再裝 requirements
COPY requirements.txt .
RUN pip install "setuptools<58" "wheel" && \
    pip install -r requirements.txt
# 建立非 root 使用者
RUN useradd -m -u 1000 appuser
# 複製所有 Python 程式檔
COPY --chown=appuser:appuser *.py ./
# 個資/免責條文單一來源(web + App 共用)
COPY --chown=appuser:appuser legal.json ./
# 複製判讀核心包（divination/core + divination/aspects）
COPY --chown=appuser:appuser divination/ ./divination/
# 複製 Jinja 模板與靜態檔(CSS 等)
COPY --chown=appuser:appuser templates/ ./templates/
COPY --chown=appuser:appuser static/ ./static/
# 複製 docs/(AI 解讀 prompt 等)
COPY --chown=appuser:appuser docs/ ./docs/
USER appuser
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "180", \
     "--access-logfile", "-", \
     "app:app"]
