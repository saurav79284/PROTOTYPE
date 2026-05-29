"""Pydantic models for FundFlow Intelligence API."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class TransactionChannel(str, Enum):
    UPI = "UPI"
    IMPS = "IMPS"
    RTGS = "RTGS"
    NEFT = "NEFT"
    SWIFT = "SWIFT"
    CBS = "CBS"


class AlertStatus(str, Enum):
    PENDING = "PENDING"
    INVESTIGATING = "INVESTIGATING"
    CONFIRMED_FRAUD = "CONFIRMED_FRAUD"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    STR_FILED = "STR_FILED"


class RiskTier(str, Enum):
    LOW = "LOW"           # 0-30
    MEDIUM = "MEDIUM"     # 31-60
    HIGH = "HIGH"         # 61-85
    CRITICAL = "CRITICAL" # 86-100


class Transaction(BaseModel):
    txn_id: str
    timestamp: datetime
    sender_account: str
    sender_name: str
    receiver_account: str
    receiver_name: str
    amount: float
    channel: TransactionChannel
    sender_bank: str = "PSB National Bank"
    receiver_bank: str = "PSB National Bank"
    location: Optional[str] = None
    device_id: Optional[str] = None
    ip_address: Optional[str] = None


class MLScore(BaseModel):
    composite_score: float = Field(ge=0, le=100)
    gnn_score: float = Field(ge=0, le=1)
    xgboost_score: float = Field(ge=0, le=1)
    isolation_forest_score: float = Field(ge=0, le=1)
    lstm_score: float = Field(ge=0, le=1)
    tier: RiskTier
    latency_ms: float


class SHAPExplanation(BaseModel):
    feature: str
    importance: float
    value: str
    direction: str  # "increases_risk" or "decreases_risk"


class GraphPattern(BaseModel):
    pattern_type: str  # "circular_flow", "structuring", "layering", "dormant_reactivation"
    involved_accounts: List[str]
    hop_count: int
    total_amount: float
    confidence: float
    description: str


class Alert(BaseModel):
    alert_id: str
    transaction: Transaction
    ml_score: MLScore
    shap_explanations: List[SHAPExplanation]
    graph_patterns: List[GraphPattern]
    status: AlertStatus = AlertStatus.PENDING
    created_at: datetime
    assigned_to: Optional[str] = None
    notes: Optional[str] = None
    fatf_typology: Optional[str] = None


class STRReport(BaseModel):
    str_id: str
    alert_id: str
    report_type: str = "FINNET_2.0"
    generated_at: datetime
    entity_name: str
    entity_account: str
    suspicious_amount: float
    period_start: datetime
    period_end: datetime
    narrative: str
    fatf_typology: str
    risk_indicators: List[str]
    xml_content: str
    status: str = "DRAFT"


class AccountNode(BaseModel):
    account_id: str
    holder_name: str
    bank: str
    account_type: str
    risk_score: float
    kyc_status: str
    opened_date: str
    total_inflow: float
    total_outflow: float
    transaction_count: int


class GraphEdge(BaseModel):
    source: str
    target: str
    amount: float
    count: int
    channel: str
    is_suspicious: bool = False


class NetworkGraph(BaseModel):
    nodes: List[AccountNode]
    edges: List[GraphEdge]
    circular_flows: List[GraphPattern]


class DashboardStats(BaseModel):
    total_transactions_today: int
    total_amount_today: float
    alerts_generated: int
    critical_alerts: int
    avg_risk_score: float
    circular_flows_detected: int
    str_reports_filed: int
    false_positive_rate: float
    avg_latency_ms: float
    channels_active: dict
