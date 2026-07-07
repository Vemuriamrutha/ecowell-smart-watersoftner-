from typing import Any, Dict, List, Optional

from pydantic import BaseModel
class Telemetry(BaseModel):
    device_id: str
    time: Optional[str] = None
    state: str
    fault_reason: Optional[str] = None
    sensors: Dict[str, Any]
    regen_status: str


class Event(BaseModel):
    time: str
    level: str
    message: str


class DashboardData(BaseModel):
    telemetry: Dict[str, Any]
    events: List[Dict[str, Any]]