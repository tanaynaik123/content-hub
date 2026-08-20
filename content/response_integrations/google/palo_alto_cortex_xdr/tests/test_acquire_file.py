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
import json
import time
from unittest import mock
import pytest

from ..actions import AcquireFile
from ..core.datamodels import ActionStatusData, EndpointData, FileRetrievalDetails
from ..core.exceptions import (
    CortexXDRActionError,
    CortexXDRAuthError,
    CortexXDRException,
    CortexXDRNotFoundError,
    CortexXDRValidationError,
)

EXECUTION_STATE_COMPLETED = 0
EXECUTION_STATE_FAILED = 1
EXECUTION_STATE_INPROGRESS = 2
EXECUTION_STATE_TIMEDOUT = 3


@pytest.fixture
def mock_siemplify():
    siemplify = mock.MagicMock()
    siemplify.script_name = "Acquire File"
    siemplify.execution_deadline_unix_time_ms = 0
    siemplify.target_entities = []
    siemplify.parameters = {}
    siemplify.LOGGER = mock.MagicMock()
    siemplify.result = mock.MagicMock()
    siemplify.end = mock.MagicMock()
    return siemplify


@pytest.fixture
def sample_endpoint():
    return EndpointData(
        endpoint_id="cortex-ep-12345",
        endpoint_name="WORKSTATION-01",
        os_type="windows",
        is_isolated="AGENT_UNISOLATED",
        ip_addresses=["10.0.0.15"],
        endpoint_status="CONNECTED",
        raw_data={
            "endpoint_id": "cortex-ep-12345",
            "endpoint_name": "WORKSTATION-01",
            "os_type": "windows",
            "is_isolated": "AGENT_UNISOLATED",
            "ip": ["10.0.0.15"],
            "endpoint_status": "CONNECTED",
        },
    )


class TestAcquireFileAction:
    def test_first_run_initiate_success_explicit_target_os(
        self,
        mock_siemplify,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.initiate_file_retrieval.return_value = 8899

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return "cortex-ep-12345"
                if param_name == "File Path":
                    return r"C:\Windows\System32\drivers\etc\hosts"
                if param_name == "Target OS":
                    return "windows"
                if param_name == "Timeout Hours":
                    return 72
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=True)

            mock_manager.initiate_file_retrieval.assert_called_once_with(
                "cortex-ep-12345", "windows", r"C:\Windows\System32\drivers\etc\hosts"
            )
            mock_manager.get_endpoint_by_id.assert_not_called()

            mock_siemplify.result.add_result_json.assert_called_once()
            result_json = mock_siemplify.result.add_result_json.call_args[0][0]
            assert result_json["group_action_id"] == 8899
            assert result_json["endpoint_id"] == "cortex-ep-12345"
            assert result_json["file_path"] == r"C:\Windows\System32\drivers\etc\hosts"

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_INPROGRESS
            parsed_additional_data = json.loads(res)
            assert parsed_additional_data["group_action_id"] == 8899
            assert parsed_additional_data["endpoint_id"] == "cortex-ep-12345"
            assert parsed_additional_data["file_path"] == r"C:\Windows\System32\drivers\etc\hosts"
            assert "started_at" in parsed_additional_data

    def test_first_run_initiate_success_auto_detect_os(
        self,
        mock_siemplify,
        sample_endpoint,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint
        mock_manager.initiate_file_retrieval.return_value = 7711

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return "cortex-ep-12345"
                if param_name == "File Path":
                    return r"C:\Windows\System32\drivers\etc\hosts"
                if param_name == "Target OS":
                    return None
                if param_name == "Timeout Hours":
                    return 72
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=True)

            mock_manager.get_endpoint_by_id.assert_called_once_with("cortex-ep-12345")
            mock_manager.initiate_file_retrieval.assert_called_once_with(
                "cortex-ep-12345", "windows", r"C:\Windows\System32\drivers\etc\hosts"
            )

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_INPROGRESS
            parsed_data = json.loads(res)
            assert parsed_data["group_action_id"] == 7711

    def test_first_run_fallback_to_target_entity_hostname(
        self,
        mock_siemplify,
        sample_endpoint,
    ):
        mock_entity = mock.MagicMock()
        mock_entity.entity_type = "HOSTNAME"
        mock_entity.identifier = "cortex-ep-12345"
        mock_siemplify.target_entities = [mock_entity]

        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint
        mock_manager.initiate_file_retrieval.return_value = 6655

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return None
                if param_name == "File Path":
                    return "/etc/hosts"
                if param_name == "Target OS":
                    return "linux"
                if param_name == "Timeout Hours":
                    return 72
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=True)

            mock_manager.initiate_file_retrieval.assert_called_once_with(
                "cortex-ep-12345", "linux", "/etc/hosts"
            )
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_INPROGRESS

    def test_first_run_fallback_to_target_entity_ipaddress(
        self,
        mock_siemplify,
        sample_endpoint,
    ):
        mock_entity = mock.MagicMock()
        mock_entity.entity_type = "IP_ADDRESS"
        mock_entity.identifier = "10.0.0.15"
        mock_siemplify.target_entities = [mock_entity]

        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint
        mock_manager.initiate_file_retrieval.return_value = 5544

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return None
                if param_name == "File Path":
                    return "/etc/resolv.conf"
                if param_name == "Target OS":
                    return "linux"
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=True)

            mock_manager.initiate_file_retrieval.assert_called_once_with(
                "10.0.0.15", "linux", "/etc/resolv.conf"
            )
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_INPROGRESS

    def test_first_run_missing_endpoint_id_and_no_target_entities(
        self,
        mock_siemplify,
    ):
        mock_siemplify.target_entities = []
        mock_manager = mock.MagicMock()

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return None
                if param_name == "File Path":
                    return "/etc/hosts"
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=True)

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "Endpoint ID was not provided" in msg

    def test_first_run_missing_endpoint_id_multiple_target_entities(
        self,
        mock_siemplify,
    ):
        e1 = mock.MagicMock()
        e1.entity_type = "HOSTNAME"
        e1.identifier = "host-1"
        e2 = mock.MagicMock()
        e2.entity_type = "HOSTNAME"
        e2.identifier = "host-2"
        mock_siemplify.target_entities = [e1, e2]
        mock_manager = mock.MagicMock()

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return None
                if param_name == "File Path":
                    return "/etc/hosts"
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=True)

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "Found 2 suitable target entities" in msg

    def test_first_run_endpoint_not_found_on_os_lookup(
        self,
        mock_siemplify,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.side_effect = CortexXDRNotFoundError(
            "Endpoint cortex-ep-999 not found"
        )

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return "cortex-ep-999"
                if param_name == "File Path":
                    return "/etc/hosts"
                if param_name == "Target OS":
                    return None
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=True)

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "Endpoint cortex-ep-999 not found" in msg

    def test_first_run_initiate_file_retrieval_validation_error(
        self,
        mock_siemplify,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.initiate_file_retrieval.side_effect = CortexXDRValidationError(
            "Path is not a valid escaped full path"
        )

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return "cortex-ep-12345"
                if param_name == "File Path":
                    return "invalid_relative_path"
                if param_name == "Target OS":
                    return "windows"
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=True)

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "Path is not a valid escaped full path" in msg

    def test_first_run_initiate_file_retrieval_auth_error(
        self,
        mock_siemplify,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.initiate_file_retrieval.side_effect = CortexXDRAuthError(
            "Invalid authorization credentials"
        )

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return "cortex-ep-12345"
                if param_name == "File Path":
                    return "/etc/hosts"
                if param_name == "Target OS":
                    return "linux"
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=True)

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "Invalid authorization credentials" in msg

    def test_polling_run_in_progress(
        self,
        mock_siemplify,
    ):
        additional_data = {
            "group_action_id": 9988,
            "endpoint_id": "cortex-ep-12345",
            "file_path": "/etc/hosts",
            "started_at": time.time(),
        }
        mock_siemplify.parameters = {"additional_data": json.dumps(additional_data)}

        mock_manager = mock.MagicMock()
        mock_manager.get_action_status.return_value = ActionStatusData(
            action_id=9988,
            status="IN_PROGRESS",
            endpoint_statuses={"cortex-ep-12345": "IN_PROGRESS"},
        )

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Timeout Hours":
                    return 72
                if param_name == "additional_data":
                    return json.dumps(additional_data)
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=False)

            mock_manager.get_action_status.assert_called_once_with(9988)

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_INPROGRESS
            assert "File acquisition in progress: IN_PROGRESS" in msg
            parsed = json.loads(res)
            assert parsed["group_action_id"] == 9988

    @pytest.mark.parametrize("status_val", ["PENDING", "COMPLETED_PARTIAL", "PENDING_ABORT"])
    def test_polling_run_pending_statuses(
        self,
        status_val,
        mock_siemplify,
    ):
        additional_data = {
            "group_action_id": 9988,
            "endpoint_id": "cortex-ep-12345",
            "file_path": "/etc/hosts",
            "started_at": time.time(),
        }
        mock_siemplify.parameters = {"additional_data": json.dumps(additional_data)}

        mock_manager = mock.MagicMock()
        mock_manager.get_action_status.return_value = ActionStatusData(
            action_id=9988,
            status=status_val,
            endpoint_statuses={"cortex-ep-12345": status_val},
        )

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Timeout Hours":
                    return 72
                if param_name == "additional_data":
                    return json.dumps(additional_data)
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=False)

            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_INPROGRESS
            assert f"File acquisition in progress: {status_val}" in msg

    def test_polling_run_completed_successfully_download_and_hash(
        self,
        mock_siemplify,
    ):
        additional_data = {
            "group_action_id": 9988,
            "endpoint_id": "cortex-ep-12345",
            "file_path": r"C:\Windows\System32\drivers\etc\hosts",
            "started_at": time.time(),
        }
        mock_siemplify.parameters = {"additional_data": json.dumps(additional_data)}

        mock_manager = mock.MagicMock()
        mock_manager.get_action_status.return_value = ActionStatusData(
            action_id=9988,
            status="COMPLETED_SUCCESSFULLY",
            endpoint_statuses={"cortex-ep-12345": "COMPLETED_SUCCESSFULLY"},
        )
        mock_manager.get_file_retrieval_details.return_value = FileRetrievalDetails(
            action_id=9988,
            download_urls={"cortex-ep-12345": "https://api-gw.paloaltonetworks.com/download/file123"},
        )
        mock_manager.download_file_stream.return_value = (
            "/tmp/cortex_xdr_file_123.zip",
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            1024,
        )

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Timeout Hours":
                    return 72
                if param_name == "additional_data":
                    return json.dumps(additional_data)
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=False)

            mock_manager.get_action_status.assert_called_once_with(9988)
            mock_manager.get_file_retrieval_details.assert_called_once_with(9988)
            mock_manager.download_file_stream.assert_called_once_with(
                "https://api-gw.paloaltonetworks.com/download/file123"
            )

            mock_siemplify.result.add_result_json.assert_called_once()
            result_json = mock_siemplify.result.add_result_json.call_args[0][0]
            assert result_json["group_action_id"] == 9988
            assert result_json["endpoint_id"] == "cortex-ep-12345"
            assert result_json["file_path"] == r"C:\Windows\System32\drivers\etc\hosts"
            assert result_json["file_name"] == "hosts"
            assert result_json["sha256"] == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            assert result_json["file_size_bytes"] == 1024
            assert result_json["local_package_file"] == "/tmp/cortex_xdr_file_123.zip"
            assert result_json["download_url"] == "https://api-gw.paloaltonetworks.com/download/file123"
            assert result_json["status"] == "COMPLETED_SUCCESSFULLY"
            assert "downloaded_at" in result_json

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_COMPLETED
            assert res == "/tmp/cortex_xdr_file_123.zip"
            assert "Successfully acquired and downloaded file" in msg

    def test_polling_run_failed_missing_files(
        self,
        mock_siemplify,
    ):
        additional_data = {
            "group_action_id": 9988,
            "endpoint_id": "cortex-ep-12345",
            "file_path": r"C:\fake\missing_file.txt",
            "started_at": time.time(),
        }
        mock_siemplify.parameters = {"additional_data": json.dumps(additional_data)}

        mock_manager = mock.MagicMock()
        mock_manager.get_action_status.return_value = ActionStatusData(
            action_id=9988,
            status="FAILED",
            endpoint_statuses={"cortex-ep-12345": "FAILED"},
            error_reasons={"cortex-ep-12345": {"missing_files": [r"C:\fake\missing_file.txt"]}},
        )

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Timeout Hours":
                    return 72
                if param_name == "additional_data":
                    return json.dumps(additional_data)
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=False)

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert f"File not found on endpoint: {r'C:\fake\missing_file.txt'}" in msg

    def test_polling_run_failed_generic_error(
        self,
        mock_siemplify,
    ):
        additional_data = {
            "group_action_id": 9988,
            "endpoint_id": "cortex-ep-12345",
            "file_path": "/etc/shadow",
            "started_at": time.time(),
        }
        mock_siemplify.parameters = {"additional_data": json.dumps(additional_data)}

        mock_manager = mock.MagicMock()
        mock_manager.get_action_status.return_value = ActionStatusData(
            action_id=9988,
            status="FAILED",
            endpoint_statuses={"cortex-ep-12345": "FAILED"},
            error_reasons={"cortex-ep-12345": "Endpoint connection lost"},
        )

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Timeout Hours":
                    return 72
                if param_name == "additional_data":
                    return json.dumps(additional_data)
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=False)

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "Endpoint connection lost" in msg

    def test_polling_run_timeout_exceeded(
        self,
        mock_siemplify,
    ):
        started_at = time.time() - (73 * 3600)
        additional_data = {
            "group_action_id": 9988,
            "endpoint_id": "cortex-ep-12345",
            "file_path": "/etc/hosts",
            "started_at": started_at,
        }
        mock_siemplify.parameters = {"additional_data": json.dumps(additional_data)}

        mock_manager = mock.MagicMock()

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Timeout Hours":
                    return 72
                if param_name == "additional_data":
                    return json.dumps(additional_data)
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=False)

            mock_manager.get_action_status.assert_not_called()
            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "timed out" in msg.lower()

    def test_polling_run_get_action_status_api_error(
        self,
        mock_siemplify,
    ):
        additional_data = {
            "group_action_id": 9988,
            "endpoint_id": "cortex-ep-12345",
            "file_path": "/etc/hosts",
            "started_at": time.time(),
        }
        mock_siemplify.parameters = {"additional_data": json.dumps(additional_data)}

        mock_manager = mock.MagicMock()
        mock_manager.get_action_status.side_effect = CortexXDRActionError("Cortex API 500 Server Error")

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Timeout Hours":
                    return 72
                if param_name == "additional_data":
                    return json.dumps(additional_data)
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=False)

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "Cortex API 500 Server Error" in msg

    def test_polling_run_download_url_not_found(
        self,
        mock_siemplify,
    ):
        additional_data = {
            "group_action_id": 9988,
            "endpoint_id": "cortex-ep-12345",
            "file_path": "/etc/hosts",
            "started_at": time.time(),
        }
        mock_siemplify.parameters = {"additional_data": json.dumps(additional_data)}

        mock_manager = mock.MagicMock()
        mock_manager.get_action_status.return_value = ActionStatusData(
            action_id=9988,
            status="COMPLETED_SUCCESSFULLY",
            endpoint_statuses={"cortex-ep-12345": "COMPLETED_SUCCESSFULLY"},
        )
        mock_manager.get_file_retrieval_details.return_value = FileRetrievalDetails(
            action_id=9988,
            download_urls={},
        )

        with mock.patch.object(AcquireFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(AcquireFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(AcquireFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Timeout Hours":
                    return 72
                if param_name == "additional_data":
                    return json.dumps(additional_data)
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            AcquireFile.main(is_first_run=False)

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"

    def test_get_manager_config_extraction(
        self,
        mock_siemplify,
    ):
        with mock.patch.object(AcquireFile, "extract_configuration_param") as mock_extract_conf, \
             mock.patch.object(AcquireFile, "CortexXDRResponseManager") as mock_manager_cls:

            def fake_extract_conf(siemplify, provider_name, param_name, **kwargs):
                if param_name == "Api Root":
                    return "https://api-gw.paloaltonetworks.com"
                if param_name == "Api Key ID":
                    return "123"
                if param_name == "Api Key":
                    return "secret-token"
                if param_name == "Verify SSL":
                    return False
                return kwargs.get("default_value")

            mock_extract_conf.side_effect = fake_extract_conf

            mgr = AcquireFile.get_manager(mock_siemplify)

            mock_manager_cls.assert_called_once_with(
                api_root="https://api-gw.paloaltonetworks.com",
                api_key_id="123",
                api_key="secret-token",
                verify_ssl=False,
                siemplify_logger=mock_siemplify.LOGGER,
            )
            assert mgr == mock_manager_cls.return_value
