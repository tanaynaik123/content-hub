# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EndpointData:
    """Dataclass representing a Palo Alto Cortex XDR Endpoint."""

    endpoint_id: str
    endpoint_name: str = ""
    os_type: str = ""
    is_isolated: str = "AGENT_UNISOLATED"
    ip_addresses: List[str] = field(default_factory=list)
    endpoint_status: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> Dict[str, Any]:
        """Convert EndpointData instance to a JSON-serializable dictionary."""
        return {
            "endpoint_id": self.endpoint_id,
            "endpoint_name": self.endpoint_name,
            "os_type": self.os_type,
            "is_isolated": self.is_isolated,
            "ip_addresses": self.ip_addresses,
            "endpoint_status": self.endpoint_status,
            "raw_data": self.raw_data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EndpointData:
        """Construct EndpointData from raw Cortex XDR API endpoint dictionary."""
        ip_list = data.get("ip") or data.get("ip_addresses") or []
        if isinstance(ip_list, str):
            ip_list = [ip_list]

        return cls(
            endpoint_id=str(data.get("endpoint_id") or data.get("id") or ""),
            endpoint_name=str(data.get("endpoint_name") or data.get("name") or data.get("computer_name") or ""),
            os_type=str(data.get("os_type") or data.get("os") or ""),
            is_isolated=str(data.get("is_isolated") or "AGENT_UNISOLATED"),
            ip_addresses=list(ip_list),
            endpoint_status=str(data.get("endpoint_status") or data.get("status") or ""),
            raw_data=data,
        )


@dataclass
class ActionStatusData:
    """Dataclass representing the status of an asynchronous Cortex XDR action."""

    action_id: int
    status: str
    endpoint_statuses: Dict[str, str] = field(default_factory=dict)
    error_reasons: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> Dict[str, Any]:
        """Convert ActionStatusData to a JSON-serializable dictionary."""
        return {
            "action_id": self.action_id,
            "status": self.status,
            "endpoint_statuses": self.endpoint_statuses,
            "error_reasons": self.error_reasons,
        }

    @classmethod
    def from_dict(cls, action_id: int, reply_data: Dict[str, Any]) -> ActionStatusData:
        """Construct ActionStatusData from raw Cortex XDR API get_action_status response reply."""
        endpoint_statuses: Dict[str, str] = {}
        error_reasons: Dict[str, Any] = (
            reply_data.get("errorReasons") or reply_data.get("error_reasons") or {}
        )
        overall_status = "UNKNOWN"

        data = reply_data.get("data")
        if isinstance(data, dict):
            endpoint_statuses = {str(k): str(v) for k, v in data.items()}
        elif isinstance(data, str):
            overall_status = data
        elif not data:
            for k, v in reply_data.items():
                if k not in ["errorReasons", "error_reasons", "action_id", "group_action_id"] and isinstance(v, str):
                    endpoint_statuses[str(k)] = str(v)

        if endpoint_statuses:
            values = list(endpoint_statuses.values())
            if any(v == "FAILED" for v in values):
                overall_status = "FAILED"
            elif any(v == "IN_PROGRESS" for v in values):
                overall_status = "IN_PROGRESS"
            elif any(v == "PENDING" for v in values):
                overall_status = "PENDING"
            elif all(v == "COMPLETED_SUCCESSFULLY" for v in values):
                overall_status = "COMPLETED_SUCCESSFULLY"
            else:
                overall_status = values[0]
        elif overall_status == "UNKNOWN" and "status" in reply_data:
            overall_status = str(reply_data["status"])

        return cls(
            action_id=int(action_id),
            status=overall_status,
            endpoint_statuses=endpoint_statuses,
            error_reasons=error_reasons,
        )


@dataclass
class FileRetrievalDetails:
    """Dataclass representing file retrieval details and download URLs."""

    action_id: int
    download_urls: Dict[str, str] = field(default_factory=dict)

    def get_download_url(self, endpoint_id: Optional[str] = None) -> Optional[str]:
        """Retrieve the download URL for a specific endpoint_id, or the first available URL."""
        if endpoint_id and endpoint_id in self.download_urls:
            return self.download_urls[endpoint_id]
        if self.download_urls:
            return next(iter(self.download_urls.values()))
        return None

    def to_json(self) -> Dict[str, Any]:
        """Convert FileRetrievalDetails to a JSON-serializable dictionary."""
        return {
            "action_id": self.action_id,
            "download_urls": self.download_urls,
        }

    @classmethod
    def from_dict(cls, action_id: int, reply_data: Dict[str, Any]) -> FileRetrievalDetails:
        """Construct FileRetrievalDetails from raw Cortex XDR file_retrieval_details response reply."""
        download_urls: Dict[str, str] = {}
        data = reply_data.get("data")
        if isinstance(data, dict):
            download_urls = {str(k): str(v) for k, v in data.items()}
        elif isinstance(data, str):
            download_urls["default"] = data
        elif isinstance(reply_data, dict):
            for k, v in reply_data.items():
                if k not in ["action_id", "group_action_id"] and isinstance(v, str) and (v.startswith("http://") or v.startswith("https://") or "/" in v):
                    download_urls[str(k)] = str(v)

        return cls(
            action_id=int(action_id),
            download_urls=download_urls,
        )
