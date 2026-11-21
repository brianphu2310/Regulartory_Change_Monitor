# Regulatory change monitor: one container run = one monitoring pass.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt requirements-monitor.txt ./
RUN pip install --no-cache-dir pandas requests feedparser beautifulsoup4 \
    && useradd --create-home monitor
COPY classifier.py impact_model.py ./
COPY monitor/ monitor/
RUN mkdir -p data/live reports && chown -R monitor /app
USER monitor
ENTRYPOINT ["python", "-m", "monitor.run"]
