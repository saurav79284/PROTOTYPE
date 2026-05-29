"""Transaction engine for FundFlow Intelligence — loads from CSV dataset."""
import csv
import json
import random
import uuid
import os
from datetime import datetime, timedelta
from backend.models import Transaction, TransactionChannel

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# ─── Load CSV Dataset ───
def _load_accounts():
    path = os.path.join(DATA_DIR, "accounts.csv")
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _load_transactions():
    path = os.path.join(DATA_DIR, "transactions.csv")
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _load_fraud_rings():
    path = os.path.join(DATA_DIR, "fraud_rings.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

ACCOUNTS = _load_accounts()
ALL_TRANSACTIONS = _load_transactions()
FRAUD_RINGS = _load_fraud_rings()

# Build lookup maps
ACCOUNT_MAP = {a["account_id"]: a for a in ACCOUNTS}
FRAUD_TXNS = [t for t in ALL_TRANSACTIONS if t["pattern_type"] != "normal"]
NORMAL_TXNS = [t for t in ALL_TRANSACTIONS if t["pattern_type"] == "normal"]

# Legacy compatibility — expose for graph_engine.py
ACCOUNT_HOLDERS = [(a["holder_name"], a["account_id"], a["bank"]) for a in ACCOUNTS]

# Circular flow rings — extract from fraud_rings.json (use account indices)
CIRCULAR_FLOW_RINGS = []
for ring in FRAUD_RINGS:
    if ring["type"] == "circular_flow":
        CIRCULAR_FLOW_RINGS.append(ring["members"])

CITIES = list(set(a["city"] for a in ACCOUNTS))

print(f"[DataLoader] Loaded {len(ACCOUNTS)} accounts, {len(ALL_TRANSACTIONS)} transactions "
      f"({len(FRAUD_TXNS)} suspicious, {len(NORMAL_TXNS)} normal), "
      f"{len(CIRCULAR_FLOW_RINGS)} circular flow rings")

# Initialize ML model stats from loaded data
from backend.ml_scoring import initialize_stats
initialize_stats(ALL_TRANSACTIONS, ACCOUNTS)



def _csv_to_transaction(row):
    """Convert a CSV row dict to a Transaction model."""
    channel_str = row["channel"]
    try:
        channel = TransactionChannel(channel_str)
    except ValueError:
        channel = TransactionChannel.IMPS

    try:
        ts = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
    except (ValueError, KeyError):
        ts = datetime.now() - timedelta(seconds=random.randint(0, 3600))

    return Transaction(
        txn_id=row.get("txn_id", f"TXN{uuid.uuid4().hex[:12].upper()}"),
        timestamp=ts,
        sender_account=row["sender_account"],
        sender_name=row["sender_name"],
        receiver_account=row["receiver_account"],
        receiver_name=row["receiver_name"],
        amount=float(row["amount"]),
        channel=channel,
        sender_bank=row.get("sender_bank", "PSB National Bank"),
        receiver_bank=row.get("receiver_bank", "PSB National Bank"),
        location=row.get("location"),
        device_id=row.get("device_id"),
        ip_address=row.get("ip_address"),
    )


def generate_txn_id():
    return f"TXN{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:8].upper()}"


def generate_normal_transaction(timestamp=None):
    """Pick a random normal transaction from dataset and re-timestamp it."""
    row = random.choice(NORMAL_TXNS).copy()
    row["txn_id"] = generate_txn_id()
    if timestamp:
        row["timestamp"] = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    else:
        row["timestamp"] = (datetime.now() - timedelta(seconds=random.randint(0, 3600))).strftime("%Y-%m-%d %H:%M:%S")
    return _csv_to_transaction(row)


def generate_suspicious_transaction(pattern_type="circular", ring_idx=0, step=0, timestamp=None):
    """Pick a matching suspicious transaction from dataset."""
    pattern_map = {
        "circular": "circular_flow",
        "structuring": "structuring",
        "layering": "layering",
        "dormant": "dormant_reactivation",
    }
    target_pattern = pattern_map.get(pattern_type, pattern_type)
    matching = [t for t in FRAUD_TXNS if t["pattern_type"] == target_pattern]
    if not matching:
        matching = FRAUD_TXNS  # fallback

    row = random.choice(matching).copy()
    row["txn_id"] = generate_txn_id()
    if timestamp:
        row["timestamp"] = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    else:
        row["timestamp"] = (datetime.now() - timedelta(seconds=random.randint(0, 1800))).strftime("%Y-%m-%d %H:%M:%S")
    return _csv_to_transaction(row)


def generate_transaction_batch(count=20, suspicious_ratio=0.15):
    """Generate a batch of transactions with some suspicious ones mixed in."""
    transactions = []
    suspicious_count = max(1, int(count * suspicious_ratio))
    normal_count = count - suspicious_count

    for _ in range(normal_count):
        transactions.append(("normal", generate_normal_transaction()))

    patterns = ["circular", "structuring", "layering", "dormant"]
    for i in range(suspicious_count):
        pattern = random.choice(patterns)
        transactions.append((pattern, generate_suspicious_transaction(pattern)))

    random.shuffle(transactions)
    return transactions


def get_dataset_stats():
    """Return statistics about the loaded dataset."""
    pattern_counts = {}
    total_amount = 0
    for t in ALL_TRANSACTIONS:
        p = t["pattern_type"]
        pattern_counts[p] = pattern_counts.get(p, 0) + 1
        total_amount += float(t.get("amount", 0))

    return {
        "total_accounts": len(ACCOUNTS),
        "total_transactions": len(ALL_TRANSACTIONS),
        "fraud_transactions": len(FRAUD_TXNS),
        "normal_transactions": len(NORMAL_TXNS),
        "fraud_rate": round(len(FRAUD_TXNS) / len(ALL_TRANSACTIONS) * 100, 1),
        "circular_flow_rings": len(CIRCULAR_FLOW_RINGS),
        "pattern_distribution": pattern_counts,
        "banks": list(set(a["bank"] for a in ACCOUNTS)),
        "cities": CITIES,
        "total_amount": round(total_amount, 2),
    }
