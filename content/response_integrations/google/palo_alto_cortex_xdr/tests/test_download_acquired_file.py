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
from unittest import mock
import pytest

from ..actions import DownloadAcquiredFile
from ..core.datamodels import FileRetrievalDetails
from ..core.exceptions import (
    CortexXDRActionError,
    CortexXDRAuthError,
    CortexXDRException,
    CortexXDRNotFoundError,
    CortexXDRValidationError,
)

EXECUTION_STATE_COMPLETED = 0
EXECUTION_STATE_FAILED = 1


@pytest.fixture
def mock_siemplify():
    siemplify = mock.MagicMock()
    siemplify.script_name = "Download Acquired File"
    siemplify.target_entities = []
    siemplify.parameters = {}
    siemplify.LOGGER = mock.MagicMock()
    siemplify.result = mock.MagicMock()
    siemplify.end = mock.MagicMock()
    return siemplify


class TestDownloadAcquiredFileAction:
    def test_download_acquired_file_success(
        self,
        mock_siemplify,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_file_retrieval_details.return_value = FileRetrievalDetails(
            action_id=9988,
            download_urls={"cortex-ep-12345": "https://api-gw.paloaltonetworks.com/download/9988"},
        )
        mock_manager.download_file_stream.return_value = (
            "/tmp/cortex_xdr_file_9988.zip",
            "abc123sha256hash",
            2048,
        )

        with mock.patch.object(DownloadAcquiredFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(DownloadAcquiredFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(DownloadAcquiredFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Group Action ID":
                    return "9988"
                if param_name == "Endpoint ID":
                    return "cortex-ep-12345"
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            DownloadAcquiredFile.main()

            mock_manager.get_file_retrieval_details.assert_called_once_with(9988)
            mock_manager.download_file_stream.assert_called_once_with(
                "https://api-gw.paloaltonetworks.com/download/9988"
            )

            mock_siemplify.result.add_result_json.assert_called_once()
            result_json = mock_siemplify.result.add_result_json.call_args[0][0]
            assert result_json["sha256"] == "abc123sha256hash"
            assert result_json["local_package_file"] == "/tmp/cortex_xdr_file_9988.zip"
            assert result_json["bytes_written"] == 2048
            assert result_json["download_url"] == "https://api-gw.paloaltonetworks.com/download/9988"
            assert "downloaded_at" in result_json

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_COMPLETED
            assert res == "/tmp/cortex_xdr_file_9988.zip"
            assert "Successfully downloaded" in msg

    def test_download_acquired_file_entity_fallback_hostname(
        self,
        mock_siemplify,
    ):
        mock_entity = mock.MagicMock()
        mock_entity.entity_type = "HOSTNAME"
        mock_entity.identifier = "host-99"
        mock_siemplify.target_entities = [mock_entity]

        mock_manager = mock.MagicMock()
        mock_manager.get_file_retrieval_details.return_value = FileRetrievalDetails(
            action_id=1234,
            download_urls={"host-99": "https://api-gw.paloaltonetworks.com/download/1234"},
        )
        mock_manager.download_file_stream.return_value = (
            "/tmp/cortex_xdr_file_1234.zip",
            "sha256-hash-99",
            512,
        )

        with mock.patch.object(DownloadAcquiredFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(DownloadAcquiredFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(DownloadAcquiredFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Group Action ID":
                    return "1234"
                if param_name == "Endpoint ID":
                    return None
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            DownloadAcquiredFile.main()

            mock_manager.download_file_stream.assert_called_once_with(
                "https://api-gw.paloaltonetworks.com/download/1234"
            )
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_COMPLETED
            assert res == "/tmp/cortex_xdr_file_1234.zip"

    def test_download_acquired_file_entity_fallback_ipaddress(
        self,
        mock_siemplify,
    ):
        mock_entity = mock.MagicMock()
        mock_entity.entity_type = "IP_ADDRESS"
        mock_entity.identifier = "10.1.1.1"
        mock_siemplify.target_entities = [mock_entity]

        mock_manager = mock.MagicMock()
        mock_manager.get_file_retrieval_details.return_value = FileRetrievalDetails(
            action_id=5678,
            download_urls={"10.1.1.1": "https://api-gw.paloaltonetworks.com/download/5678"},
        )
        mock_manager.download_file_stream.return_value = (
            "/tmp/cortex_xdr_file_5678.zip",
            "sha256-hash-ip",
            1024,
        )

        with mock.patch.object(DownloadAcquiredFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(DownloadAcquiredFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(DownloadAcquiredFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Group Action ID":
                    return "5678"
                if param_name == "Endpoint ID":
                    return None
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            DownloadAcquiredFile.main()

            mock_manager.download_file_stream.assert_called_once_with(
                "https://api-gw.paloaltonetworks.com/download/5678"
            )
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_COMPLETED
            assert res == "/tmp/cortex_xdr_file_5678.zip"

    def test_download_acquired_file_missing_endpoint_id_and_no_entities(
        self,
        mock_siemplify,
    ):
        mock_siemplify.target_entities = []
        mock_manager = mock.MagicMock()

        with mock.patch.object(DownloadAcquiredFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(DownloadAcquiredFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(DownloadAcquiredFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Group Action ID":
                    return "9988"
                if param_name == "Endpoint ID":
                    return None
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            DownloadAcquiredFile.main()

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "Endpoint ID was not provided" in msg

    def test_download_acquired_file_missing_endpoint_id_multiple_entities(
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

        with mock.patch.object(DownloadAcquiredFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(DownloadAcquiredFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(DownloadAcquiredFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Group Action ID":
                    return "9988"
                if param_name == "Endpoint ID":
                    return None
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            DownloadAcquiredFile.main()

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "Found 2 suitable target entities" in msg

    def test_download_acquired_file_missing_download_url(
        self,
        mock_siemplify,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_file_retrieval_details.return_value = FileRetrievalDetails(
            action_id=9988,
            download_urls={},
        )

        with mock.patch.object(DownloadAcquiredFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(DownloadAcquiredFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(DownloadAcquiredFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Group Action ID":
                    return "9988"
                if param_name == "Endpoint ID":
                    return "cortex-ep-12345"
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            DownloadAcquiredFile.main()

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "not found" in msg.lower()

    def test_download_acquired_file_not_found_404(
        self,
        mock_siemplify,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_file_retrieval_details.side_effect = CortexXDRNotFoundError(
            "File retrieval details for action ID 9988 not found."
        )

        with mock.patch.object(DownloadAcquiredFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(DownloadAcquiredFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(DownloadAcquiredFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Group Action ID":
                    return "9988"
                if param_name == "Endpoint ID":
                    return "cortex-ep-12345"
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            DownloadAcquiredFile.main()

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "File retrieval details for action ID 9988 not found." in msg

    def test_download_acquired_file_download_stream_error(
        self,
        mock_siemplify,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_file_retrieval_details.return_value = FileRetrievalDetails(
            action_id=9988,
            download_urls={"cortex-ep-12345": "https://api-gw.paloaltonetworks.com/download/9988"},
        )
        mock_manager.download_file_stream.side_effect = CortexXDRActionError(
            "Failed to stream download file: Connection aborted"
        )

        with mock.patch.object(DownloadAcquiredFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(DownloadAcquiredFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(DownloadAcquiredFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Group Action ID":
                    return "9988"
                if param_name == "Endpoint ID":
                    return "cortex-ep-12345"
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            DownloadAcquiredFile.main()

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "Failed to stream download file" in msg

    def test_download_acquired_file_auth_error(
        self,
        mock_siemplify,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_file_retrieval_details.side_effect = CortexXDRAuthError(
            "Invalid authorization"
        )

        with mock.patch.object(DownloadAcquiredFile, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(DownloadAcquiredFile, "extract_action_param") as mock_extract_action, \
             mock.patch.object(DownloadAcquiredFile, "get_manager", return_value=mock_manager):

            def fake_extract_action(siemplify, param_name, **kwargs):
                if param_name == "Group Action ID":
                    return "9988"
                if param_name == "Endpoint ID":
                    return "cortex-ep-12345"
                return kwargs.get("default_value")

            mock_extract_action.side_effect = fake_extract_action

            DownloadAcquiredFile.main()

            mock_siemplify.end.assert_called_once()
            msg, res, status = mock_siemplify.end.call_args[0]
            assert status == EXECUTION_STATE_FAILED
            assert res == "false"
            assert "Invalid authorization" in msg

    def test_get_manager_config_extraction(
        self,
        mock_siemplify,
    ):
        with mock.patch.object(DownloadAcquiredFile, "extract_configuration_param") as mock_extract_conf, \
             mock.patch.object(DownloadAcquiredFile, "CortexXDRResponseManager") as mock_manager_cls:

            def fake_extract_conf(siemplify, provider_name, param_name, **kwargs):
                if param_name == "Api Root":
                    return "https://api-gw.paloaltonetworks.com"
                if param_name == "Api Key ID":
                    return "456"
                if param_name == "Api Key":
                    return "secret-token-xyz"
                if param_name == "Verify SSL":
                    return True
                return kwargs.get("default_value")

            mock_extract_conf.side_effect = fake_extract_conf

            mgr = DownloadAcquiredFile.get_manager(mock_siemplify)

            mock_manager_cls.assert_called_once_with(
                api_root="https://api-gw.paloaltonetworks.com",
                api_key_id="456",
                api_key="secret-token-xyz",
                verify_ssl=True,
                siemplify_logger=mock_siemplify.LOGGER,
            )
            assert mgr == mock_manager_cls.return_value
