# 吉大校园智能体（JLU Campus Agent）

基于 LLM + RAG + Tool-Calling 的吉林大学校园生活智能助手，支持校园问答、OA 通知检索、教务系统查询等功能。

## 功能

- **校园知识问答** — 本地 RAG 知识库覆盖校园卡、缓考、奖学金、大创等常见问题
- **OA 校内通知检索** — 定时抓取吉大电子校务平台通知，支持语义搜索
- **教务课表查询** — HTTP 登录吉大 CAS + 教务系统，查询本人本学期课表
- **联网搜索** — 对本地资料不足的问题自动联网搜索补充
- **多轮对话记忆** — 基于 Redis 的对话历史管理，支持摘要压缩

## 技术架构

```
frontend (Vue 3 + Vant)  →  FastAPI  →  LangGraph Agent
                              │
                              ├── DeepSeek API (LLM + Tool Calling)
                              ├── Redis (会话 / 教务登录态 / 对话记忆)
                              ├── SQLite (用户 / 对话 / OA 通知)
                              ├── ChromaDB (本地知识库向量检索)
                              └── 吉大 CAS / 教务系统 (HTTP 登录 + 数据查询)
```

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3, TypeScript, Vant UI, Axios |
| 后端 | FastAPI, Python 3 |
| Agent | LangGraph, DeepSeek V4 Pro (tool-calling) |
| 检索 | ChromaDB 向量检索 + BM25 混合 |
| 存储 | SQLite, Redis |
| LLM | DeepSeek API (Chat + Embedding) |

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 20+
- Redis 7+

### 1. 克隆仓库

```bash
git clone https://github.com/TToppsss/jlu-campus-agent.git
cd jlu-campus-agent
```

### 2. 后端配置

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

复制并编辑环境变量：

```bash
cp .env.example .env
```

`.env` 必填项：

```env
DEEPSEEK_API_KEY=sk-xxx       # DeepSeek API Key
SILICONFLOW_API_KEY=sk-xxx    # SiliconFlow API Key (Embedding)
JWT_SECRET_KEY=your-secret    # JWT 签名密钥（自行生成随机字符串）
REDIS_URL=redis://127.0.0.1:6379/0
```

### 3. 启动 Redis

```bash
# macOS
brew install redis && brew services start redis

# Windows
# 下载 Windows 版 Redis 或使用 Docker
docker run -d -p 6379:6379 redis:7-alpine

# Linux
sudo apt install redis && sudo systemctl start redis
```

### 4. 初始化知识库

```bash
cd backend
python -m scripts.ingest_docs
```

### 5. 启动后端

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档自动生成：http://localhost:8000/docs

### 6. 启动前端（开发模式）

```bash
cd frontend
npm install
npm run dev
```

开发模式下前端运行在 http://localhost:5173，API 请求自动代理到后端 8000 端口。

### 7. 生产部署（单端口）

构建前端静态文件，由 FastAPI 统一托管：

```bash
cd frontend && npm run build
cd ../backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000 即可使用完整应用。

## 部署方案

### 花生壳内网穿透（免公网 IP）

1. 下载 [花生壳客户端](https://hsk.oray.com)，注册并实名认证

2. 在花生壳中添加端口映射：

| 设置项 | 值 |
|--------|-----|
| 内网主机 | `127.0.0.1` |
| 内网端口 | `8000` |

3. 启动后端（单端口模式）：

```bash
cd frontend && npm run build
cd ../backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

4. 花生壳会分配一个外网域名（如 `xxx.oray.vip`），将域名分享给其他人即可访问

> 免费版每月 1GB 流量、1Mbps 带宽，适合小规模使用。

### 云服务部署

| 组件 | 推荐平台 |
|------|----------|
| 后端 | Railway / Fly.io / 阿里云 ECS |
| 前端 | Vercel / Netlify（连 GitHub 自动部署）|
| Redis | Upstash（免费云 Redis）|

## 项目结构

```
├── backend/
│   ├── app/
│   │   ├── agent/        # LangGraph Agent 编排 + 工具定义
│   │   ├── api/          # FastAPI 路由（auth, edu, agent, conversations）
│   │   ├── edu/          # 吉大 CAS 登录 + 教务系统 HTTP 客户端
│   │   ├── rag/          # 向量检索 + 知识库导入
│   │   ├── oa/           # OA 通知爬取与增量更新
│   │   ├── llm/          # DeepSeek API 客户端
│   │   └── db/           # 数据库模型
│   ├── scripts/          # 知识库导入等运维脚本
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── views/        # 页面组件（聊天、登录等）
│       ├── api/          # API 客户端
│       └── router/       # 前端路由
└── data/
    └── raw_docs/         # 知识库原始 Markdown 文档
```

## 教务登录

本项目通过纯 HTTP 请求实现吉大 CAS 统一认证登录：

1. 前端输入账号密码 → 后端 POST CAS 登录页获取图形验证码
2. 用户输入图形码 → 服务端触发企业微信验证码
3. 用户输入微信码 → 服务端完成登录，获取教务系统 Cookie
4. Cookie 仅存储在 Redis 中，**密码不被保存**
5. 登录态通过定时心跳保持

## API 概览

| 路径 | 说明 |
|------|------|
| `POST /api/auth/register` | 注册应用账号 |
| `POST /api/auth/login` | 登录应用 |
| `POST /api/agent/chat` | 智能体对话 |
| `GET /api/edu/status` | 查询教务登录状态 |
| `POST /api/edu/login_init` | 教务登录 — 初始化 |
| `POST /api/edu/login_send_wechat` | 教务登录 — 发送微信码 |
| `POST /api/edu/login_confirm` | 教务登录 — 确认登录 |
| `GET /api/conversations` | 对话列表 |
| `DELETE /api/conversations/{id}` | 删除对话 |

## License

MIT
