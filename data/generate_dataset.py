"""
Synthetic Dataset Generator for FundFlow Intelligence.
Generates realistic Indian banking data with injected fraud patterns.
Target: 1,000 accounts · 50,000 transactions · ~5% fraud rate.
"""
import csv
import random
import uuid
import os
from datetime import datetime, timedelta

random.seed(42)  # Reproducible

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─── Indian Name Pools ───
FIRST_NAMES_M = ["Rajesh","Amit","Vikram","Suresh","Karan","Ravi","Mohan","Arjun","Rohan","Sanjay",
    "Anil","Deepak","Gaurav","Harsh","Jai","Kunal","Lakshman","Manish","Nikhil","Om",
    "Pankaj","Rahul","Sachin","Tarun","Uday","Vinod","Yash","Ajay","Bharat","Chetan",
    "Dhruv","Eshan","Farhan","Girish","Hemant","Ishaan","Jatin","Kartik","Lalit","Mayank"]
FIRST_NAMES_F = ["Priya","Sneha","Anita","Meena","Deepa","Sunita","Kavita","Neha","Pooja","Divya",
    "Aarti","Bhavna","Chhaya","Disha","Ekta","Fatima","Gauri","Heena","Isha","Juhi",
    "Komal","Lata","Manju","Nandini","Padma","Rachna","Sarita","Tanvi","Uma","Vandana"]
LAST_NAMES = ["Sharma","Patel","Kumar","Gupta","Singh","Desai","Reddy","Iyer","Mehta","Nair",
    "Joshi","Verma","Das","Rao","Malhotra","Chopra","Bajaj","Agarwal","Mishra","Kapoor",
    "Bhatt","Chauhan","Dubey","Garg","Hegde","Iyengar","Jain","Khanna","Luthra","Menon",
    "Naik","Oberoi","Pandey","Qureshi","Rathore","Saxena","Tiwari","Upadhyay","Vyas","Yadav"]

BANKS = [
    ("PSB National Bank", "PSBN"),
    ("State Bank of India", "SBIN"),
    ("Punjab National Bank", "PNBK"),
    ("Bank of Baroda", "BARB"),
    ("Canara Bank", "CNRB"),
    ("Union Bank of India", "UBIN"),
    ("HDFC Bank", "HDFC"),
    ("ICICI Bank", "ICIC"),
    ("Axis Bank", "AXIS"),
    ("Kotak Mahindra Bank", "KOTK"),
]

CITIES = ["Mumbai","Delhi","Bangalore","Chennai","Hyderabad","Pune","Kolkata",
    "Ahmedabad","Jaipur","Lucknow","Chandigarh","Kochi","Indore","Bhopal",
    "Nagpur","Surat","Vadodara","Visakhapatnam","Coimbatore","Thiruvananthapuram"]

ACCOUNT_TYPES = ["Savings","Current","Salary","NRI","Joint","Fixed Deposit"]
KYC_STATUSES = ["Verified","Verified","Verified","Verified","Pending Review","Expired","Re-KYC Due"]
CHANNELS = ["UPI","UPI","UPI","IMPS","IMPS","NEFT","NEFT","RTGS","SWIFT","CBS"]

# ─── Generate Accounts ───
def generate_accounts(n=1000):
    accounts = []
    for i in range(n):
        is_female = random.random() < 0.45
        first = random.choice(FIRST_NAMES_F if is_female else FIRST_NAMES_M)
        last = random.choice(LAST_NAMES)
        name = f"{first} {last}"
        bank_name, bank_code = random.choice(BANKS)
        acc_id = f"{bank_code}{random.randint(10000000, 99999999)}"
        opened = datetime(2015, 1, 1) + timedelta(days=random.randint(0, 3650))
        accounts.append({
            "account_id": acc_id,
            "holder_name": name,
            "gender": "F" if is_female else "M",
            "bank": bank_name,
            "bank_code": bank_code,
            "account_type": random.choice(ACCOUNT_TYPES),
            "kyc_status": random.choice(KYC_STATUSES),
            "opened_date": opened.strftime("%Y-%m-%d"),
            "city": random.choice(CITIES),
            "risk_label": "normal",  # updated later for fraud accounts
        })
    return accounts


# ─── Generate Fraud Rings ───
def inject_fraud_patterns(accounts):
    """Mark certain accounts as part of fraud rings and return ring definitions."""
    n = len(accounts)
    rings = []
    fraud_indices = set()

    # Circular flow rings (15 rings of 4-6 accounts each)
    for ring_id in range(15):
        ring_size = random.randint(4, 6)
        # Pick accounts not already in a ring
        candidates = [i for i in range(n) if i not in fraud_indices]
        if len(candidates) < ring_size:
            break
        ring_members = random.sample(candidates, ring_size)
        ring_members.append(ring_members[0])  # close the cycle
        for idx in ring_members[:-1]:
            accounts[idx]["risk_label"] = "circular_flow"
            fraud_indices.add(idx)
        rings.append({"type": "circular_flow", "members": ring_members, "ring_id": ring_id})

    # Structuring accounts (20 sender-receiver pairs)
    for struct_id in range(20):
        candidates = [i for i in range(n) if i not in fraud_indices]
        if len(candidates) < 2:
            break
        pair = random.sample(candidates, 2)
        accounts[pair[0]]["risk_label"] = "structuring_sender"
        accounts[pair[1]]["risk_label"] = "structuring_receiver"
        fraud_indices.update(pair)
        rings.append({"type": "structuring", "members": pair, "ring_id": struct_id})

    # Layering chains (10 chains of 5-8 accounts)
    for layer_id in range(10):
        chain_len = random.randint(5, 8)
        candidates = [i for i in range(n) if i not in fraud_indices]
        if len(candidates) < chain_len:
            break
        chain = random.sample(candidates, chain_len)
        for idx in chain:
            accounts[idx]["risk_label"] = "layering"
            fraud_indices.add(idx)
        rings.append({"type": "layering", "members": chain, "ring_id": layer_id})

    # Dormant reactivation (15 accounts)
    for dorm_id in range(15):
        candidates = [i for i in range(n) if i not in fraud_indices]
        if not candidates:
            break
        idx = random.choice(candidates)
        accounts[idx]["risk_label"] = "dormant_reactivation"
        accounts[idx]["opened_date"] = (datetime(2015, 1, 1) + timedelta(days=random.randint(0, 1000))).strftime("%Y-%m-%d")
        fraud_indices.add(idx)
        rings.append({"type": "dormant_reactivation", "members": [idx], "ring_id": dorm_id})

    return rings, fraud_indices


# ─── Generate Transactions ───
def generate_transactions(accounts, rings, fraud_indices, n_total=50000):
    txns = []
    n_accounts = len(accounts)
    fraud_ratio = 0.05
    n_fraud = int(n_total * fraud_ratio)
    n_normal = n_total - n_fraud

    base_date = datetime(2026, 5, 1)

    # Normal transactions
    for i in range(n_normal):
        ts = base_date + timedelta(seconds=random.randint(0, 15 * 86400))
        s_idx = random.randint(0, n_accounts - 1)
        r_idx = random.randint(0, n_accounts - 1)
        while r_idx == s_idx:
            r_idx = random.randint(0, n_accounts - 1)

        amount = round(random.choice([
            random.uniform(50, 5000),
            random.uniform(5000, 50000),
            random.uniform(50000, 300000),
            random.uniform(100, 25000),
        ]), 2)

        txns.append(_make_txn(accounts, s_idx, r_idx, amount, ts, "normal", "none"))

    # Fraud transactions
    fraud_txn_count = 0
    for ring in rings:
        if fraud_txn_count >= n_fraud:
            break
        members = ring["members"]
        rtype = ring["type"]

        if rtype == "circular_flow":
            # Generate 5-15 transactions cycling through the ring
            n_cycles = random.randint(5, 15)
            for j in range(n_cycles):
                if fraud_txn_count >= n_fraud:
                    break
                s_idx = members[j % (len(members) - 1)]
                r_idx = members[(j + 1) % (len(members) - 1)]
                amount = round(random.uniform(500000, 3000000) * random.uniform(0.95, 1.05), 2)
                ts = base_date + timedelta(days=random.randint(0, 15), hours=random.randint(0, 23), minutes=random.randint(0, 59))
                txns.append(_make_txn(accounts, s_idx, r_idx, amount, ts, "circular_flow", f"ring_{ring['ring_id']}"))
                fraud_txn_count += 1

        elif rtype == "structuring":
            # 8-20 transactions just below ₹10L threshold
            n_struct = random.randint(8, 20)
            for j in range(n_struct):
                if fraud_txn_count >= n_fraud:
                    break
                amount = round(random.uniform(800000, 999999), 2)
                ts = base_date + timedelta(days=random.randint(0, 15), hours=random.randint(9, 17))
                txns.append(_make_txn(accounts, members[0], members[1], amount, ts, "structuring", f"struct_{ring['ring_id']}"))
                fraud_txn_count += 1

        elif rtype == "layering":
            # Chain of transfers, each slightly reduced
            n_layers = len(members) - 1
            base_amount = random.uniform(1000000, 5000000)
            for j in range(n_layers):
                if fraud_txn_count >= n_fraud:
                    break
                amount = round(base_amount * (0.95 ** j) + random.uniform(-5000, 5000), 2)
                ts = base_date + timedelta(days=random.randint(0, 3), hours=j, minutes=random.randint(0, 30))
                txns.append(_make_txn(accounts, members[j], members[j + 1], amount, ts, "layering", f"layer_{ring['ring_id']}"))
                fraud_txn_count += 1

        elif rtype == "dormant_reactivation":
            # Sudden burst of activity on dormant account
            idx = members[0]
            n_burst = random.randint(5, 12)
            for j in range(n_burst):
                if fraud_txn_count >= n_fraud:
                    break
                r_idx = random.randint(0, n_accounts - 1)
                while r_idx == idx:
                    r_idx = random.randint(0, n_accounts - 1)
                amount = round(random.uniform(200000, 2000000), 2)
                ts = base_date + timedelta(days=random.randint(12, 15), hours=random.randint(22, 23), minutes=random.randint(0, 59))
                txns.append(_make_txn(accounts, idx, r_idx, amount, ts, "dormant_reactivation", f"dormant_{ring['ring_id']}"))
                fraud_txn_count += 1

    # Fill remaining fraud quota with random suspicious patterns
    while fraud_txn_count < n_fraud:
        fraud_accs = list(fraud_indices)
        s_idx = random.choice(fraud_accs)
        r_idx = random.randint(0, n_accounts - 1)
        while r_idx == s_idx:
            r_idx = random.randint(0, n_accounts - 1)
        amount = round(random.uniform(500000, 3000000), 2)
        ts = base_date + timedelta(days=random.randint(0, 15), hours=random.randint(0, 23))
        txns.append(_make_txn(accounts, s_idx, r_idx, amount, ts, "suspicious", "misc"))
        fraud_txn_count += 1

    random.shuffle(txns)
    return txns


def _make_txn(accounts, s_idx, r_idx, amount, timestamp, pattern, pattern_group):
    sender = accounts[s_idx]
    receiver = accounts[r_idx]
    channel = random.choice(CHANNELS)
    # High-value txns tend to use RTGS/NEFT
    if amount > 500000:
        channel = random.choice(["RTGS", "RTGS", "NEFT", "IMPS", "SWIFT"])
    elif amount > 100000:
        channel = random.choice(["NEFT", "IMPS", "RTGS", "UPI"])

    return {
        "txn_id": f"TXN{timestamp.strftime('%Y%m%d')}{uuid.uuid4().hex[:8].upper()}",
        "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "sender_account": sender["account_id"],
        "sender_name": sender["holder_name"],
        "sender_bank": sender["bank"],
        "receiver_account": receiver["account_id"],
        "receiver_name": receiver["holder_name"],
        "receiver_bank": receiver["bank"],
        "amount": amount,
        "channel": channel,
        "location": sender["city"],
        "device_id": f"DEV-{uuid.uuid4().hex[:12].upper()}",
        "ip_address": f"{random.choice(['192.168','10.0','172.16'])}.{random.randint(1,255)}.{random.randint(1,255)}",
        "pattern_type": pattern,
        "pattern_group": pattern_group,
    }


# ─── Main ───
if __name__ == "__main__":
    print("Generating 1,000 synthetic accounts...")
    accounts = generate_accounts(1000)

    print("Injecting fraud patterns...")
    rings, fraud_indices = inject_fraud_patterns(accounts)

    print(f"  - {sum(1 for r in rings if r['type']=='circular_flow')} circular flow rings")
    print(f"  - {sum(1 for r in rings if r['type']=='structuring')} structuring pairs")
    print(f"  - {sum(1 for r in rings if r['type']=='layering')} layering chains")
    print(f"  - {sum(1 for r in rings if r['type']=='dormant_reactivation')} dormant reactivations")
    print(f"  - {len(fraud_indices)} total fraud-linked accounts ({len(fraud_indices)/len(accounts)*100:.1f}%)")

    print("Generating 50,000 transactions...")
    txns = generate_transactions(accounts, rings, fraud_indices, n_total=50000)

    fraud_txns = sum(1 for t in txns if t["pattern_type"] != "normal")
    print(f"  - {fraud_txns} suspicious transactions ({fraud_txns/len(txns)*100:.1f}%)")
    print(f"  - {len(txns) - fraud_txns} normal transactions")

    # Write accounts CSV
    acc_path = os.path.join(OUTPUT_DIR, "accounts.csv")
    with open(acc_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(accounts[0].keys()))
        w.writeheader()
        w.writerows(accounts)
    print(f"Saved: {acc_path}")

    # Write transactions CSV
    txn_path = os.path.join(OUTPUT_DIR, "transactions.csv")
    with open(txn_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(txns[0].keys()))
        w.writeheader()
        w.writerows(txns)
    print(f"Saved: {txn_path}")

    # Write fraud rings metadata
    import json
    rings_path = os.path.join(OUTPUT_DIR, "fraud_rings.json")
    serializable_rings = []
    for r in rings:
        sr = dict(r)
        sr["account_ids"] = [accounts[i]["account_id"] for i in r["members"] if i < len(accounts)]
        serializable_rings.append(sr)
    with open(rings_path, "w", encoding="utf-8") as f:
        json.dump(serializable_rings, f, indent=2)
    print(f"Saved: {rings_path}")

    print("\nDataset generation complete!")
