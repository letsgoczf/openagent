## OpenAgent Docker/运行部署详细设计

### 1. 目标
- 为开发环境提供一键运行（backend + 可选 qdrant + sqlite 持久化）
- 前端与后端解耦：前端可独立开发，后端提供统一 API/WS

### 2. 推荐的容器化组件
- 后端 FastAPI
- Qdrant（如需要）
- OCR 依赖组件（可选：tesseract/paddleocr 以镜像方式提供）

### 3. docker-compose 建议（高层逻辑）
- `backend`：暴露 API/WS
- `qdrant`：数据卷持久化
- `frontend`（可选）：开发阶段可不容器化

### 4. 配置映射要求
- 挂载配置文件：`openagent/config/openagent.yaml`
- 挂载 data 目录：SQLite 与抽取缓存（避免丢）
- 环境变量：
  - OpenAI/其他 provider 密钥通过 env 注入（不写入镜像）

### 5. 验收标准
- `docker compose up` 后能访问 WS/REST
- 支持文档导入 -> ingestion job -> Chat -> 返回 citations

