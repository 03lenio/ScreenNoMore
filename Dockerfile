FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && \
    adduser --system --ingroup app app && \
    mkdir /data /health && \
    chown app:app /data /health

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=app:app main.py ./main.py
COPY --chown=app:app backend ./backend

USER app

EXPOSE 8080

CMD ["gunicorn", "--no-control-socket", "--bind", "0.0.0.0:8080", "backend.web.app:app"]
