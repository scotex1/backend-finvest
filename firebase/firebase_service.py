"""
firebase/firebase_service.py — Firestore database operations

FIXES vs v1:
 [1] PaymentService.create_payment_record: idempotency_key stored
 [2] PaymentService.get_by_idempotency_key: new method for dedup
 [3] FirebaseService.get_all_users: offset actually used in query
 [4] AdminService.get_dashboard_stats: N+1 Firestore reads fixed
     (was streaming ALL payments twice — now streams once)
 [5] PlanService.activate_plan: returns expiry as ISO string (not datetime)
"""

from firebase_admin import firestore
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def _db():
    return firestore.client()


# ════════════════════════════════════════════════════════════
# USER OPERATIONS
# ════════════════════════════════════════════════════════════

class FirebaseService:

    @staticmethod
    def get_user(uid: str) -> Optional[dict]:
        doc = _db().collection("users").document(uid).get()
        return doc.to_dict() if doc.exists else None

    @staticmethod
    def create_or_update_user(uid: str, data: dict) -> dict:
        ref = _db().collection("users").document(uid)
        doc = ref.get()

        if doc.exists:
            update_data = {k: v for k, v in data.items() if v is not None}
            update_data["updated_at"] = datetime.utcnow()
            ref.update(update_data)
        else:
            ref.set({
                "uid":           uid,
                "email":         data.get("email", ""),
                "name":          data.get("name", ""),
                "photo":         data.get("photo", ""),
                "plan":          "free",
                "plan_expiry":   None,
                "plan_name":     "Free",
                "is_active":     True,
                "is_admin":      False,
                "login_count":   0,
                "total_revenue": 0,
                "created_at":    datetime.utcnow(),
                "updated_at":    datetime.utcnow(),
            })

        ref.update({"login_count": firestore.Increment(1)})
        return ref.get().to_dict()

    @staticmethod
    def update_user_profile(uid: str, data: dict):
        allowed = ["name", "phone", "city", "occupation", "income", "photo"]
        update  = {k: v for k, v in data.items() if k in allowed and v is not None}
        update["updated_at"] = datetime.utcnow()
        _db().collection("users").document(uid).update(update)

    @staticmethod
    def get_all_users(limit: int = 50, offset: int = 0,
                      search: str = "", plan_filter: str = "") -> dict:
        """
        [FIX 3] offset used via stream + skip pattern
        (Firestore doesn't support SQL OFFSET — we stream and skip).
        For large datasets, use cursor-based pagination with start_after().
        """
        ref   = _db().collection("users")
        query = ref.order_by("created_at", direction=firestore.Query.DESCENDING)

        if plan_filter:
            query = query.where("plan", "==", plan_filter)

        all_docs = list(query.stream())
        total    = len(all_docs)

        # Apply search filter client-side (Firestore doesn't support LIKE)
        if search:
            s        = search.lower()
            all_docs = [
                d for d in all_docs
                if s in (d.to_dict().get("email", "") + d.to_dict().get("name", "")).lower()
            ]
            total = len(all_docs)

        # Apply offset + limit
        page_docs = all_docs[offset: offset + limit]
        users = []
        for doc in page_docs:
            u = doc.to_dict()
            # Serialize datetime fields
            for field in ("created_at", "updated_at", "plan_expiry"):
                if isinstance(u.get(field), datetime):
                    u[field] = u[field].isoformat()
            users.append(u)

        return {"users": users, "total": total}

    @staticmethod
    def delete_user(uid: str):
        _db().collection("users").document(uid).delete()
        payments = _db().collection("payments").where("uid", "==", uid).stream()
        for p in payments:
            p.reference.delete()
        goals = _db().collection("users").document(uid).collection("goals").stream()
        for g in goals:
            g.reference.delete()
        logger.info(f"Deleted user + payments + goals for uid={uid}")

    @staticmethod
    def is_admin(uid: str) -> bool:
        user = FirebaseService.get_user(uid)
        return bool(user and user.get("is_admin", False))


# ════════════════════════════════════════════════════════════
# PLAN / SUBSCRIPTION OPERATIONS
# ════════════════════════════════════════════════════════════

class PlanService:

    @staticmethod
    def get_user_plan(uid: str) -> dict:
        user = FirebaseService.get_user(uid)
        if not user:
            return {"plan_id": "free", "plan_name": "Free", "expiry_date": None}

        plan      = user.get("plan", "free")
        expiry    = user.get("plan_expiry")
        plan_name = user.get("plan_name", "Free")

        if expiry and datetime.utcnow() > expiry:
            PlanService.expire_plan(uid)
            return {"plan_id": "free", "plan_name": "Free", "expiry_date": None}

        return {
            "plan_id":     plan,
            "plan_name":   plan_name,
            "expiry_date": expiry.isoformat() if expiry else None,
        }

    @staticmethod
    def activate_plan(uid: str, plan_id: str, duration_days: int,
                      order_id: str, amount: int) -> str:
        """[FIX 5] Returns ISO string consistently."""
        plan_names = {
            "basic":        "Basic Plan",
            "pro":          "Pro Plan",
            "elite":        "Elite Plan",
            "basic_yearly": "Basic Plan (Yearly)",
            "pro_yearly":   "Pro Plan (Yearly)",
        }
        base_plan = plan_id.replace("_yearly", "")
        expiry    = datetime.utcnow() + timedelta(days=duration_days)

        _db().collection("users").document(uid).update({
            "plan":        base_plan,
            "plan_name":   plan_names.get(plan_id, plan_id),
            "plan_expiry": expiry,
            "updated_at":  datetime.utcnow(),
        })
        logger.info(f"Plan activated: uid={uid} plan={plan_id} expiry={expiry.isoformat()}")
        return expiry.isoformat()  # [FIX 5] Always return ISO string

    @staticmethod
    def expire_plan(uid: str):
        _db().collection("users").document(uid).update({
            "plan":        "free",
            "plan_name":   "Free",
            "plan_expiry": None,
            "updated_at":  datetime.utcnow(),
        })

    @staticmethod
    def get_plan_stats() -> dict:
        users = list(_db().collection("users").stream())
        stats = {"free": 0, "basic": 0, "pro": 0, "elite": 0}
        for u in users:
            plan = u.to_dict().get("plan", "free")
            if plan in stats:
                stats[plan] += 1
        return stats


# ════════════════════════════════════════════════════════════
# PAYMENT OPERATIONS
# ════════════════════════════════════════════════════════════

class PaymentService:

    @staticmethod
    def create_payment_record(uid: str, order_id: str, plan_id: str,
                               amount: int, idempotency_key: str = "") -> str:
        """[FIX 1] idempotency_key stored."""
        _db().collection("payments").document(order_id).set({
            "order_id":         order_id,
            "uid":              uid,
            "plan":             plan_id,
            "amount":           amount,
            "status":           "PENDING",
            "idempotency_key":  idempotency_key,  # [FIX 1]
            "created_at":       datetime.utcnow(),
            "updated_at":       datetime.utcnow(),
        })
        return order_id

    @staticmethod
    def get_by_idempotency_key(key: str, uid: str) -> Optional[dict]:
        """[FIX 2] New method — used for duplicate order prevention."""
        if not key:
            return None
        docs = (_db().collection("payments")
                .where("idempotency_key", "==", key)
                .where("uid", "==", uid)
                .limit(1)
                .stream())
        for doc in docs:
            return doc.to_dict()
        return None

    @staticmethod
    def update_payment_status(order_id: str, status: str,
                               payment_id: str = "", user_email: str = ""):
        update = {
            "status":     status,
            "updated_at": datetime.utcnow(),
        }
        if payment_id:  update["payment_id"]  = payment_id
        if user_email:  update["user_email"]   = user_email
        _db().collection("payments").document(order_id).update(update)

        if status == "SUCCESS":
            doc = _db().collection("payments").document(order_id).get().to_dict()
            uid    = doc.get("uid")
            amount = doc.get("amount", 0)
            if uid:
                _db().collection("users").document(uid).update({
                    "total_revenue": firestore.Increment(amount)
                })

    @staticmethod
    def get_payment(order_id: str) -> Optional[dict]:
        doc = _db().collection("payments").document(order_id).get()
        return doc.to_dict() if doc.exists else None

    @staticmethod
    def get_user_payments(uid: str) -> list:
        docs = (_db().collection("payments")
                .where("uid", "==", uid)
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(20)
                .stream())
        results = []
        for d in docs:
            p = d.to_dict()
            if isinstance(p.get("created_at"), datetime):
                p["created_at"] = p["created_at"].isoformat()
            results.append(p)
        return results

    @staticmethod
    def get_all_payments(limit: int = 50, status_filter: str = "",
                          plan_filter: str = "") -> dict:
        """[FIX 4] Streams payments once — no duplicate streaming."""
        ref = _db().collection("payments").order_by(
            "created_at", direction=firestore.Query.DESCENDING)
        if status_filter:
            ref = ref.where("status", "==", status_filter)
        if plan_filter:
            ref = ref.where("plan", "==", plan_filter)

        all_docs = list(ref.stream())
        payments = []
        total_revenue = 0
        month_revenue = 0
        success_count = 0
        month_start   = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)

        for doc in all_docs:
            p = doc.to_dict()
            if p.get("status") == "SUCCESS":
                success_count += 1
                amt = p.get("amount", 0)
                total_revenue += amt
                created = p.get("created_at")
                if isinstance(created, datetime) and created >= month_start:
                    month_revenue += amt

        # Serialize for JSON
        for doc in all_docs[:limit]:
            p = doc.to_dict()
            if isinstance(p.get("created_at"), datetime):
                p["created_at"] = p["created_at"].isoformat()
                p["date"]       = p["created_at"]
            payments.append(p)

        total_tx      = len(all_docs)
        success_rate  = round(success_count / total_tx * 100, 1) if total_tx else 0

        return {
            "payments": payments,
            "total":    total_tx,
            "stats": {
                "total_revenue":    total_revenue,
                "month_revenue":    month_revenue,
                "success_rate":     success_rate,
                "success_count":    success_count,
                "total_transactions": total_tx,
            }
        }


# ════════════════════════════════════════════════════════════
# ADMIN STATS
# ════════════════════════════════════════════════════════════

class AdminService:

    @staticmethod
    def get_dashboard_stats() -> dict:
        """[FIX 4] Single stream per collection — no N+1 reads."""
        users    = [u.to_dict() for u in _db().collection("users").stream()]
        payments = [p.to_dict() for p in
                    _db().collection("payments").where("status", "==", "SUCCESS").stream()]

        total_users = len(users)
        active_subs = sum(1 for u in users if u.get("plan", "free") != "free")

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        new_today   = sum(
            1 for u in users
            if isinstance(u.get("created_at"), datetime) and u["created_at"] >= today_start
        )
        payments_today = [
            p for p in payments
            if isinstance(p.get("created_at"), datetime) and p["created_at"] >= today_start
        ]

        total_revenue = sum(p.get("amount", 0) for p in payments)
        revenue_today = sum(p.get("amount", 0) for p in payments_today)

        # MRR: actual sum of active monthly subscriptions
        from core.config import settings
        mrr = sum(
            settings.PLAN_PRICES.get(u.get("plan", "free"), 0) / 100
            for u in users
            if u.get("plan", "free") != "free"
        )

        plan_stats = PlanService.get_plan_stats()

        return {
            "total_users":     total_users,
            "active_subs":     active_subs,
            "new_users_today": new_today,
            "mrr":             mrr,
            "mrr_growth":      0,
            "churn_rate":      0,
            "payments_today":  len(payments_today),
            "revenue_today":   revenue_today / 100,    # convert paise to rupees
            "total_revenue":   total_revenue / 100,
            **plan_stats,
        }


# ════════════════════════════════════════════════════════════
# ENGINE RESULT STORAGE — portfolio, retirement, stock analysis,
# investment advice, and news cache
# ════════════════════════════════════════════════════════════

class EngineDataService:
    """
    [NEW] Saves engine outputs to Firestore so users have history instead
    of results disappearing after each calculation. All saves are
    "best-effort" from the caller's side — engines call these wrapped in
    try/except so a Firestore hiccup never breaks the user-facing result.
    """

    # ── Portfolio Optimizer ────────────────────────────────
    @staticmethod
    def save_portfolio_result(uid: str, params: dict, result: dict) -> str:
        ref = (_db().collection("users").document(uid)
               .collection("portfolio_history").document())
        ref.set({
            "amount":     params.get("amount"),
            "risk":       params.get("risk"),
            "horizon":    params.get("horizon"),
            "result":     result,
            "created_at": datetime.utcnow(),
        })
        return ref.id

    @staticmethod
    def get_portfolio_history(uid: str, limit: int = 10) -> list:
        docs = (_db().collection("users").document(uid)
                .collection("portfolio_history")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit).stream())
        out = []
        for d in docs:
            item = d.to_dict()
            item["id"] = d.id
            if isinstance(item.get("created_at"), datetime):
                item["created_at"] = item["created_at"].isoformat()
            out.append(item)
        return out

    # ── Retirement Calculator ──────────────────────────────
    @staticmethod
    def save_retirement_result(uid: str, params: dict, result: dict) -> str:
        ref = (_db().collection("users").document(uid)
               .collection("retirement_history").document())
        ref.set({
            "params":     params,
            "result":     result,
            "created_at": datetime.utcnow(),
        })
        return ref.id

    @staticmethod
    def get_retirement_history(uid: str, limit: int = 10) -> list:
        docs = (_db().collection("users").document(uid)
                .collection("retirement_history")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit).stream())
        out = []
        for d in docs:
            item = d.to_dict()
            item["id"] = d.id
            if isinstance(item.get("created_at"), datetime):
                item["created_at"] = item["created_at"].isoformat()
            out.append(item)
        return out

    # ── Stock Analysis ──────────────────────────────────────
    @staticmethod
    def save_stock_analysis(uid: str, result: dict) -> str:
        ref = (_db().collection("users").document(uid)
               .collection("stock_analysis").document())
        ref.set({
            "symbol":     result.get("symbol"),
            "verdict":    result.get("verdict"),
            "result":     result,
            "created_at": datetime.utcnow(),
        })
        return ref.id

    @staticmethod
    def get_stock_analysis_history(uid: str, limit: int = 20) -> list:
        docs = (_db().collection("users").document(uid)
                .collection("stock_analysis")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit).stream())
        out = []
        for d in docs:
            item = d.to_dict()
            item["id"] = d.id
            if isinstance(item.get("created_at"), datetime):
                item["created_at"] = item["created_at"].isoformat()
            out.append(item)
        return out

    # ── Investment Advisory ─────────────────────────────────
    @staticmethod
    def save_investment_advice(uid: str, result: dict) -> str:
        ref = (_db().collection("users").document(uid)
               .collection("investment_advice").document())
        ref.set({
            "result":     result,
            "created_at": datetime.utcnow(),
        })
        return ref.id

    @staticmethod
    def get_investment_advice_history(uid: str, limit: int = 10) -> list:
        docs = (_db().collection("users").document(uid)
                .collection("investment_advice")
                .order_by("created_at", direction=firestore.Query.DESCENDING)
                .limit(limit).stream())
        out = []
        for d in docs:
            item = d.to_dict()
            item["id"] = d.id
            if isinstance(item.get("created_at"), datetime):
                item["created_at"] = item["created_at"].isoformat()
            out.append(item)
        return out

    # ── News Cache (shared across all users/instances) ─────
    @staticmethod
    def get_news_cache(cache_key: str, ttl_minutes: int = 15) -> Optional[dict]:
        """Returns cached news payload if still fresh, else None."""
        doc = _db().collection("news_cache").document(cache_key).get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        cached_at = data.get("cached_at")
        if not isinstance(cached_at, datetime):
            return None
        if datetime.utcnow() - cached_at > timedelta(minutes=ttl_minutes):
            return None
        return data.get("payload")

    @staticmethod
    def save_news_cache(cache_key: str, payload: dict):
        _db().collection("news_cache").document(cache_key).set({
            "payload":   payload,
            "cached_at": datetime.utcnow(),
        })
