"""FundFlow Intelligence - FastAPI Backend Server.

Features:
- WebSocket real-time transaction streaming
- In-memory cache layer (simulating Redis)
- Audit trail for HITL workflow
- Mule account detection endpoint
"""
import uuid
import random
import asyncio
import os
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.models import (
    Alert, AlertStatus, DashboardStats, Transaction,
    RiskTier, NetworkGraph
)
from backend.transaction_engine import generate_transaction_batch, generate_normal_transaction, get_dataset_stats
from backend.ml_scoring import score_transaction, generate_shap_explanations, get_fatf_typology
from backend.graph_engine import build_network_graph, get_account_subgraph, detect_circular_flows, detect_mule_accounts
from backend.str_generator import generate_str_report
from backend.cache import cache

# Environment configuration
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",") if os.getenv("ALLOWED_ORIGINS", "*") != "*" else ["*"]

app = FastAPI(
    title="FundFlow Intelligence API",
    description="Real-time Fund Tracking & Fraud Detection System",
    version="2.0.0",
    debug=DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory stores (for hackathon prototype)
alerts_store: dict[str, Alert] = {}
str_store: dict[str, dict] = {}
transaction_log: list[dict] = []
audit_log: list[dict] = []  # Audit trail for HITL workflow

# WebSocket connections
ws_connections: list[WebSocket] = []


def _add_audit_entry(action, entity_id, details="", officer="System"):
    """Add an entry to the audit trail."""
    audit_log.append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "entity_id": entity_id,
        "details": details,
        "officer": officer,
    })


# Pre-populate some alerts on startup
def _seed_data():
    batch = generate_transaction_batch(count=30, suspicious_ratio=0.3)
    for pattern_type, txn in batch:
        ml_score = score_transaction(txn, pattern_type)
        if ml_score.composite_score >= 45:
            alert_id = f"ALT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
            shap = generate_shap_explanations(txn, ml_score, pattern_type)
            graph_patterns = detect_circular_flows() if pattern_type in ("circular", "circular_flow") else []
            fatf = get_fatf_typology(pattern_type)
            statuses = [AlertStatus.PENDING, AlertStatus.PENDING, AlertStatus.PENDING,
                        AlertStatus.INVESTIGATING, AlertStatus.CONFIRMED_FRAUD]
            alert = Alert(
                alert_id=alert_id, transaction=txn, ml_score=ml_score,
                shap_explanations=shap, graph_patterns=graph_patterns,
                status=random.choice(statuses), created_at=datetime.now(),
                fatf_typology=fatf,
            )
            alerts_store[alert_id] = alert
            _add_audit_entry("ALERT_GENERATED", alert_id, f"Score: {ml_score.composite_score}, Pattern: {pattern_type}")

        transaction_log.append({
            "txn": txn.model_dump(mode="json"),
            "pattern": pattern_type,
            "score": ml_score.model_dump(mode="json"),
        })

_seed_data()


# ─── WebSocket: Real-Time Transaction Streaming ───
@app.websocket("/ws/transactions")
async def transaction_stream(websocket: WebSocket):
    """Stream transactions to connected clients in real-time.
    Sends one transaction every 2 seconds with ML scoring.
    """
    await websocket.accept()
    ws_connections.append(websocket)
    try:
        while True:
            batch = generate_transaction_batch(count=1, suspicious_ratio=0.15)
            for pattern_type, txn in batch:
                score = score_transaction(txn, pattern_type)
                shap = generate_shap_explanations(txn, score, pattern_type)

                payload = {
                    "type": "transaction",
                    "transaction": txn.model_dump(mode="json"),
                    "ml_score": score.model_dump(mode="json"),
                    "pattern_type": pattern_type,
                    "is_flagged": score.composite_score >= 60,
                }

                # Auto-create alert for high-scoring transactions
                if score.composite_score >= 60:
                    alert_id = f"ALT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
                    graph_patterns = detect_circular_flows() if pattern_type in ("circular", "circular_flow") else []
                    fatf = get_fatf_typology(pattern_type)
                    alert = Alert(
                        alert_id=alert_id, transaction=txn, ml_score=score,
                        shap_explanations=shap, graph_patterns=graph_patterns,
                        status=AlertStatus.PENDING, created_at=datetime.now(),
                        fatf_typology=fatf,
                    )
                    alerts_store[alert_id] = alert
                    cache.invalidate("dashboard_stats")
                    _add_audit_entry("ALERT_GENERATED", alert_id,
                                     f"Score: {score.composite_score}, Pattern: {pattern_type}")

                    # Send alert notification
                    payload["alert"] = {
                        "alert_id": alert_id,
                        "tier": score.tier.value,
                        "score": score.composite_score,
                        "sender": txn.sender_name,
                        "amount": txn.amount,
                    }

                transaction_log.append({
                    "txn": txn.model_dump(mode="json"),
                    "pattern": pattern_type,
                    "score": score.model_dump(mode="json"),
                })

                await websocket.send_json(payload)

            await asyncio.sleep(2)
    except WebSocketDisconnect:
        ws_connections.remove(websocket)
    except Exception:
        if websocket in ws_connections:
            ws_connections.remove(websocket)


# ─── Dashboard Stats ───
@app.get("/api/stats", response_model=DashboardStats)
def get_dashboard_stats():
    # Check cache first
    cached = cache.get("dashboard_stats")
    if cached:
        return cached

    ds = get_dataset_stats()
    total_txns = ds["total_transactions"] + len(transaction_log)
    total_amount = sum(t["txn"]["amount"] for t in transaction_log) + ds.get("total_amount", 1e8)
    critical = sum(1 for a in alerts_store.values() if a.ml_score.tier == RiskTier.CRITICAL)
    scores = [a.ml_score.composite_score for a in alerts_store.values()]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0

    channels = {}
    for t in transaction_log:
        ch = t["txn"]["channel"]
        channels[ch] = channels.get(ch, 0) + 1

    # Deterministic false positive rate from actual data
    fp_count = sum(1 for a in alerts_store.values() if a.status == AlertStatus.FALSE_POSITIVE)
    total_alerts = len(alerts_store)
    fp_rate = round((fp_count / total_alerts * 100) if total_alerts > 0 else 3.2, 1)

    # Deterministic latency from actual scores
    latencies = [a.ml_score.latency_ms for a in alerts_store.values()]
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else 35.0

    result = DashboardStats(
        total_transactions_today=total_txns,
        total_amount_today=round(total_amount, 2),
        alerts_generated=total_alerts,
        critical_alerts=critical,
        avg_risk_score=avg_score,
        circular_flows_detected=ds["circular_flow_rings"],
        str_reports_filed=len(str_store),
        false_positive_rate=fp_rate,
        avg_latency_ms=avg_latency,
        channels_active=channels,
    )

    cache.set("dashboard_stats", result, ttl=30)
    return result


@app.get("/api/dataset")
def get_dataset_info():
    import json as _json
    stats = get_dataset_stats()
    # Include model training metrics if available
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "feature_config.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = _json.load(f)
        if "metrics" in config:
            stats["model_metrics"] = config["metrics"]
    return stats


# ─── Live Transaction Feed ───
@app.get("/api/transactions/live")
def get_live_transactions(count: int = Query(default=10, ge=1, le=50)):
    batch = generate_transaction_batch(count=count, suspicious_ratio=0.15)
    results = []
    for pattern_type, txn in batch:
        ml_score = score_transaction(txn, pattern_type)
        results.append({
            "transaction": txn.model_dump(mode="json"),
            "ml_score": ml_score.model_dump(mode="json"),
            "pattern_type": pattern_type,
            "is_flagged": ml_score.composite_score >= 60,
        })
        transaction_log.append({
            "txn": txn.model_dump(mode="json"),
            "pattern": pattern_type,
            "score": ml_score.model_dump(mode="json"),
        })
    return {"transactions": results, "timestamp": datetime.now().isoformat()}


async def _broadcast_to_websockets(payload: dict):
    """Broadcast a message to all connected WebSocket clients."""
    dead = []
    for ws in ws_connections:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_connections.remove(ws)


from pydantic import BaseModel as _PydanticBase

class NewTransactionRequest(_PydanticBase):
    sender_name: str = "Demo User"
    sender_account: str = "DEMO00001234"
    receiver_name: str = "Demo Receiver"
    receiver_account: str = "DEMO00005678"
    amount: float = 50000
    channel: str = "UPI"
    sender_bank: str = "PSB National Bank"
    receiver_bank: str = "PSB National Bank"
    location: Optional[str] = "Mumbai"


@app.post("/api/transactions")
async def submit_transaction(req: NewTransactionRequest):
    """Submit a custom transaction through the full ML pipeline.
    
    The transaction is:
    1. Scored by XGBoost + Isolation Forest + LSTM + GNN ensemble
    2. SHAP explanations generated
    3. Broadcast to all WebSocket clients (appears in live feed)
    4. Auto-creates alert if score >= 60
    """
    import os
    # Build a Transaction object
    txn_id = f"TXN-DEMO-{uuid.uuid4().hex[:8].upper()}"
    channel_map = {"UPI": "UPI", "IMPS": "IMPS", "NEFT": "NEFT", "RTGS": "RTGS", "SWIFT": "SWIFT", "CBS": "CBS"}
    channel = channel_map.get(req.channel.upper(), "UPI")

    txn = Transaction(
        txn_id=txn_id,
        timestamp=datetime.now(),
        sender_account=req.sender_account,
        sender_name=req.sender_name,
        receiver_account=req.receiver_account,
        receiver_name=req.receiver_name,
        amount=req.amount,
        channel=channel,
        sender_bank=req.sender_bank,
        receiver_bank=req.receiver_bank,
        location=req.location,
    )

    # Score through ML pipeline
    pattern_type = "normal"  # User-submitted transactions are treated as unknown
    ml_score = score_transaction(txn, pattern_type)
    shap = generate_shap_explanations(txn, ml_score, pattern_type)

    # Build WebSocket payload
    payload = {
        "type": "transaction",
        "transaction": txn.model_dump(mode="json"),
        "ml_score": ml_score.model_dump(mode="json"),
        "pattern_type": "user_submitted",
        "is_flagged": ml_score.composite_score >= 60,
        "is_demo": True,
    }

    # Auto-create alert if high risk
    alert_data = None
    if ml_score.composite_score >= 60:
        alert_id = f"ALT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        graph_patterns = []
        fatf = get_fatf_typology(pattern_type)
        alert = Alert(
            alert_id=alert_id, transaction=txn, ml_score=ml_score,
            shap_explanations=shap, graph_patterns=graph_patterns,
            status=AlertStatus.PENDING, created_at=datetime.now(),
            fatf_typology=fatf,
        )
        alerts_store[alert_id] = alert
        cache.invalidate("dashboard_stats")
        _add_audit_entry("ALERT_GENERATED", alert_id,
                         f"User-submitted transaction. Score: {ml_score.composite_score}")
        alert_data = {
            "alert_id": alert_id,
            "tier": ml_score.tier.value,
            "score": ml_score.composite_score,
            "sender": txn.sender_name,
            "amount": txn.amount,
        }
        payload["alert"] = alert_data

    # Add to transaction log
    transaction_log.append({
        "txn": txn.model_dump(mode="json"),
        "pattern": "user_submitted",
        "score": ml_score.model_dump(mode="json"),
    })

    # Broadcast to all WebSocket clients
    await _broadcast_to_websockets(payload)

    return {
        "status": "scored",
        "txn_id": txn_id,
        "ml_score": ml_score.model_dump(mode="json"),
        "shap_top_features": [s.model_dump() for s in shap[:3]],
        "alert": alert_data,
        "ws_broadcast": len(ws_connections),
    }


# ─── Alerts ───
@app.get("/api/alerts")
def get_alerts(
    status: Optional[str] = None,
    tier: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    alerts = list(alerts_store.values())
    if status:
        alerts = [a for a in alerts if a.status.value == status]
    if tier:
        alerts = [a for a in alerts if a.ml_score.tier.value == tier]
    alerts.sort(key=lambda x: x.ml_score.composite_score, reverse=True)
    return {
        "alerts": [a.model_dump(mode="json") for a in alerts[:limit]],
        "total": len(alerts),
    }


@app.get("/api/alerts/{alert_id}")
def get_alert_detail(alert_id: str):
    if alert_id not in alerts_store:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alerts_store[alert_id].model_dump(mode="json")


@app.put("/api/alerts/{alert_id}/status")
def update_alert_status(alert_id: str, new_status: str, notes: Optional[str] = None):
    if alert_id not in alerts_store:
        raise HTTPException(status_code=404, detail="Alert not found")
    try:
        status = AlertStatus(new_status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")

    old_status = alerts_store[alert_id].status.value
    alerts_store[alert_id].status = status
    if notes:
        alerts_store[alert_id].notes = notes

    cache.invalidate("dashboard_stats")
    _add_audit_entry(
        "STATUS_CHANGE", alert_id,
        f"{old_status} → {new_status}" + (f" | Note: {notes}" if notes else ""),
        officer="Compliance Officer"
    )

    return {"status": "updated", "alert_id": alert_id, "new_status": new_status}


# ─── Graph Network ───
@app.get("/api/graph/network")
def get_network_graph():
    cached = cache.get("graph_network")
    if cached:
        return cached

    graph = build_network_graph(include_suspicious=True)
    result = graph.model_dump(mode="json")
    cache.set("graph_network", result, ttl=60)
    return result


@app.get("/api/graph/account/{account_id}")
def get_account_graph(account_id: str):
    graph = get_account_subgraph(account_id)
    return graph.model_dump(mode="json")


@app.get("/api/graph/mule-accounts")
def get_mule_accounts():
    """Detect potential mule accounts in the transaction network."""
    mules = detect_mule_accounts()
    return {"mule_accounts": mules, "total": len(mules)}


# ─── STR Generation ───
@app.post("/api/str/generate/{alert_id}")
def generate_str(alert_id: str):
    if alert_id not in alerts_store:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert = alerts_store[alert_id]
    report = generate_str_report(alert)
    str_store[report.str_id] = report.model_dump(mode="json")
    alerts_store[alert_id].status = AlertStatus.STR_FILED
    cache.invalidate("dashboard_stats")

    _add_audit_entry(
        "STR_GENERATED", report.str_id,
        f"For alert {alert_id}, Amount: ₹{alert.transaction.amount:,.2f}",
        officer="Compliance Officer"
    )

    return report.model_dump(mode="json")


@app.get("/api/str/list")
def list_str_reports():
    return {"reports": list(str_store.values()), "total": len(str_store)}


@app.get("/api/str/{str_id}")
def get_str_report(str_id: str):
    if str_id not in str_store:
        raise HTTPException(status_code=404, detail="STR not found")
    return str_store[str_id]


# ─── Audit Trail ───
@app.get("/api/audit")
def get_audit_log(limit: int = Query(default=50, ge=1, le=200)):
    """Get the audit trail — shows all system actions in chronological order."""
    return {"entries": audit_log[-limit:], "total": len(audit_log)}


@app.get("/api/audit/{entity_id}")
def get_audit_for_entity(entity_id: str):
    """Get audit entries for a specific alert or STR."""
    entries = [e for e in audit_log if e["entity_id"] == entity_id]
    return {"entries": entries, "total": len(entries)}


# ─── Cache Stats ───
@app.get("/api/cache/stats")
def get_cache_stats():
    """Return cache statistics."""
    return cache.stats()


# ─── Health Check (for deployment monitoring) ───
@app.get("/health")
def health_check():
    """Health check endpoint for deployment platforms."""
    return {
        "status": "healthy",
        "service": "FundFlow Intelligence API",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
    }


# ─── Serve Frontend ───
import os
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
