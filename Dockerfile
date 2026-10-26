FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp XDG_CACHE_HOME=/tmp/.cache
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt
RUN groupadd --gid 10001 agent && useradd --uid 10001 --gid agent --no-create-home --home-dir /tmp agent
COPY fusion.py catalog.py runtime.py eai.py server.py agents.json ./
COPY static/ ./static/
USER 10001:10001
EXPOSE 8080
CMD ["python", "server.py"]

