# FinVest Pro — Backend API

FastAPI backend for FinVest Pro AI investment platform.

## Quick Start

```bash
# 1. Clone and enter directory
cd backend

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate     # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment
cp .env.example .env
# Fill in .env with your actual keys

# 5. Add Firebase service account
# Download from Firebase Console → Project Settings → Service Accounts
# Save as: firebase/serviceAccountKey.json

# 6. Run development server
uvicorn main:app --reload --port 8000

# 7. Open API docs (debug mode only)
# http://localhost:8000/docs
```

## Production Deployment

```bash
# Railway / Render / DigitalOcean
uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2

# Environment variables to set in production:
# DEBUG=False
# FRONTEND_URL=https://your-frontend.com
# BACKEND_URL=https://your-api.com
# CASHFREE_BASE_URL=https://api.cashfree.com/pg   (NOT sandbox)
# All Firebase + Cashfree keys
```

## API Endpoints

| Method | Path | Auth | Plan |
|--------|------|------|------|
| POST | /api/v1/auth/sync | No | - |
| GET | /api/v1/user/profile | Yes | Any |
| GET | /api/v1/user/dashboard-stats | Yes | Any |
| GET | /api/v1/user/goals | Yes | Any |
| POST | /api/v1/engines/risk-profile | Yes | Free |
| GET | /api/v1/engines/news | Yes | Free |
| POST | /api/v1/engines/goal-planner | Yes | Basic+ |
| POST | /api/v1/engines/retirement | Yes | Basic+ |
| POST | /api/v1/engines/stock-analysis | Yes | Pro+ |
| POST | /api/v1/engines/portfolio | Yes | Pro+ |
| GET | /api/v1/engines/global-events | Yes | Pro+ |
| POST | /api/v1/payment/create-order | Yes | Any |
| POST | /api/v1/payment/verify | Yes | Any |
| POST | /api/v1/payment/webhook | No* | - |
| GET | /api/v1/admin/stats | Yes | Admin |

*Webhook verified by Cashfree signature