# 私有化部署指南

办公小浣熊复刻版私有化部署：全栈 Docker Compose，离线镜像包，模型可本地化。

## 架构

```
nginx(可选) → frontend(Vite build, 静态) + backend(FastAPI)
            ↘ Postgres / Redis / Qdrant / MinIO
            ↘ embedding(bge-m3, 本地)
            ↘ sandbox(Docker-in-Docker 或 sibling 容器)
```

## 1. 在线部署（开发/测试）

```sh
docker compose -f deploy/docker-compose.prod.yml up -d
```

包含：postgres / redis / qdrant / minio / embedding(bge-m3) / backend / frontend。

## 2. 离线部署（生产/内网）

### 2.1 在有网环境打包镜像

```sh
# 构建所有镜像
docker compose -f deploy/docker-compose.prod.yml build

# 导出为离线包
docker save \
  raccoon-backend:latest \
  raccoon-frontend:latest \
  raccoon-sandbox:latest \
  ghcr.io/huggingface/text-embeddings-inference:cpu-1.5 \
  postgres:16-alpine redis:7-alpine qdrant/qdrant:latest minio/minio:latest \
  -o raccoon-images.tar

# 打包部署文件
tar czf raccoon-deploy.tar.gz deploy/ .env.example
```

### 2.2 内网部署

```sh
# 加载镜像
docker load -i raccoon-images.tar
# 解压部署文件
tar xzf raccoon-deploy.tar.gz
cp .env.example .env  # 填入配置
docker compose -f deploy/docker-compose.prod.yml up -d
```

## 3. 模型本地化

私有化默认仍走 ARK（需外网）。完全离线时切换本地模型：

```env
# .env
LLM_PROVIDER=vllm
VLLM_BASE_URL=http://local-llm:8001/v1
VLLM_API_KEY=local
ARK_MODEL=Qwen2.5-32B-Instruct   # 本地 vLLM 加载的模型

# embedding 用本地 bge-m3
EMBED_MODEL=BAAI/bge-m3
EMBED_MODEL_DIR=/models/bge-m3   # 预下载到本地
```

vLLM 部署（GPU 机器）：
```sh
docker run --gpus all -p 8001:8001 \
  -v /models:/models \
  vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-32B-Instruct --port 8001
```

## 4. 软硬一体机规格

| 档位 | GPU | 显存 | 内存 | 存储 | 适用 |
|------|-----|------|------|------|------|
| 轻量 | 无（CPU） | — | 32GB | 500GB SSD | 小团队，数据分析为主 |
| 标准 | 1× A10 | 24GB | 64GB | 1TB SSD | 中型企业，本地 LLM |
| 旗舰 | 2× A100 | 80GB×2 | 128GB | 2TB NVMe | 大型企业，多模型并发 |

一体机预装：OS + Docker + 全栈镜像 + 本地模型权重，开机即用。
交付时 `docker compose up -d` 即可启动服务。

## 5. 安全合规

- 数据加密：Postgres/MinIO 启用 TLS（生产配置）
- 沙箱：run_code 走 Docker 强隔离（--network none --read-only --memory）
- 审计：所有工具调用写入 `audit.log`（hooks 引擎）
- 脱敏：敏感数据（手机/身份证/邮箱/银行卡）自动脱敏
- 多租户：按 tenant 隔离数据与工具白名单
