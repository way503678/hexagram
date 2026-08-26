# syntax=docker/dockerfile:1.6
# ==========================================================
# 命果 MINGO - Dockerfile（單階段）
# ==========================================================
FROM python:3.12-slim
ENV LANG=C.UTF-8 \
    TZ=Asia/Taipei \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
# 建立非 root 使用者
RUN useradd -m -u 1000 appuser
# 複製所有 Python 程式檔
COPY --chown=appuser:appuser *.py ./
# 個資/免責條文單一來源(web + App 共用)
COPY --chown=appuser:appuser legal.json ./
# Apple AppTransaction JWS 驗證所需的官方根憑證
COPY --chown=appuser:appuser certs/ ./certs/
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
