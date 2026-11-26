# Table & Tadka

**food-app**

A fictional food-ordering application based on the AI Smart Food Ordering & Restaurant Assistant case study. It includes a FastAPI API, a browser interface, SQLAlchemy persistence, a single OpenAI tool-calling assistant, document retrieval and confirmation-gated actions. No real payment or delivery takes place.

## Run locally

Requires Python 3.11 or 3.12. From this directory:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 or http://127.0.0.1:8000/docs. Local development defaults to a persistent SQLite database. For MySQL, create an empty database and user, then set `DATABASE_URL` in `.env`, for example `mysql+pymysql://food_user:password@127.0.0.1:3306/food_ai?charset=utf8mb4`. Tables are created at startup; schema migrations are not yet provided. Use a separate database for tests.

On an empty database, demo accounts `maya`, `arjun` and `admin` are created with password `demo1234`, along with a fictional menu and three sample orders. These credentials are for local demonstrations only. Do not expose this demo to untrusted networks or use its default accounts in production. Basic authentication requires HTTPS outside localhost. Browser credentials are held only in memory.

## Database migrations

Alembic migrations are in `migrations/`. For a new database, run `.venv/bin/alembic upgrade head` before starting the app; startup still creates missing tables for the quick local demo. For an existing database created by the app's automatic table setup, back it up and run `.venv/bin/alembic stamp head` once to mark the baseline as applied. Do not run `upgrade head` against an existing unversioned schema, because its tables already exist. Create future migrations with `.venv/bin/alembic revision --autogenerate -m "describe schema change"`, review the generated migration, then apply it with `.venv/bin/alembic upgrade head`.

## Assistant and documents

Set `OPENAI_API_KEY` in `.env` and restart the server to enable the assistant and OpenAI embeddings. The key stays server-side. Sign in as `admin` and upload the fictional files in `knowledge_base/` from Manage; documents are chunked and indexed in local ChromaDB. Without an API key the menu and ordering remain usable and chat reports that the assistant is unavailable. External API usage may incur charges.

The agent reads live business data through a fixed, server-configured local API URL. Ordering and cancellation are first stored as pending actions; only the confirmation button executes them. Confirmed order prices are rechecked in the order transaction. Pending actions, chat history and tool audit records are persisted in the relational database. Model output and uploaded documents are untrusted; the UI renders messages as text. Policy answers should cite indexed sources and cannot guarantee allergen safety.

`INTERNAL_API_BASE_URL` must match the server's own local address and port. The application uses an in-process request limit intended for a single local development process; use an external shared rate limiter, proper account management, HTTPS, database migrations, durable job processing and additional security review before deployment.

## Structure

The HTTP layer is in `app/main.py` and `app/routes_chat.py`; schemas and authentication are separate. `app/services.py` owns transactional order rules, while repositories and SQLAlchemy models handle persistence. `app/chat.py` owns agent orchestration and confirmation, and `app/rag.py` handles document extraction, embeddings and retrieval. The browser assets are in `frontend/`. Dependencies are injected at the HTTP boundary, and tools reuse the same business API as the frontend.

## Tests

```bash
.venv/bin/python -m pytest -q
```

Tests use a temporary SQLite database and mock AI action execution; a configured OpenAI key and separate MySQL database are needed for live AI and MySQL concurrency verification.
