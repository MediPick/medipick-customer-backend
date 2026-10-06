# MediPick - Customer Backend

This is the FastAPI backend application for the MediPick customer-facing platform.

## Prerequisites

- Python 3.10+
- PostgreSQL or SQLite (depending on your configuration)

## Getting Started

1. **Set up Virtual Environment:**
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\Activate.ps1
   # On macOS/Linux:
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment:**
   Copy `.env.example` to `.env` and configure your database URI, Stripe secret keys, etc.
   ```bash
   cp .env.example .env
   ```

4. **Initialize & Seed Database:**
   ```bash
   python seed.py
   ```

5. **Start the server:**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
   The API documentation (Swagger) will be available at `http://127.0.0.1:8000/docs`.

## Project Structure
- `/app/api` - FastAPI routers and endpoint definitions
- `/app/schemas` - Pydantic models for validation
- `/app/models` - SQLAlchemy database models
- `/app/services` - Business logic and core functionality
- `/alembic` - Database migration scripts
