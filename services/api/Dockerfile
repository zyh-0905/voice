FROM python:3.12-slim
WORKDIR /app
COPY services/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/api ./services/api
# 运维与 E2E 脚本进镜像:real-api 套件要在容器内准备测试库并起 API,
# 而它跑在 compose 网络里才能连到 postgres(数据库端口不发布到宿主机)。
COPY scripts ./scripts
CMD ["uvicorn", "services.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
