FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && \
    adduser --system --ingroup app app && \
    mkdir /data && \
    chown app:app /data

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=app:app main.py ./main.py
COPY --chown=app:app backend ./backend

USER app

CMD ["python", "main.py"]
