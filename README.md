# AQL 检测系统部署版

面向质检团队的中文 Web 应用：多用户登录、角色权限、AQL 抽样计算、检验单、缺陷登记、自动判定、打印报告与 CSV 导出。技术栈为 Flask + SQLAlchemy + SQLite，无前端构建步骤。

## 服务器要求

- Linux 服务器，建议 1 核 CPU / 1 GB 内存起
- Docker Engine 24+ 与 Docker Compose v2
- 对外开放 8000 端口，或由 Nginx 反向代理到本机 8000

Ubuntu 可按 Docker 官方安装文档安装 Docker Engine；安装后确认：

```bash
docker --version
docker compose version
```

## 配置并启动

```bash
unzip AQL检测系统部署版.zip
cd aql-deploy
cp .env.example .env
openssl rand -hex 32
nano .env                 # 填入管理员名、强密码及上一步生成的 SECRET_KEY
docker compose up -d --build
docker compose logs -f
```

浏览器访问 `http://服务器IP:8000`。默认端口是 **8000**。

首次启动且数据库没有用户时，系统用 `ADMIN_USER` 与 `ADMIN_PASSWORD` 创建首个管理员。之后可在“用户”页新增管理员或检验员、禁用账号。数据库已有用户后，修改这两个变量不会重置管理员密码。

`.env` 示例字段：

- `ADMIN_USER`：首个管理员用户名
- `ADMIN_PASSWORD`：首个管理员密码（建议 16 位以上随机密码）
- `SECRET_KEY`：会话签名密钥，务必随机生成且长期保持不变
- `DATA_DIR=/data`：容器内数据库目录
- `COOKIE_SECURE=1`：仅在 HTTPS 已正确配置后启用安全 Cookie；直接用 HTTP 测试时保留为 `0`

不要把 `.env` 提交到版本库，也不要与压缩包一起转发。

## 权限

- `admin`：查看全部检验单；创建、启用或禁用用户。
- `inspector`：只能查看、编辑、删除自己创建的检验单。

## 数据与备份

SQLite 位于 Docker 命名卷 `aql_data` 的 `/data/aql.db`。在线备份建议先短暂停止写入：

```bash
docker compose stop aql
docker run --rm -v aql-deploy_aql_data:/data -v "$PWD":/backup alpine \
  sh -c 'cp /data/aql.db /backup/aql-$(date +%F-%H%M).db'
docker compose start aql
```

卷名通常是“目录名 + `_aql_data`”；执行 `docker volume ls` 可核对。恢复前先停止服务，并保留当前数据库副本。

## Nginx 反向代理建议

生产环境建议只让应用监听服务器本机/内网，并由 Nginx 提供 HTTPS。站点配置核心示例：

```nginx
server {
    listen 80;
    server_name aql.example.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

再用你现有的证书方案（例如 Certbot）启用 HTTPS。防火墙只开放 80/443；若已用 Nginx，不应把 8000 暴露到公网，可将 compose 端口改为 `127.0.0.1:8000:8000`。

## 抽样规则说明

系统内置 MIL-STD-105E / ISO 2859-1 的**正常检验、单次抽样**：Table I 字码与 Table II-A 标准 AQL 档位（0.010–10.0），包括上下箭头转用相邻抽样方案；箭头方案导致不同样本量时，实际抽样量取三类中最大值。若计算样本量达到或超过批量，则转为 100% 检验。

核对锚点：`n=125, AQL 1.0 → Ac 3 / Re 4`；`n=80, AQL 2.5 → 5 / 6`；`n=200, AQL 1.0 → 5 / 6`。

公开核对资料：

- MIL-STD-105E 原表扫描：https://cqeacademy.com/wp-content/uploads/2014/03/milstd105e.pdf
- York University 接收抽样讲义（含 Table I 与示例）：http://www.yorku.ca/ptryfos/accsamp.pdf
- 可读版 AQL 表：https://www.davincipipes.com/_files/ugd/77c265_c88a3a7a3c6049888f7cfafa4a14309a.pdf

AQL 是抽样判定工具，不等同于对整批缺陷率的保证；关键安全项目应结合合同、法规及风险要求决定是否全检。

## 运维命令

```bash
docker compose ps
docker compose logs --tail=200 aql
docker compose restart aql
docker compose down              # 保留命名卷数据
docker compose down -v           # 会删除数据库卷，请勿随意执行
```
