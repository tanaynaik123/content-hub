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
import secrets
import string
import tempfile
import time
from unittest import mock
import pytest
import requests

from ..core.datamodels import ActionStatusData, EndpointData, FileRetrievalDetails
from ..core.exceptions import (
    CortexXDRActionError,
    CortexXDRAcquisitionPendingError,
    CortexXDRAuthError,
    CortexXDRException,
    CortexXDRNotFoundError,
    CortexXDRValidationError,
)
from ..core.CortexXDRResponseManager import CortexXDRResponseManager, get_os_type


class TestCortexXDRAuthAndInit:
    def test_init_properties(self, manager, api_root, api_key_id, api_key):
        assert manager.api_root == api_root
        assert manager.api_key_id == api_key_id
        assert manager.api_key == api_key
        assert manager.verify_ssl is True
        assert manager.session.verify is True

    def test_init_trailing_slashes_stripped(self, api_key_id, api_key):
        mgr = CortexXDRResponseManager(
            api_root="https://api-gw.paloaltonetworks.com///",
            api_key_id=api_key_id,
            api_key=api_key,
            verify_ssl=False,
        )
        assert mgr.api_root == "https://api-gw.paloaltonetworks.com"
        assert mgr.verify_ssl is False
        assert mgr.session.verify is False

    def test_generate_auth_headers_structure_and_hash(self, manager):
        headers = manager._generate_auth_headers()
        assert "x-xdr-timestamp" in headers
        assert "x-xdr-nonce" in headers
        assert "x-xdr-auth-id" in headers
        assert "Authorization" in headers
        assert headers["Content-Type"] == "application/json"

        assert len(headers["x-xdr-nonce"]) == 64
        assert headers["x-xdr-auth-id"] == manager.api_key_id

        expected_key = f"{manager.api_key}{headers['x-xdr-nonce']}{headers['x-xdr-timestamp']}"
        expected_hash = hashlib.sha256(expected_key.encode("utf-8")).hexdigest()
        assert headers["Authorization"] == expected_hash

    def test_os_type_normalization(self):
        assert get_os_type("Windows 10 Enterprise") == "windows"
        assert get_os_type("WIN_SERVER_2019") == "windows"
        assert get_os_type("macos 14 Sonoma") == "macos"
        assert get_os_type("Mac OS X 10.15") == "macos"
        assert get_os_type("Darwin 23.4") == "macos"
        assert get_os_type("Ubuntu 22.04 LTS") == "linux"
        assert get_os_type("CentOS Linux 7") == "linux"
        assert get_os_type("RHEL 8") == "linux"
        assert get_os_type(None) == "windows"
        assert get_os_type("") == "windows"


class TestValidateResponseAndErrorHandling:
    def test_validate_response_200_ok(self, manager, mock_response):
        resp = mock_response(json_data={"reply": True}, status_code=200)
        manager.validate_response(resp)

    def test_validate_response_401_auth_error(self, manager, mock_response):
        resp = mock_response(
            json_data={"reply": {"err_code": 401, "err_msg": "Invalid authorization credentials"}},
            status_code=401,
        )
        with pytest.raises(CortexXDRAuthError) as exc_info:
            manager.validate_response(resp)
        assert "authentication failed" in str(exc_info.value).lower()

    def test_validate_response_403_auth_error(self, manager, mock_response):
        resp = mock_response(
            json_data={"reply": {"err_code": 403, "err_msg": "Unauthorized"}},
            status_code=403,
        )
        with pytest.raises(CortexXDRAuthError):
            manager.validate_response(resp)

    def test_validate_response_404_not_found(self, manager, mock_response):
        resp = mock_response(
            json_data={"reply": {"err_code": 404, "err_msg": "Endpoint does not exist"}},
            status_code=404,
        )
        with pytest.raises(CortexXDRNotFoundError):
            manager.validate_response(resp)

    def test_validate_response_400_validation_error(self, manager, mock_response):
        resp = mock_response(
            json_data={"reply": {"err_code": 400, "err_msg": "Not a valid escaped full path"}},
            status_code=400,
        )
        with pytest.raises(CortexXDRValidationError):
            manager.validate_response(resp)

    def test_validate_response_500_action_error(self, manager, mock_response):
        resp = mock_response(
            json_data={"reply": {"err_code": 500, "err_msg": "Internal Server Error"}},
            status_code=500,
        )
        with pytest.raises(CortexXDRActionError):
            manager.validate_response(resp)


class TestConnectivityAndEndpointLookup:
    def test_test_connectivity_success(self, manager, mock_response):
        resp = mock_response(json_data={"reply": {"endpoints": []}}, status_code=200)
        with mock.patch.object(manager.session, "post", return_value=resp) as mock_post:
            assert manager.test_connectivity() is True
            assert mock_post.called
            url = mock_post.call_args[0][0]
            assert url == "https://api-gw.paloaltonetworks.com/public_api/v1/endpoints/get_endpoint/"

    def test_get_endpoint_by_id_success(self, manager, mock_response):
        endpoint_payload = {
            "reply": {
                "endpoints": [
                    {
                        "endpoint_id": "ep-12345",
                        "endpoint_name": "WIN-SRV-01",
                        "os_type": "AGENT_OS_WINDOWS",
                        "is_isolated": "AGENT_ISOLATED",
                        "ip": ["192.168.1.50"],
                        "endpoint_status": "CONNECTED",
                    }
                ]
            }
        }
        resp = mock_response(json_data=endpoint_payload, status_code=200)
        with mock.patch.object(manager.session, "post", return_value=resp):
            endpoint = manager.get_endpoint_by_id("ep-12345")
            assert isinstance(endpoint, EndpointData)
            assert endpoint.endpoint_id == "ep-12345"
            assert endpoint.endpoint_name == "WIN-SRV-01"
            assert endpoint.is_isolated == "AGENT_ISOLATED"
            assert endpoint.ip_addresses == ["192.168.1.50"]
            assert endpoint.endpoint_status == "CONNECTED"

    def test_get_endpoint_by_id_not_found(self, manager, mock_response):
        resp = mock_response(json_data={"reply": {"endpoints": []}}, status_code=200)
        with mock.patch.object(manager.session, "post", return_value=resp):
            with pytest.raises(CortexXDRNotFoundError):
                manager.get_endpoint_by_id("nonexistent-ep")


class TestContainmentOperations:
    def test_isolate_endpoint_success(self, manager, mock_response):
        resp = mock_response(json_data={"reply": {"action_id": 9988}}, status_code=200)
        with mock.patch.object(manager.session, "post", return_value=resp) as mock_post:
            action_id = manager.isolate_endpoint("ep-12345")
            assert action_id == 9988
            url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
            assert url == "https://api-gw.paloaltonetworks.com/public_api/v1/endpoints/isolate/"
            assert kwargs["json"]["request_data"]["endpoint_id"] == "ep-12345"

    def test_unisolate_endpoint_success(self, manager, mock_response):
        resp = mock_response(json_data={"reply": {"action_id": 7766}}, status_code=200)
        with mock.patch.object(manager.session, "post", return_value=resp) as mock_post:
            action_id = manager.unisolate_endpoint("ep-12345")
            assert action_id == 7766
            url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
            assert url == "https://api-gw.paloaltonetworks.com/public_api/v1/endpoints/unisolate/"
            assert kwargs["json"]["request_data"]["endpoint_id"] == "ep-12345"

    def test_get_containment_status_mappings(self, manager, mock_response):
        def create_ep_resp(isolated_val):
            return mock_response(
                json_data={
                    "reply": {
                        "endpoints": [
                            {"endpoint_id": "ep-1", "is_isolated": isolated_val}
                        ]
                    }
                },
                status_code=200,
            )

        with mock.patch.object(manager.session, "post", return_value=create_ep_resp("AGENT_ISOLATED")):
            assert manager.get_containment_status("ep-1") == "contained"

        with mock.patch.object(manager.session, "post", return_value=create_ep_resp("AGENT_UNISOLATED")):
            assert manager.get_containment_status("ep-1") == "uncontained"

        with mock.patch.object(manager.session, "post", return_value=create_ep_resp("AGENT_PENDING_ISOLATION")):
            assert manager.get_containment_status("ep-1") == "containment_requested"

        with mock.patch.object(manager.session, "post", return_value=create_ep_resp("AGENT_PENDING_UNISOLATION")):
            assert manager.get_containment_status("ep-1") == "uncontainment_requested"

        with mock.patch.object(manager.session, "post", return_value=create_ep_resp("UNKNOWN_STATE")):
            assert manager.get_containment_status("ep-1") == "unknown"


class TestFileRetrievalAndDownload:
    def test_initiate_file_retrieval_success(self, manager, mock_response):
        resp = mock_response(json_data={"reply": {"action_id": 5544}}, status_code=200)
        with mock.patch.object(manager.session, "post", return_value=resp) as mock_post:
            action_id = manager.initiate_file_retrieval(
                endpoint_id="ep-12345",
                os_type="windows",
                file_path="C:\\Windows\\System32\\calc.exe",
            )
            assert action_id == 5544
            url, kwargs = mock_post.call_args[0][0], mock_post.call_args[1]
            assert url == "https://api-gw.paloaltonetworks.com/public_api/v1/endpoints/file_retrieval/"
            files_dict = kwargs["json"]["request_data"]["files"]
            assert "windows" in files_dict
            assert files_dict["windows"] == ["C:\\Windows\\System32\\calc.exe"]

    def test_get_action_status_success(self, manager, mock_response):
        status_payload = {
            "reply": {
                "data": {"ep-12345": "COMPLETED_SUCCESSFULLY"},
                "errorReasons": None,
            }
        }
        resp = mock_response(json_data=status_payload, status_code=200)
        with mock.patch.object(manager.session, "post", return_value=resp):
            status_data = manager.get_action_status(5544)
            assert isinstance(status_data, ActionStatusData)
            assert status_data.action_id == 5544
            assert status_data.status == "COMPLETED_SUCCESSFULLY"
            assert status_data.endpoint_statuses["ep-12345"] == "COMPLETED_SUCCESSFULLY"

    def test_get_file_retrieval_details_success(self, manager, mock_response):
        details_payload = {
            "reply": {
                "data": {
                    "ep-12345": "https://api-gw.paloaltonetworks.com/public_api/v1/download/package_5544.zip"
                }
            }
        }
        resp = mock_response(json_data=details_payload, status_code=200)
        with mock.patch.object(manager.session, "post", return_value=resp):
            details = manager.get_file_retrieval_details(5544)
            assert isinstance(details, FileRetrievalDetails)
            assert details.action_id == 5544
            download_url = details.get_download_url("ep-12345")
            assert download_url == "https://api-gw.paloaltonetworks.com/public_api/v1/download/package_5544.zip"

    def test_download_file_stream_success(self, manager, mock_response):
        dummy_content = b"Simulated Zip Content For Palo Alto Cortex XDR File Retrieval"
        resp = mock_response(raw_bytes=dummy_content, status_code=200)

        with mock.patch.object(manager.session, "post", return_value=resp):
            with tempfile.TemporaryDirectory() as tmpdir:
                file_path, sha256_hash, file_size = manager.download_file_stream(
                    download_url="https://api-gw.paloaltonetworks.com/public_api/v1/download/package_5544.zip",
                    destination_dir=tmpdir,
                )
                assert os.path.exists(file_path)
                assert file_size == len(dummy_content)
                assert sha256_hash == hashlib.sha256(dummy_content).hexdigest()
                with open(file_path, "rb") as f:
                    assert f.read() == dummy_content
