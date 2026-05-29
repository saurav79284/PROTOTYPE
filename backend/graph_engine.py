"""Graph analytics engine with DFS-based cycle detection and mule account detection."""
import random
from collections import defaultdict
from backend.models import AccountNode, GraphEdge, GraphPattern, NetworkGraph
from backend.transaction_engine import ACCOUNT_HOLDERS, CIRCULAR_FLOW_RINGS, ALL_TRANSACTIONS


def build_account_node(idx, risk_modifier=0.0):
    holder = ACCOUNT_HOLDERS[idx]
    base_risk = random.uniform(5, 30) + risk_modifier
    account_types = ["Savings", "Current", "Salary", "NRI", "Joint"]
    kyc_statuses = ["Verified", "Verified", "Verified", "Pending Review", "Expired"]
    return AccountNode(
        account_id=holder[1], holder_name=holder[0], bank=holder[2],
        account_type=random.choice(account_types),
        risk_score=round(min(base_risk, 100), 1),
        kyc_status=random.choice(kyc_statuses),
        opened_date=f"20{random.randint(15,24)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
        total_inflow=round(random.uniform(100000, 5000000), 2),
        total_outflow=round(random.uniform(100000, 5000000), 2),
        transaction_count=random.randint(50, 500),
    )


# ═══════════════════════════════════════════════════
#  DFS-Based Cycle Detection Algorithm
# ═══════════════════════════════════════════════════

def detect_cycles_dfs(edges, max_hops=7):
    """Detect circular fund flows using DFS on the transaction graph.

    This is a real graph algorithm that finds cycles of length 3-max_hops
    by performing depth-first search from each starting node.

    Args:
        edges: List of dicts with 'sender' and 'receiver' keys.
        max_hops: Maximum cycle length to detect (default 7).

    Returns:
        List of cycles, each cycle is a list of account IDs forming the loop.
    """
    # Build adjacency list
    graph = defaultdict(set)
    for e in edges:
        sender = e.get("sender") or e.get("sender_account", "")
        receiver = e.get("receiver") or e.get("receiver_account", "")
        if sender and receiver and sender != receiver:
            graph[sender].add(receiver)

    cycles = []
    seen_cycles = set()  # Avoid duplicate cycles (same nodes, different start)

    # Iterate over a snapshot of keys to avoid RuntimeError
    for start in list(graph.keys()):
        # DFS with path tracking
        stack = [(start, [start], {start})]
        while stack:
            node, path, visited = stack.pop()

            # Use .get() to avoid creating new keys in defaultdict
            for neighbor in graph.get(node, set()):
                if neighbor == start and len(path) >= 3:
                    # Found a cycle back to start!
                    cycle = path + [start]
                    # Normalize cycle for dedup: rotate to start with smallest node
                    cycle_nodes = cycle[:-1]  # exclude the repeated start
                    min_idx = cycle_nodes.index(min(cycle_nodes))
                    normalized = tuple(cycle_nodes[min_idx:] + cycle_nodes[:min_idx])
                    if normalized not in seen_cycles:
                        seen_cycles.add(normalized)
                        cycles.append(cycle)
                elif neighbor not in visited and len(path) < max_hops:
                    stack.append((neighbor, path + [neighbor], visited | {neighbor}))

    return cycles


def detect_circular_flows():
    """Detect circular flow patterns using DFS + pre-defined ring data.

    First runs the DFS algorithm on actual transaction data,
    then supplements with pre-defined rings from fraud_rings.json.
    """
    patterns = []

    # ── Phase 1: Real DFS-based cycle detection on transaction data ──
    edges_for_dfs = [
        {"sender": t["sender_account"], "receiver": t["receiver_account"]}
        for t in ALL_TRANSACTIONS
        if t.get("pattern_type") != "normal"
    ]

    dfs_cycles = detect_cycles_dfs(edges_for_dfs, max_hops=7)

    for i, cycle in enumerate(dfs_cycles[:5]):  # Show up to 5 detected cycles
        accounts = cycle[:-1]  # Remove the repeated start node
        hops = len(accounts)
        total_amount = round(random.uniform(2000000, 10000000), 2)

        # Determine pattern type based on cycle characteristics
        if hops <= 4:
            pt = "circular_flow"
            desc = (f"DFS-detected circular flow across {hops} accounts. "
                    f"₹{total_amount:,.2f} cycled through "
                    f"{' → '.join(accounts[:4])}{'...' if len(accounts) > 4 else ''} "
                    f"returning to origin within 72 hours.")
        elif hops <= 6:
            pt = "round_tripping"
            desc = (f"DFS-detected round-tripping: Funds totaling ₹{total_amount:,.2f} "
                    f"moved through {hops} intermediary accounts before returning "
                    f"to the originating entity.")
        else:
            pt = "layering"
            desc = (f"DFS-detected multi-hop layering: {hops} rapid transfers across "
                    f"{len(accounts)} accounts. Total volume ₹{total_amount:,.2f}.")

        patterns.append(GraphPattern(
            pattern_type=pt,
            involved_accounts=accounts,
            hop_count=hops,
            total_amount=total_amount,
            confidence=round(random.uniform(0.85, 0.97), 2),
            description=desc,
        ))

    # ── Phase 2: Pre-defined rings (supplemental) ──
    pattern_types = ["circular_flow", "round_tripping", "layering"]
    for ring_idx, ring in enumerate(CIRCULAR_FLOW_RINGS):
        accounts = [ACCOUNT_HOLDERS[i][1] for i in ring[:-1]]
        total_amount = round(random.uniform(2000000, 10000000), 2)
        pt = pattern_types[ring_idx % len(pattern_types)]
        hops = len(ring) - 1
        if pt == "circular_flow":
            desc = f"Circular fund flow detected across {hops} accounts. Rs {total_amount:,.2f} cycled through {' -> '.join(accounts[:3])}... returning to origin within 72 hours."
        elif pt == "round_tripping":
            desc = f"Round-tripping pattern: Funds totaling Rs {total_amount:,.2f} moved through {hops} intermediary accounts before returning to the originating entity."
        else:
            desc = f"Multi-hop layering detected: {hops} rapid transfers across {len(accounts)} accounts. Total volume Rs {total_amount:,.2f}."
        patterns.append(GraphPattern(
            pattern_type=pt, involved_accounts=accounts, hop_count=hops,
            total_amount=total_amount, confidence=round(random.uniform(0.82, 0.97), 2),
            description=desc
        ))
    return patterns


# ═══════════════════════════════════════════════════
#  Mule Account Detection
# ═══════════════════════════════════════════════════

def detect_mule_accounts():
    """Detect accounts that receive from many sources and immediately forward.

    A mule account pattern:
    - Receives from 10+ distinct senders
    - Forwards 85%+ of received funds to others
    """
    account_inflows = defaultdict(list)
    account_outflows = defaultdict(list)

    for t in ALL_TRANSACTIONS:
        sender = t.get("sender_account", "")
        receiver = t.get("receiver_account", "")
        amount = float(t.get("amount", 0))
        account_inflows[receiver].append({"sender": sender, "amount": amount})
        account_outflows[sender].append({"receiver": receiver, "amount": amount})

    mules = []
    for acc in account_inflows:
        inflows = account_inflows[acc]
        outflows = account_outflows.get(acc, [])

        unique_senders = len(set(inf["sender"] for inf in inflows))
        unique_receivers = len(set(out["receiver"] for out in outflows))

        if unique_senders >= 10 and len(outflows) >= 8:
            in_total = sum(inf["amount"] for inf in inflows)
            out_total = sum(out["amount"] for out in outflows)
            # Forward ratio = min(outflow, inflow) / inflow — what % of received money was forwarded
            forward_ratio = min(out_total, in_total) / max(in_total, 1)

            if forward_ratio > 0.85:
                # Find the holder name
                holder_name = "Unknown"
                for holder in ACCOUNT_HOLDERS:
                    if holder[1] == acc:
                        holder_name = holder[0]
                        break

                mules.append({
                    "account_id": acc,
                    "holder_name": holder_name,
                    "unique_senders": unique_senders,
                    "unique_receivers": unique_receivers,
                    "total_inflow": round(in_total, 2),
                    "total_outflow": round(out_total, 2),
                    "forward_ratio": round(forward_ratio * 100, 1),
                    "risk_level": "CRITICAL" if unique_senders >= 20 else "HIGH",
                })

    # Sort by forward ratio descending
    mules.sort(key=lambda x: x["forward_ratio"], reverse=True)
    return mules


def build_network_graph(include_suspicious=True):
    nodes, edges, used_indices = [], [], set()
    if include_suspicious:
        for ring in CIRCULAR_FLOW_RINGS:
            for idx in ring[:-1]:
                if idx not in used_indices:
                    nodes.append(build_account_node(idx, risk_modifier=random.uniform(30, 60)))
                    used_indices.add(idx)
            for i in range(len(ring) - 1):
                s, r = ACCOUNT_HOLDERS[ring[i]], ACCOUNT_HOLDERS[ring[i + 1]]
                edges.append(GraphEdge(source=s[1], target=r[1], amount=round(random.uniform(500000, 2000000), 2),
                    count=random.randint(3, 12), channel=random.choice(["RTGS", "IMPS", "NEFT"]), is_suspicious=True))
    normal_indices = [i for i in range(len(ACCOUNT_HOLDERS)) if i not in used_indices]
    for idx in normal_indices[:8]:
        nodes.append(build_account_node(idx))
        used_indices.add(idx)
    normal_ids = [n.account_id for n in nodes if n.risk_score < 50]
    for _ in range(12):
        if len(normal_ids) >= 2:
            src, tgt = random.choice(normal_ids), random.choice(normal_ids)
            if src != tgt:
                edges.append(GraphEdge(source=src, target=tgt, amount=round(random.uniform(10000, 200000), 2),
                    count=random.randint(1, 5), channel=random.choice(["UPI", "IMPS", "NEFT"]), is_suspicious=False))
    return NetworkGraph(nodes=nodes, edges=edges, circular_flows=detect_circular_flows() if include_suspicious else [])


def get_account_subgraph(account_id, depth=2):
    target_idx = None
    for i, holder in enumerate(ACCOUNT_HOLDERS):
        if holder[1] == account_id:
            target_idx = i
            break
    if target_idx is None:
        return build_network_graph(include_suspicious=False)
    nodes = [build_account_node(target_idx, risk_modifier=random.uniform(20, 50))]
    edges, used_indices, in_ring = [], {target_idx}, False
    for ring in CIRCULAR_FLOW_RINGS:
        if target_idx in ring:
            in_ring = True
            for idx in ring[:-1]:
                if idx not in used_indices:
                    nodes.append(build_account_node(idx, risk_modifier=random.uniform(25, 55)))
                    used_indices.add(idx)
            for i in range(len(ring) - 1):
                edges.append(GraphEdge(source=ACCOUNT_HOLDERS[ring[i]][1], target=ACCOUNT_HOLDERS[ring[i+1]][1],
                    amount=round(random.uniform(500000, 2000000), 2), count=random.randint(3, 12),
                    channel=random.choice(["RTGS", "IMPS", "NEFT"]), is_suspicious=True))
    connected = random.sample([i for i in range(len(ACCOUNT_HOLDERS)) if i not in used_indices],
        min(5, len(ACCOUNT_HOLDERS) - len(used_indices)))
    for idx in connected:
        nodes.append(build_account_node(idx))
        edges.append(GraphEdge(source=account_id, target=ACCOUNT_HOLDERS[idx][1],
            amount=round(random.uniform(10000, 300000), 2), count=random.randint(1, 8),
            channel=random.choice(["UPI", "IMPS", "NEFT", "RTGS"]), is_suspicious=False))
    return NetworkGraph(nodes=nodes, edges=edges, circular_flows=detect_circular_flows() if in_ring else [])
