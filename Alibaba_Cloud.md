# Alibaba Cloud Deployment Notes

## Goal

LegacyPilot should use one shared cloud environment for contest development and final demo.

Target shape:

```text
Alibaba Cloud ECS
  -> Docker Compose
      -> MySQL
      -> Redis
      -> Backend, later
      -> Frontend, later
```

If every development machine connects to the same ECS MySQL and Redis, data changes are shared immediately:

```text
Laptop A writes data -> ECS MySQL
Laptop B reads data  -> same ECS MySQL
Cloud backend reads  -> same ECS MySQL
```

This avoids repeatedly exporting and importing local Docker database dumps between machines.

## Why Not Only Local Docker

Local Docker MySQL stores data in a local Docker volume.

That means:

```text
Current computer Docker volume != Home computer Docker volume
```

To move local data between computers, we would need:

```text
mysqldump export
mysql import
```

This works, but it is manual and easy to forget.

For the hackathon, a shared ECS database is more convenient and closer to the final deployment requirement.

## Recommended Plan

### Stage 1: Keep Local Docker For Learning

Use local Docker to understand the mechanics:

```text
deploy/docker-compose.local.yml
  mysql
  redis
  local volumes
```

Local MySQL can be created manually first:

```sql
CREATE DATABASE legacypilot DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'legacypilot'@'%' IDENTIFIED BY 'legacypilot_pwd';
GRANT ALL PRIVILEGES ON legacypilot.* TO 'legacypilot'@'%';
FLUSH PRIVILEGES;
```

This is for learning and local testing only.

### Stage 2: Create Alibaba Cloud ECS

Create one ECS instance for the contest environment.

Suggested minimum:

```text
OS: Ubuntu or Alibaba Cloud Linux
CPU/RAM: 2C4G preferred, 2C2G acceptable for a small demo
Disk: 40GB+
Network: public IP enabled
```

Install:

```text
Docker
Docker Compose plugin
Git
```

### Stage 3: Add Remote Compose

Create a separate remote compose file later:

```text
deploy/docker-compose.remote.yml
```

Do not reuse local config blindly.

Remote compose should run:

```text
mysql
redis
backend, later
frontend, later
```

Use Docker volumes:

```text
legacypilot_mysql_data
legacypilot_redis_data
```

These volumes preserve data across container restart and server reboot.

### Stage 4: Use .env For Cloud Secrets

Do not hardcode cloud passwords in YAML.

Use a remote `.env` file on ECS:

```text
MYSQL_ROOT_PASSWORD=change_me
MYSQL_DATABASE=legacypilot
MYSQL_USER=legacypilot
MYSQL_PASSWORD=change_me
REDIS_PASSWORD=change_me
QWEN_API_KEY=change_me
QWEN_BASE_URL=change_me
QWEN_MODEL=qwen-plus
```

Do not commit real `.env` files.

Commit only:

```text
.env.example
```

### Stage 5: Database Initialization

There are two useful mechanisms:

#### Init SQL

MySQL Docker runs SQL files in:

```text
/docker-entrypoint-initdb.d/
```

only when the MySQL data directory is empty.

Use it for:

```text
first-time database creation
schema creation
optional demo seed data
```

Important limitation:

```text
init SQL runs only once per empty volume
```

If the volume already exists, changing init SQL will not apply automatically.

#### Migrations

Later, use migration files for ongoing schema changes:

```text
LegacyPilot/src/main/resources/db/migration/
  V1__init_schema.sql
  V2__add_code_analysis_snapshot.sql
```

Flyway can apply migrations automatically when Spring Boot starts.

Recommended direction:

```text
init SQL: first bootstrap
Flyway migration: long-term schema evolution
mysqldump: transfer real current data when needed
```

### Stage 6: Local Backend Connects To ECS Database

During development, local Spring Boot can connect to ECS MySQL:

```text
SPRING_DATASOURCE_URL=jdbc:mysql://ECS_PUBLIC_IP:3306/legacypilot
SPRING_DATASOURCE_USERNAME=legacypilot
SPRING_DATASOURCE_PASSWORD=...
```

Redis:

```text
REDIS_HOST=ECS_PUBLIC_IP
REDIS_PORT=6379
REDIS_PASSWORD=...
```

This lets multiple computers share the same data.

### Stage 7: Final Contest Deployment

Eventually deploy backend and frontend to the same ECS.

Final production-like shape:

```text
frontend container
  -> backend container
      -> mysql container, internal Docker network
      -> redis container, internal Docker network
      -> Qwen Cloud API
```

When backend runs inside Docker on ECS, it should connect by service name:

```text
jdbc:mysql://mysql:3306/legacypilot
redis://redis:6379
```

Not by public IP.

## Security Notes

Do not expose MySQL and Redis to the whole internet if avoidable.

Safer options:

```text
1. Restrict ECS security group to your current public IP for port 3306.
2. Do not expose Redis publicly unless needed.
3. Use strong passwords.
4. Prefer SSH tunnel for database access if possible.
```

Minimum acceptable contest setup:

```text
MySQL: strong password, security group restricted to developer IPs
Redis: password enabled or not exposed publicly
Backend/Frontend: publicly accessible for demo
```

## What We Should Do Next

1. Finish local understanding of MySQL and Redis Docker.
2. Add Spring Boot JDBC dependency and test DB connection locally.
3. Create schema migration for core tables:

```text
legacy_project
repository_index
analysis_task
code_analysis_snapshot
```

4. Create `docker-compose.remote.yml`.
5. Create ECS and install Docker.
6. Start MySQL and Redis on ECS.
7. Point local backend to ECS database.
8. Later deploy backend and frontend containers to ECS.

