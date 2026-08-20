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
import hashlib
import os
import re
import secrets
import string
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import requests

try:
    from .datamodels import ActionStatusData, EndpointData, FileRetrievalDetails
    from .exceptions import (
        CortexXDRActionError,
        CortexXDRAcquisitionPendingError,
        CortexXDRAuthError,
        CortexXDRException,
        CortexXDRNotFoundError,
        CortexXDRValidationError,
    )
except ImportError:
    from datamodels import ActionStatusData, EndpointData, FileRetrievalDetails
    from exceptions import (
        CortexXDRActionError,
        CortexXDRAcquisitionPendingError,
        CortexXDRAuthError,
        CortexXDRException,
        CortexXDRNotFoundError,
        CortexXDRValidationError,
    )

CONTAINMENT_STATUS_MAP = {
    "AGENT_ISOLATED": "contained",
    "AGENT_UNISOLATED": "uncontained",
    "AGENT_PENDING_ISOLATION": "containment_requested",
    "AGENT_PENDING_UNISOLATION": "uncontainment_requested",
}


def get_os_type(os_string: Optional[str]) -> str:
    """Normalize uppercase/mixed OS string to windows, macos, or linux."""
    if not os_string:
        return "windows"
    upper_os = str(os_string).upper()
    if "MAC" in upper_os or "DARWIN" in upper_os or "OSX" in upper_os or "OS X" in upper_os or "APPLE" in upper_os:
        return "macos"
    if "LINUX" in upper_os or "CENTOS" in upper_os or "UBUNTU" in upper_os or "RHEL" in upper_os or "DEBIAN" in upper_os or "SUSE" in upper_os or "FEDORA" in upper_os:
        return "linux"
    if "WIN" in upper_os:
        return "windows"
    return str(os_string).lower()


class CortexXDRResponseManager:
    """
    Decoupled Palo Alto Cortex XDR Response Actions Manager.

    Complies with Chronicle Content Hub SDK standards and Palo Alto Advanced
    API Authentication (64-character alphanumeric nonce + millisecond timestamp
    + SHA-256 HMAC digest).
    """

    def __init__(
        self,
        api_root: str,
        api_key_id: Union[str, int],
        api_key: str,
        verify_ssl: bool = True,
        siemplify_logger: Any = None,
    ):
        self.api_root = api_root.rstrip("/")
        self.api_key_id = str(api_key_id)
        self.api_key = str(api_key)
        self.verify_ssl = verify_ssl
        self.siemplify_logger = siemplify_logger

        self.session = requests.Session()
        self.session.verify = verify_ssl

    @staticmethod
    def get_os_type(os_string: Optional[str]) -> str:
        """Helper method to normalize OS type string."""
        return get_os_type(os_string)

    def _generate_auth_headers(self) -> Dict[str, str]:
        """
        Compute Palo Alto Advanced Authentication HTTP headers.

        Generates:
        - 64-character random alphanumeric nonce.
        - Millisecond timestamp string.
        - SHA-256 digest of (api_key + nonce + timestamp).
        - x-xdr-timestamp, x-xdr-nonce, x-xdr-auth-id, Authorization headers.
        """
        nonce = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(64))
        timestamp = str(int(time.time() * 1000))
        auth_key = f"{self.api_key}{nonce}{timestamp}"
        auth_hash = hashlib.sha256(auth_key.encode("utf-8")).hexdigest()

        return {
            "x-xdr-timestamp": timestamp,
            "x-xdr-nonce": nonce,
            "x-xdr-auth-id": self.api_key_id,
            "Authorization": auth_hash,
            "Content-Type": "application/json",
        }

    def validate_response(self, response: requests.Response, error_msg: str = "") -> None:
        """
        Validate HTTP response from Palo Alto Cortex XDR API.

        :param response: requests.Response object
        :param error_msg: Optional contextual error prefix
        :raises CortexXDRAuthError: On 401/403 or auth errors
        :raises CortexXDRNotFoundError: On 404 or missing resource
        :raises CortexXDRValidationError: On 400 or bad path/parameters
        :raises CortexXDRActionError: On other API errors
        """
        status_code = response.status_code
        err_text = ""
        err_code = None
        reply_dict = {}

        try:
            resp_json = response.json()
            if isinstance(resp_json, dict):
                reply_val = resp_json.get("reply")
                if isinstance(reply_val, dict):
                    reply_dict = reply_val
                    err_text = reply_dict.get("err_msg") or reply_dict.get("error") or ""
                    err_code = reply_dict.get("err_code")
                    if "err_extra" in reply_dict and reply_dict["err_extra"]:
                        err_text = f"{err_text} ({reply_dict['err_extra']})".strip()
                elif "err_msg" in resp_json:
                    err_text = resp_json.get("err_msg") or ""
                    err_code = resp_json.get("err_code")
                elif "message" in resp_json:
                    err_text = str(resp_json["message"])
                elif "error" in resp_json:
                    err_text = str(resp_json["error"])
        except Exception:
            err_text = response.text or ""

        prefix = f"{error_msg}: " if error_msg else ""
        full_msg = f"{prefix}{err_text}".strip() or f"{prefix}HTTP status {status_code}"

        if status_code in (401, 403) or err_code in (401, 403) or "invalid authorization" in err_text.lower():
            raise CortexXDRAuthError(f"Cortex XDR authentication failed: {full_msg}")

        if status_code == 404 or err_code == 404 or "does not exist" in err_text.lower() or "not found" in err_text.lower():
            raise CortexXDRNotFoundError(f"Cortex XDR resource not found: {full_msg}")

        if (
            status_code == 400
            or err_code == 400
            or "not a valid escaped full path" in err_text.lower()
            or "invalid" in err_text.lower()
        ):
            raise CortexXDRValidationError(f"Cortex XDR validation error: {full_msg}")

        if not (200 <= status_code < 300) or (err_code is not None and int(err_code) >= 400):
            raise CortexXDRActionError(f"Cortex XDR action error (HTTP {status_code}): {full_msg}")

    def test_connectivity(self) -> bool:
        """
        Validate connectivity and authentication against Cortex XDR API.

        :return: True if connection and auth succeed
        :raises CortexXDRAuthError: If authentication fails
        :raises CortexXDRException: If API error occurs
        """
        url = f"{self.api_root}/public_api/v1/endpoints/get_endpoint/"
        payload = {"request_data": {"limit": 1}}
        response = self.session.post(
            url,
            json=payload,
            headers=self._generate_auth_headers(),
        )
        self.validate_response(response, "Connectivity test failed")
        return True

    def get_endpoint_by_id(self, endpoint_id: str) -> EndpointData:
        """
        Retrieve endpoint details by endpoint ID.

        :param endpoint_id: Cortex XDR endpoint ID string
        :return: EndpointData dataclass instance
        :raises CortexXDRNotFoundError: If endpoint is not found
        :raises CortexXDRException: On API error
        """
        url = f"{self.api_root}/public_api/v1/endpoints/get_endpoint/"
        payload = {
            "request_data": {
                "filters": [
                    {
                        "field": "endpoint_id_list",
                        "operator": "in",
                        "value": [endpoint_id],
                    }
                ]
            }
        }
        response = self.session.post(
            url,
            json=payload,
            headers=self._generate_auth_headers(),
        )
        self.validate_response(response, f"Failed to get endpoint {endpoint_id}")
        resp_json = response.json()
        reply = resp_json.get("reply", {})
        endpoints = reply.get("endpoints", []) if isinstance(reply, dict) else []

        if not endpoints:
            raise CortexXDRNotFoundError(
                f"Endpoint with ID '{endpoint_id}' was not found in Cortex XDR."
            )

        return EndpointData.from_dict(endpoints[0])

    def isolate_endpoint(self, endpoint_id: str) -> int:
        """
        Isolate (contain) an endpoint.

        :param endpoint_id: Cortex XDR endpoint ID
        :return: Action ID (integer)
        :raises CortexXDRNotFoundError: If endpoint not found
        :raises CortexXDRActionError: On action/API failure
        """
        url = f"{self.api_root}/public_api/v1/endpoints/isolate/"
        payload = {"request_data": {"endpoint_id": endpoint_id}}
        response = self.session.post(
            url,
            json=payload,
            headers=self._generate_auth_headers(),
        )
        self.validate_response(response, f"Failed to isolate endpoint {endpoint_id}")
        resp_json = response.json()
        reply = resp_json.get("reply")

        if reply is None:
            raise CortexXDRActionError(f"Isolate endpoint {endpoint_id} returned no reply.")

        if isinstance(reply, dict):
            action_id = reply.get("action_id") or reply.get("group_action_id")
            if action_id is not None:
                return int(action_id)
        elif isinstance(reply, (int, str)) and str(reply).isdigit():
            return int(reply)

        raise CortexXDRActionError(f"Could not extract action_id from isolate response: {resp_json}")

    def unisolate_endpoint(self, endpoint_id: str) -> int:
        """
        Unisolate (uncontain) an endpoint.

        :param endpoint_id: Cortex XDR endpoint ID
        :return: Action ID (integer)
        :raises CortexXDRNotFoundError: If endpoint not found
        :raises CortexXDRActionError: On action/API failure
        """
        url = f"{self.api_root}/public_api/v1/endpoints/unisolate/"
        payload = {"request_data": {"endpoint_id": endpoint_id}}
        response = self.session.post(
            url,
            json=payload,
            headers=self._generate_auth_headers(),
        )
        self.validate_response(response, f"Failed to unisolate endpoint {endpoint_id}")
        resp_json = response.json()
        reply = resp_json.get("reply")

        if reply is None:
            raise CortexXDRActionError(f"Unisolate endpoint {endpoint_id} returned no reply.")

        if isinstance(reply, dict):
            action_id = reply.get("action_id") or reply.get("group_action_id")
            if action_id is not None:
                return int(action_id)
        elif isinstance(reply, (int, str)) and str(reply).isdigit():
            return int(reply)

        raise CortexXDRActionError(f"Could not extract action_id from unisolate response: {resp_json}")

    def get_containment_status(self, endpoint_id: str) -> str:
        """
        Query endpoint containment status against Cortex XDR API.

        Maps raw is_isolated field:
        - AGENT_ISOLATED -> contained
        - AGENT_UNISOLATED -> uncontained
        - AGENT_PENDING_ISOLATION -> containment_requested
        - AGENT_PENDING_UNISOLATION -> uncontainment_requested
        - fallback -> unknown

        :param endpoint_id: Cortex XDR endpoint ID
        :return: Normalized containment status string
        :raises CortexXDRNotFoundError: If endpoint not found
        """
        endpoint = self.get_endpoint_by_id(endpoint_id)
        return CONTAINMENT_STATUS_MAP.get(endpoint.is_isolated, "unknown")

    def initiate_file_retrieval(self, endpoint_id: str, os_type: str, file_path: str) -> int:
        """
        Initiate asynchronous file retrieval on an endpoint.

        :param endpoint_id: Cortex XDR endpoint ID
        :param os_type: Target OS string (e.g. windows, macos, linux, AGENT_OS_WINDOWS)
        :param file_path: Full file path on target machine
        :return: Action ID (integer)
        :raises CortexXDRValidationError: If file path is invalid
        :raises CortexXDRActionError: On API failure
        """
        normalized_os = self.get_os_type(os_type)
        sanitized_path = file_path.strip().strip('"').strip("'")
        if normalized_os == "windows":
            sanitized_path = re.sub(r"\\{2,}", r"\\", sanitized_path)

        url = f"{self.api_root}/public_api/v1/endpoints/file_retrieval/"
        payload = {
            "request_data": {
                "filters": [
                    {
                        "field": "endpoint_id_list",
                        "operator": "in",
                        "value": [endpoint_id],
                    }
                ],
                "files": {
                    normalized_os: [sanitized_path],
                },
            }
        }
        response = self.session.post(
            url,
            json=payload,
            headers=self._generate_auth_headers(),
        )
        self.validate_response(response, f"Failed to initiate file retrieval for {file_path}")
        resp_json = response.json()
        reply = resp_json.get("reply")

        if reply is None:
            raise CortexXDRActionError(
                f"File retrieval for {file_path} on endpoint {endpoint_id} returned no reply."
            )

        if isinstance(reply, dict):
            action_id = reply.get("action_id") or reply.get("group_action_id")
            if action_id is not None:
                return int(action_id)
        elif isinstance(reply, (int, str)) and str(reply).isdigit():
            return int(reply)

        raise CortexXDRActionError(
            f"Could not extract action_id from file retrieval response: {resp_json}"
        )

    def get_action_status(self, action_id: Union[int, str]) -> ActionStatusData:
        """
        Poll the status of an asynchronous action ID.

        :param action_id: Action ID (group_action_id)
        :return: ActionStatusData dataclass instance
        :raises CortexXDRActionError: On API failure
        """
        url = f"{self.api_root}/public_api/v1/actions/get_action_status"
        payload = {"request_data": {"group_action_id": int(action_id)}}
        response = self.session.post(
            url,
            json=payload,
            headers=self._generate_auth_headers(),
        )
        self.validate_response(response, f"Failed to get action status for action {action_id}")
        resp_json = response.json()
        reply = resp_json.get("reply", {})
        return ActionStatusData.from_dict(action_id=int(action_id), reply_data=reply)

    def get_file_retrieval_details(self, action_id: Union[int, str]) -> FileRetrievalDetails:
        """
        Retrieve file download URLs for a completed file retrieval action.

        :param action_id: Action ID (group_action_id)
        :return: FileRetrievalDetails dataclass instance
        :raises CortexXDRNotFoundError: If details/URLs are not found
        :raises CortexXDRActionError: On API failure
        """
        url = f"{self.api_root}/public_api/v1/actions/file_retrieval_details"
        payload = {"request_data": {"group_action_id": int(action_id)}}
        response = self.session.post(
            url,
            json=payload,
            headers=self._generate_auth_headers(),
        )
        self.validate_response(response, f"Failed to get file retrieval details for action {action_id}")
        resp_json = response.json()
        reply = resp_json.get("reply")

        if reply is None:
            raise CortexXDRNotFoundError(
                f"File retrieval details for action ID {action_id} not found."
            )

        return FileRetrievalDetails.from_dict(action_id=int(action_id), reply_data=reply)

    def download_file_stream(
        self, download_url: str, destination_dir: Optional[str] = None
    ) -> Tuple[str, str, int]:
        """
        Stream and download the acquired file package from download_url to local disk.
        Computes the SHA-256 digest and total file size during streaming.

        :param download_url: Download URL provided by Cortex XDR API
        :param destination_dir: Directory where the file package should be saved (default: system temp dir)
        :return: Tuple of (local_file_path, sha256_hash, file_size_bytes)
        :raises CortexXDRNotFoundError: If file URL returns 404
        :raises CortexXDRActionError: On download/streaming failure
        """
        if destination_dir is None:
            destination_dir = tempfile.gettempdir()

        os.makedirs(destination_dir, exist_ok=True)
        unique_suffix = secrets.token_hex(4)
        filename = f"cortex_xdr_file_{int(time.time())}_{unique_suffix}.zip"
        local_file_path = os.path.join(destination_dir, filename)

        try:
            response = self.session.post(
                download_url,
                headers=self._generate_auth_headers(),
                stream=True,
            )
            self.validate_response(response, f"Failed to download file from {download_url}")

            sha256_hash = hashlib.sha256()
            total_bytes = 0

            with open(local_file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        sha256_hash.update(chunk)
                        total_bytes += len(chunk)

            return local_file_path, sha256_hash.hexdigest(), total_bytes
        except CortexXDRException:
            if os.path.exists(local_file_path):
                try:
                    os.remove(local_file_path)
                except Exception:
                    pass
            raise
        except Exception as e:
            if os.path.exists(local_file_path):
                try:
                    os.remove(local_file_path)
                except Exception:
                    pass
            raise CortexXDRActionError(
                f"Failed to stream download file from {download_url}: {e}"
            ) from e
