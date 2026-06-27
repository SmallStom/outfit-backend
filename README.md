# outfit-backend

「数字衣橱」小程序后端服务，基于 **Python 3.13 + FastAPI + SQLAlchemy 2.0（异步）+ PostgreSQL** 构建。

## 技术栈

- **Web 框架**：FastAPI
- **ORM**：SQLAlchemy 2.0 async + Alembic
- **数据库**：PostgreSQL 16
- **认证**：JWT + 微信小程序登录
- **文件存储**：腾讯云 COS STS / 本地上传
- **容器化**：Docker + Docker Compose

## 目录结构

```
outfit-backend/
├── alembic/                # 数据库迁移
├── app/
│   ├── api/v1/             # API 路由
│   ├── core/               # 配置、异常、安全、响应、时区
│   ├── db/                 # 数据库引擎、Session、依赖注入
│   ├── models/             # SQLAlchemy 模型
│   ├── schemas/            # Pydantic 请求/响应模型
│   ├── services/           # 业务逻辑
│   ├── main.py             # FastAPI 入口
├── scripts/                # 种子脚本
├── .env.example            # 环境变量模板
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 快速开始

### 1. 环境准备

复制环境变量模板并填写真实配置：

```bash
cp .env.example .env
```

### 2. 本地运行

```bash
# 安装依赖
pip install -r requirements.txt

# 数据库迁移
alembic upgrade head

# 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问文档：

- Swagger UI：`http://127.0.0.1:8000/docs`
- ReDoc：`http://127.0.0.1:8000/redoc`

### 3. Docker 运行

#### 方式一：Docker Compose（含 PostgreSQL）

```bash
docker-compose up -d
```

会启动 `db`（PostgreSQL）和 `api`（FastAPI）两个服务，API 端口 `8000`，数据库端口 `5432`。

#### 方式二：使用外部数据库

将 `.env` 中的 `DATABASE_URL` 指向外部 PostgreSQL，例如：

```env
DATABASE_URL=postgresql+asyncpg://outfit:outfit@212.64.10.45:5432/outfit_db
```

然后直接构建并运行 API 容器：

```bash
docker build -t outfit-backend .
docker run -d --env-file .env -p 8000:8000 --name outfit-api outfit-backend
```

## 环境变量说明

| 变量 | 说明 | 示例 |
|---|---|---|
| `APP_ENV` | 当前环境 | `development` / `production` |
| `DEBUG` | 调试模式 | `true` / `false` |
| `TZ` | 时区 | `Asia/Shanghai` |
| `DATABASE_URL` | PostgreSQL 连接地址 | `postgresql+asyncpg://outfit:outfit@localhost:5432/outfit_db` |
| `SECRET_KEY` | JWT 密钥 | 至少 32 位随机字符串 |
| `ACCESS_TOKEN_EXPIRE_DAYS` | JWT 有效期（天） | `7` |
| `WECHAT_APPID` / `WECHAT_SECRET` | 微信小程序登录凭证 | - |
| `COS_*` | 腾讯云 COS STS 配置 | - |
| `AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL` | AI 大模型配置 | - |
| `ALIYUN_*` | 阿里云虚拟试衣配置 | - |

## 数据库迁移

```bash
# 生成迁移（需先确保模型已更新）
alembic revision --autogenerate -m "describe"

# 升级
alembic upgrade head

# 回退一级
alembic downgrade -1
```

## 已实现的 API 模块

| 模块 | 主要接口 |
|---|---|
| 认证/用户 | 微信登录、刷新 Token、用户资料 |
| 衣橱 | 衣物 CRUD、穿着记录、标签、AI 识别占位 |
| 搭配 | AI 推荐、搭配 CRUD、搭配集 CRUD |
| 身材档案 | 身材档案 CRUD、激活、身材类型 |
| 穿搭历史 | 历史列表、近期记录 |
| 洗护 | 洗护提醒、标记完成 |
| 统计 | 资产概览、品类分布、闲置、单次穿着成本 |
| 购前预演 | 购前分析、历史记录 |
| 虚拟试衣 | 分类衣物、试衣预设、生成占位 |
| 社区 | 帖子列表/详情/点赞/发布、风格标签 |
| 收藏 | 收藏列表、帖子/单品收藏切换 |
| 上传 | COS STS、本地上传 |

## 部署说明

1. 生产环境务必修改 `SECRET_KEY`、数据库密码、COS 与 AI 密钥。
2. 使用 `docker-compose` 时，建议将 `.env` 替换为 `.env.production` 并通过 `env_file` 加载。
3. 上传文件默认保存到 `uploads/` 目录，生产环境建议挂载持久化卷或改用 COS。
4. AI 识别、搭配推荐、购前预演、虚拟试衣生成当前为规则版或占位实现，配置对应密钥后可接入真实服务。

## 开发约定

- 所有接口统一返回 `{ code, message, data }` 格式。
- 时间统一使用 `Asia/Shanghai`。
- 接口字段使用驼峰命名（`coverColor`、`isLiked` 等）。

## License

MIT
