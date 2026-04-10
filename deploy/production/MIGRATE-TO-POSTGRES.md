# Migrate from SQLite to PostgreSQL

Use this guide if your current ArcReel deployment is running on the default SQLite setup and you want to move to PostgreSQL.

## Prerequisites

- Docker and Docker Compose are installed
- ArcReel is currently using SQLite, with the database stored at `projects/.arcreel.db`

## Migration Steps

### 1. Stop ArcReel

```bash
# If ArcReel is running through Docker
docker compose down

# If ArcReel is running directly from the command line, stop the uvicorn process
```

### 2. Back Up the SQLite Database

```bash
cp projects/.arcreel.db projects/.arcreel.db.bak
```

### 3. Configure Environment Variables

Add the following variable to `.env` so the PostgreSQL container can initialize correctly:

```env
POSTGRES_PASSWORD=your_database_password
```

> You do not need to set `DATABASE_URL` manually. `docker-compose.yml` builds it automatically from `POSTGRES_PASSWORD`.

### 4. Start PostgreSQL

Start only the database service first:

```bash
docker compose up -d postgres
```

Wait until the health check passes:

```bash
docker compose ps  # Confirm that postgres is healthy
```

### 5. Migrate the Data

Use `pgloader` inside the ArcReel container to migrate the SQLite data directly into PostgreSQL:

```bash
docker compose run --rm arcreel bash -c "
  apt-get update && apt-get install -y --no-install-recommends pgloader &&
  pgloader sqlite:///app/projects/.arcreel.db            postgresql://arcreel:\${POSTGRES_PASSWORD}@postgres:5432/arcreel
"
```

> `pgloader` automatically handles common SQLite-to-PostgreSQL differences such as booleans and time formats, and it only imports data rather than recreating the existing schema.

### 6. Validate the Data

```bash
docker compose exec postgres psql -U arcreel -d arcreel -c "
  SELECT 'tasks' AS tbl, COUNT(*) FROM tasks
  UNION ALL
  SELECT 'api_calls', COUNT(*) FROM api_calls
  UNION ALL
  SELECT 'agent_sessions', COUNT(*) FROM agent_sessions
  UNION ALL
  SELECT 'api_keys', COUNT(*) FROM api_keys;
"
```

Compare the counts with the SQLite database:

```bash
sqlite3 projects/.arcreel.db "
  SELECT 'tasks', COUNT(*) FROM tasks
  UNION ALL
  SELECT 'api_calls', COUNT(*) FROM api_calls
  UNION ALL
  SELECT 'agent_sessions', COUNT(*) FROM agent_sessions
  UNION ALL
  SELECT 'api_keys', COUNT(*) FROM api_keys;
"
```

### 7. Start the Full Stack

```bash
docker compose up -d
```

Open `http://<your-ip>:1241` and confirm the service is working normally.

---

## Roll Back to SQLite

If you need to revert:

1. Stop the stack: `docker compose down`
2. Restore the backup: `cp projects/.arcreel.db.bak projects/.arcreel.db`
3. Remove `POSTGRES_PASSWORD` from `.env` and start without the PostgreSQL configuration in `docker-compose.yml`
