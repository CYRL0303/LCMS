# LegacyPilot 组员本地运行与远程数据库连接说明

> 本文给组员或接手 AI 使用。目标是在另一台电脑上拉取代码、启动后端，并连接同一台阿里云 ECS 上的 MySQL / Redis。

## 1. 你需要先准备什么

本机需要安装：

```text
Git
JDK 17
Maven
Docker Desktop（只在使用本地 MySQL/Redis 时需要）
Node.js 20+（只在运行前端时需要）
OpenSSH Client（Windows 一般自带）
```

需要向项目负责人确认，但不要写进 Git：

```text
ECS 公网 IP
ECS SSH 用户名
ECS SSH 登录方式：密码或私钥
MySQL database 名称
MySQL username
MySQL password
Redis password（如果后续启用）
```

不要提交这些文件：

```text
.env
SQL_PASSWORD.md
任何包含真实密码、API Key、服务器登录信息的文件
```

可以提交：

```text
.env.example
docker-compose 示例文件
不含真实密码的文档
```

## 2. 拉取代码

```powershell
git clone <你的仓库地址>
cd Hackathon
git checkout <你的分支名>
```

项目主要目录：

```text
LegacyPilot              Java Spring Boot 后端
LegacyPilot-Frontend     React 前端
deploy                   本地 Docker 示例
```

## 3. 数据库有两种运行方式

### 方式 A：连接共享阿里云数据库（推荐团队协作）

适合：

```text
多台电脑共用同一份数据
回家换电脑继续开发
竞赛前接近真实部署环境
```

当前推荐用 SSH 隧道，不直接把 MySQL 端口暴露给公网。

打开一个单独 PowerShell 窗口，执行：

```powershell
ssh -L 3307:127.0.0.1:3306 <ssh_user>@<ecs_public_ip>
```

示例：

```powershell
ssh -L 3307:127.0.0.1:3306 root@120.26.xxx.xxx
```

这个窗口不要关。它存在时，本机可以通过：

```text
127.0.0.1:3307
```

访问 ECS 里的 MySQL：

```text
本机 127.0.0.1:3307 -> SSH 隧道 -> ECS 127.0.0.1:3306 -> Docker MySQL
```

后端启动前，在另一个 PowerShell 窗口设置环境变量：

```powershell
cd D:\Hackathon\LegacyPilot

$env:SPRING_PROFILES_ACTIVE="dev"
$env:SPRING_DATASOURCE_URL="jdbc:mysql://127.0.0.1:3307/legacypilot"
$env:SPRING_DATASOURCE_USERNAME="legacypilot"
$env:SPRING_DATASOURCE_PASSWORD="<mysql_password>"

mvn.cmd spring-boot:run
```

如果端口 8080 被占用，可以临时换端口：

```powershell
mvn.cmd spring-boot:run -Dspring-boot.run.arguments="--server.port=8081"
```

### 方式 B：本地 Docker 启动 MySQL / Redis（适合离线学习）

适合：

```text
不连接云服务器
自己练习 Docker / MySQL / Redis
不需要共享数据
```

启动本地 MySQL：

```powershell
cd D:\Hackathon
docker compose -f deploy/docker-compose.local.yml up -d mysql
docker compose -f deploy/docker-compose.local.yml ps
```

第一次启动后，进入 MySQL 创建库和用户：

```powershell
docker exec -it legacypilot-mysql mysql -uroot -proot_pwd
```

在 MySQL 里执行：

```sql
CREATE DATABASE legacypilot DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'legacypilot'@'%' IDENTIFIED BY 'legacypilot_pwd';
GRANT ALL PRIVILEGES ON legacypilot.* TO 'legacypilot'@'%';
FLUSH PRIVILEGES;
```

后端本地连接：

```powershell
cd D:\Hackathon\LegacyPilot

$env:SPRING_PROFILES_ACTIVE="dev"
$env:SPRING_DATASOURCE_URL="jdbc:mysql://127.0.0.1:3306/legacypilot"
$env:SPRING_DATASOURCE_USERNAME="legacypilot"
$env:SPRING_DATASOURCE_PASSWORD="legacypilot_pwd"

mvn.cmd spring-boot:run
```

注意：

```text
本地 Docker 数据只在本机 Docker volume 里。
另一台电脑不会自动拿到这份数据。
如果要共享数据，用方式 A。
```

## 4. 启动后端后如何验证

健康检查：

```http
GET http://localhost:8080/api/health/db
```

如果返回数据库连接正常，说明 Spring Boot 已经连上 MySQL。

执行 onboarding：

```http
POST http://localhost:8080/api/onboarding/local-project
```

Body：

```json
{
  "projectName": "LegacyPilot",
  "sourceType": "LOCAL_PATH",
  "localRepoPath": "D:\\Hackathon\\LegacyPilot"
}
```

返回里重点看：

```text
project.projectId
repository.repoId
graph.nodeCount
graph.edgeCount
graph.endpointCount
```

测试 graph：

```http
GET http://localhost:8080/api/code-analysis/repos/{repoId}/graph
```

测试 endpoint trace：

```http
GET http://localhost:8080/api/code-analysis/repos/{repoId}/endpoint-trace?httpMethod=GET&path=/api/example
```

测试 Agent：

```http
POST http://localhost:8080/api/agent/chat
```

Body：

```json
{
  "message": "这个项目有哪些接口",
  "maxCandidates": 3
}
```

当前还没接 Qwen，重点看：

```text
query
toolResults
agentContextText
```

## 5. 前端启动

```powershell
cd D:\Hackathon\LegacyPilot-Frontend
npm.cmd install
npm.cmd run dev
```

默认地址：

```text
http://localhost:5173
```

当前前端还没有完整绑定所有后端 API。后端和 Postman 验证优先级更高。

## 6. 常见问题

### 1. SSH 隧道窗口能不能关？

连接共享云 MySQL 时不能关。

关了以后：

```text
127.0.0.1:3307 -> ECS MySQL
```

这条转发就断了，后端会连不上数据库。

### 2. push 代码时需要关 SSH 隧道吗？

不需要。

SSH 隧道只是本机网络连接，不会进入 Git。

### 3. Maven 下载依赖失败怎么办？

先确认网络。然后在项目后端目录重新执行：

```powershell
cd D:\Hackathon\LegacyPilot
mvn.cmd test
```

### 4. 8080 端口被占用怎么办？

查看占用：

```powershell
netstat -ano | findstr :8080
```

或者直接换端口：

```powershell
mvn.cmd spring-boot:run -Dspring-boot.run.arguments="--server.port=8081"
```

### 5. 数据库表谁创建？

Spring Boot 启动时，Flyway 会执行：

```text
LegacyPilot/src/main/resources/db/migration/
```

里面的 migration 文件负责建表和后续结构变更。

不要手动删除：

```text
flyway_schema_history
```

### 6. Docker volume 能不能删？

谨慎。

这个命令会删除 MySQL 数据：

```powershell
docker compose -f deploy/docker-compose.local.yml down -v
```

只想停止容器时，不要加 `-v`：

```powershell
docker compose -f deploy/docker-compose.local.yml down
```

## 7. 组员接手开发时先看哪些文档

按顺序读：

```text
PROJECT_OVERVIEW.zh-CN.md
PROJECT_PROGRESS_SUMMARY.zh-CN.md
PROJECT_CONTEXT_PROMPT.zh-CN.md
TEAM_SETUP.zh-CN.md
Alibaba_Cloud.md
```

当前下一步开发任务以 `PROJECT_PROGRESS_SUMMARY.zh-CN.md` 的“给接手 AI / 组员的执行说明”为准。
