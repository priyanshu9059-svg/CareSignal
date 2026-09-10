# Deployment

## Public Render deployment

The root `render.yaml` deploys the complete application as one public Docker service with managed PostgreSQL. `Dockerfile.render` builds the Next.js interface as static files, copies them beside FastAPI, and `render-start.sh` exposes one Uvicorn process on Render's public port. FastAPI serves `/`, frontend assets, and every `/api` route from the same origin.

Push the project to a GitHub repository. In Render choose **New → Blueprint**, connect that repository, keep `render.yaml` as the blueprint path, review the resources and approve deployment. The service name may receive a suffix if it is unavailable. Render supplies the public URL after deployment. The blueprint uses the currently documented `free` plan names; review the dashboard before approval because provider pricing and availability can change.

## Docker / PostgreSQL

Install Docker with Compose. Copy `.env.example` to `.env`, set long random `JWT_SECRET` and `POSTGRES_PASSWORD`, then `docker compose up --build`. Use a URL-safe database password or URL-encode it in a separately configured DATABASE_URL. The PostgreSQL health check gates backend startup; the backend runs migration 0001, then seeds fictional data if DEMO_ENABLED=true. The frontend uses an internal backend URL baked into its rewrite configuration. Visit localhost:3000; API docs are localhost:8000/docs.

The compose services expose only loopback ports. Put an HTTPS reverse proxy in front for a remote demonstration. Set APP_ORIGIN to the exact HTTPS origin and COOKIE_SECURE=true. Do not publish the demo with real data. PostgreSQL and Redis persist in named volumes; normal shutdown with `docker compose down` retains them.

Docker was not present in the development environment; the local SQLite path is available for execution and testing. Validate the compose deployment on a Docker-equipped machine before the presentation. PostgreSQL schema uses the same SQLAlchemy mappings, including foreign keys and JSON columns.

## Non-Docker

Follow README.md. A local PostgreSQL instance can replace SQLite by setting DATABASE_URL before running migration and seed. Start uvicorn from backend and Next.js from frontend. `npm run build` followed by `npm start` runs the production frontend. On Windows background launches should use hidden windows with logs redirected to a project-local directory.

## Model setup

Train once with `python ai/train.py`; artifacts are small JSON files in ai/models. Missing artifacts activate an explicitly identified rule fallback. Model retraining overwrites only synthetic CSV and model artifacts, not case records. Production mode does not install external models or configure providers automatically.

## Operations

Check `/health`, logs, database connectivity, and `/docs`. AI inference is synchronous and CPU-only. Single-process request limiting is suitable for the local prototype; implement shared limits and worker queues before scaling. No destructive reset command is part of startup. Use a new database URL to prepare a clean demonstration. Never run test suites against a real deployment.
