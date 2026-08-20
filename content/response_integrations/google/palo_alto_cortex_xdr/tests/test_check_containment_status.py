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

from ..actions import CheckContainmentStatus
from ..core.datamodels import EndpointData
from ..core.exceptions import (
    CortexXDRActionError,
    CortexXDRAuthError,
    CortexXDRException,
    CortexXDRNotFoundError,
)

EXECUTION_STATE_COMPLETED = 0
EXECUTION_STATE_FAILED = 1


@pytest.fixture
def mock_siemplify():
    siemplify = mock.MagicMock()
    siemplify.script_name = "Check Containment Status"
    siemplify.target_entities = []
    siemplify.LOGGER = mock.MagicMock()
    siemplify.result = mock.MagicMock()
    siemplify.end = mock.MagicMock()
    return siemplify


@pytest.fixture
def sample_endpoint_isolated():
    return EndpointData(
        endpoint_id="ep-101",
        endpoint_name="WORKSTATION-01",
        os_type="windows",
        is_isolated="AGENT_ISOLATED",
        ip_addresses=["10.0.0.15"],
        endpoint_status="CONNECTED",
        raw_data={
            "endpoint_id": "ep-101",
            "endpoint_name": "WORKSTATION-01",
            "os_type": "windows",
            "is_isolated": "AGENT_ISOLATED",
            "ip": ["10.0.0.15"],
            "endpoint_status": "CONNECTED",
        },
    )


@pytest.fixture
def sample_endpoint_unisolated():
    return EndpointData(
        endpoint_id="ep-102",
        endpoint_name="LAPTOP-DEV",
        os_type="linux",
        is_isolated="AGENT_UNISOLATED",
        ip_addresses=["192.168.1.20"],
        endpoint_status="CONNECTED",
        raw_data={
            "endpoint_id": "ep-102",
            "endpoint_name": "LAPTOP-DEV",
            "os_type": "linux",
            "is_isolated": "AGENT_UNISOLATED",
            "ip": ["192.168.1.20"],
            "endpoint_status": "CONNECTED",
        },
    )


@pytest.fixture
def sample_endpoint_pending_isolation():
    return EndpointData(
        endpoint_id="ep-103",
        endpoint_name="SERVER-SQL",
        os_type="windows",
        is_isolated="AGENT_PENDING_ISOLATION",
        ip_addresses=["10.0.0.50"],
        endpoint_status="CONNECTED",
        raw_data={
            "endpoint_id": "ep-103",
            "endpoint_name": "SERVER-SQL",
            "os_type": "windows",
            "is_isolated": "AGENT_PENDING_ISOLATION",
            "ip": ["10.0.0.50"],
            "endpoint_status": "CONNECTED",
        },
    )


@pytest.fixture
def sample_endpoint_pending_unisolation():
    return EndpointData(
        endpoint_id="ep-104",
        endpoint_name="MACBOOK-PRO",
        os_type="macos",
        is_isolated="AGENT_PENDING_UNISOLATION",
        ip_addresses=["10.0.0.99"],
        endpoint_status="CONNECTED",
        raw_data={
            "endpoint_id": "ep-104",
            "endpoint_name": "MACBOOK-PRO",
            "os_type": "macos",
            "is_isolated": "AGENT_PENDING_UNISOLATION",
            "ip": ["10.0.0.99"],
            "endpoint_status": "CONNECTED",
        },
    )


class TestCheckContainmentStatusAction:
    def test_check_containment_status_isolated(
        self,
        mock_siemplify,
        sample_endpoint_isolated,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint_isolated
        mock_manager.get_containment_status.return_value = "contained"

        with mock.patch.object(CheckContainmentStatus, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(CheckContainmentStatus, "get_manager", return_value=mock_manager), \
             mock.patch.object(CheckContainmentStatus, "extract_action_param") as mock_extract:

            def fake_extract(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return "ep-101"
                return kwargs.get("default_value")

            mock_extract.side_effect = fake_extract

            CheckContainmentStatus.main()

            mock_manager.get_endpoint_by_id.assert_called_once_with("ep-101")
            mock_manager.get_containment_status.assert_called_once_with("ep-101")

            mock_siemplify.result.add_result_json.assert_called_once()
            result_json = mock_siemplify.result.add_result_json.call_args[0][0]
            assert "endpoint_containment_status" in result_json
            assert "ep-101" in result_json["endpoint_containment_status"]
            status_obj = result_json["endpoint_containment_status"]["ep-101"]
            assert status_obj["status"] == "contained"
            assert status_obj["raw_status"] == "AGENT_ISOLATED"
            assert status_obj["reason"] is None
            assert status_obj["endpoint_details"]["endpoint_id"] == "ep-101"
            assert status_obj["endpoint_details"]["endpoint_name"] == "WORKSTATION-01"
            assert status_obj["endpoint_details"]["os_type"] == "windows"
            assert status_obj["endpoint_details"]["is_isolated"] == "AGENT_ISOLATED"

            mock_siemplify.end.assert_called_once()
            args = mock_siemplify.end.call_args[0]
            assert "Containment status of endpoint ep-101 is: contained" in args[0]
            assert args[1] == "true"
            assert args[2] == EXECUTION_STATE_COMPLETED

    def test_check_containment_status_unisolated(
        self,
        mock_siemplify,
        sample_endpoint_unisolated,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint_unisolated
        mock_manager.get_containment_status.return_value = "uncontained"

        with mock.patch.object(CheckContainmentStatus, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(CheckContainmentStatus, "get_manager", return_value=mock_manager), \
             mock.patch.object(CheckContainmentStatus, "extract_action_param") as mock_extract:

            def fake_extract(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return "ep-102"
                return kwargs.get("default_value")

            mock_extract.side_effect = fake_extract

            CheckContainmentStatus.main()

            mock_manager.get_endpoint_by_id.assert_called_once_with("ep-102")
            mock_manager.get_containment_status.assert_called_once_with("ep-102")

            result_json = mock_siemplify.result.add_result_json.call_args[0][0]
            status_obj = result_json["endpoint_containment_status"]["ep-102"]
            assert status_obj["status"] == "uncontained"
            assert status_obj["raw_status"] == "AGENT_UNISOLATED"
            assert status_obj["reason"] is None

            mock_siemplify.end.assert_called_once()
            args = mock_siemplify.end.call_args[0]
            assert "Containment status of endpoint ep-102 is: uncontained" in args[0]
            assert args[1] == "true"
            assert args[2] == EXECUTION_STATE_COMPLETED

    def test_check_containment_status_pending_isolation(
        self,
        mock_siemplify,
        sample_endpoint_pending_isolation,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint_pending_isolation
        mock_manager.get_containment_status.return_value = "containment_requested"

        with mock.patch.object(CheckContainmentStatus, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(CheckContainmentStatus, "get_manager", return_value=mock_manager), \
             mock.patch.object(CheckContainmentStatus, "extract_action_param") as mock_extract:

            def fake_extract(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return "ep-103"
                return kwargs.get("default_value")

            mock_extract.side_effect = fake_extract

            CheckContainmentStatus.main()

            result_json = mock_siemplify.result.add_result_json.call_args[0][0]
            status_obj = result_json["endpoint_containment_status"]["ep-103"]
            assert status_obj["status"] == "containment_requested"
            assert status_obj["raw_status"] == "AGENT_PENDING_ISOLATION"
            assert status_obj["reason"] is None

            mock_siemplify.end.assert_called_once()
            args = mock_siemplify.end.call_args[0]
            assert "Containment status of endpoint ep-103 is: containment_requested" in args[0]
            assert args[1] == "true"
            assert args[2] == EXECUTION_STATE_COMPLETED

    def test_check_containment_status_pending_unisolation(
        self,
        mock_siemplify,
        sample_endpoint_pending_unisolation,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint_pending_unisolation
        mock_manager.get_containment_status.return_value = "uncontainment_requested"

        with mock.patch.object(CheckContainmentStatus, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(CheckContainmentStatus, "get_manager", return_value=mock_manager), \
             mock.patch.object(CheckContainmentStatus, "extract_action_param") as mock_extract:

            def fake_extract(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return "ep-104"
                return kwargs.get("default_value")

            mock_extract.side_effect = fake_extract

            CheckContainmentStatus.main()

            result_json = mock_siemplify.result.add_result_json.call_args[0][0]
            status_obj = result_json["endpoint_containment_status"]["ep-104"]
            assert status_obj["status"] == "uncontainment_requested"
            assert status_obj["raw_status"] == "AGENT_PENDING_UNISOLATION"
            assert status_obj["reason"] is None

            mock_siemplify.end.assert_called_once()
            args = mock_siemplify.end.call_args[0]
            assert "Containment status of endpoint ep-104 is: uncontainment_requested" in args[0]
            assert args[1] == "true"
            assert args[2] == EXECUTION_STATE_COMPLETED

    def test_check_containment_status_endpoint_not_found_404(
        self,
        mock_siemplify,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.side_effect = CortexXDRNotFoundError(
            "Endpoint with ID 'ep-404' was not found in Cortex XDR."
        )

        with mock.patch.object(CheckContainmentStatus, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(CheckContainmentStatus, "get_manager", return_value=mock_manager), \
             mock.patch.object(CheckContainmentStatus, "extract_action_param") as mock_extract:

            def fake_extract(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return "ep-404"
                return kwargs.get("default_value")

            mock_extract.side_effect = fake_extract

            CheckContainmentStatus.main()

            result_json = mock_siemplify.result.add_result_json.call_args[0][0]
            status_obj = result_json["endpoint_containment_status"]["ep-404"]
            assert status_obj["status"] == "unknown"
            assert status_obj["raw_status"] is None
            assert status_obj["reason"] == "Could not find machine in Cortex XDR"
            assert status_obj["endpoint_details"] is None

            mock_siemplify.end.assert_called_once()
            args = mock_siemplify.end.call_args[0]
            assert "Action was not able to find an endpoint with the given ID: ep-404" in args[0]
            assert args[1] == "false"
            assert args[2] == EXECUTION_STATE_FAILED

    def test_check_containment_status_auth_error(
        self,
        mock_siemplify,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.side_effect = CortexXDRAuthError(
            "Cortex XDR authentication failed: HTTP status 401"
        )

        with mock.patch.object(CheckContainmentStatus, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(CheckContainmentStatus, "get_manager", return_value=mock_manager), \
             mock.patch.object(CheckContainmentStatus, "extract_action_param") as mock_extract:

            def fake_extract(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return "ep-101"
                return kwargs.get("default_value")

            mock_extract.side_effect = fake_extract

            CheckContainmentStatus.main()

            result_json = mock_siemplify.result.add_result_json.call_args[0][0]
            status_obj = result_json["endpoint_containment_status"]["ep-101"]
            assert status_obj["status"] == "unknown"
            assert "authentication failed" in status_obj["reason"]
            assert status_obj["endpoint_details"] is None

            mock_siemplify.end.assert_called_once()
            args = mock_siemplify.end.call_args[0]
            assert "authentication failed" in args[0]
            assert args[1] == "false"
            assert args[2] == EXECUTION_STATE_FAILED

    def test_check_containment_status_generic_exception(
        self,
        mock_siemplify,
    ):
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.side_effect = Exception("Connection timeout")

        with mock.patch.object(CheckContainmentStatus, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(CheckContainmentStatus, "get_manager", return_value=mock_manager), \
             mock.patch.object(CheckContainmentStatus, "extract_action_param") as mock_extract:

            def fake_extract(siemplify, param_name, **kwargs):
                if param_name == "Endpoint ID":
                    return "ep-101"
                return kwargs.get("default_value")

            mock_extract.side_effect = fake_extract

            CheckContainmentStatus.main()

            result_json = mock_siemplify.result.add_result_json.call_args[0][0]
            status_obj = result_json["endpoint_containment_status"]["ep-101"]
            assert status_obj["status"] == "unknown"
            assert "Connection timeout" in status_obj["reason"]

            mock_siemplify.end.assert_called_once()
            args = mock_siemplify.end.call_args[0]
            assert "Connection timeout" in args[0]
            assert args[1] == "false"
            assert args[2] == EXECUTION_STATE_FAILED

    def test_check_containment_status_fallback_to_hostname_entity(
        self,
        mock_siemplify,
        sample_endpoint_isolated,
    ):
        mock_entity = mock.MagicMock()
        mock_entity.entity_type = "HOSTNAME"
        mock_entity.identifier = "HOST-ENTITY-01"
        mock_siemplify.target_entities = [mock_entity]

        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint_isolated
        mock_manager.get_containment_status.return_value = "contained"

        with mock.patch.object(CheckContainmentStatus, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(CheckContainmentStatus, "get_manager", return_value=mock_manager), \
             mock.patch.object(CheckContainmentStatus, "extract_action_param") as mock_extract:

            def fake_extract(siemplify, param_name, **kwargs):
                return kwargs.get("default_value")

            mock_extract.side_effect = fake_extract

            CheckContainmentStatus.main()

            mock_manager.get_endpoint_by_id.assert_called_once_with("HOST-ENTITY-01")
            result_json = mock_siemplify.result.add_result_json.call_args[0][0]
            assert "HOST-ENTITY-01" in result_json["endpoint_containment_status"]

    def test_check_containment_status_fallback_to_ipaddress_entity(
        self,
        mock_siemplify,
        sample_endpoint_isolated,
    ):
        mock_entity = mock.MagicMock()
        mock_entity.entity_type = "IPADDRESS"
        mock_entity.identifier = "10.0.0.15"
        mock_siemplify.target_entities = [mock_entity]

        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint_isolated
        mock_manager.get_containment_status.return_value = "contained"

        with mock.patch.object(CheckContainmentStatus, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(CheckContainmentStatus, "get_manager", return_value=mock_manager), \
             mock.patch.object(CheckContainmentStatus, "extract_action_param") as mock_extract:

            def fake_extract(siemplify, param_name, **kwargs):
                return kwargs.get("default_value")

            mock_extract.side_effect = fake_extract

            CheckContainmentStatus.main()

            mock_manager.get_endpoint_by_id.assert_called_once_with("10.0.0.15")
            result_json = mock_siemplify.result.add_result_json.call_args[0][0]
            assert "10.0.0.15" in result_json["endpoint_containment_status"]

    def test_check_containment_status_missing_endpoint_id_no_entities(
        self,
        mock_siemplify,
    ):
        mock_siemplify.target_entities = []

        with mock.patch.object(CheckContainmentStatus, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(CheckContainmentStatus, "get_manager", return_value=mock.MagicMock()), \
             mock.patch.object(CheckContainmentStatus, "extract_action_param") as mock_extract:

            def fake_extract(siemplify, param_name, **kwargs):
                return kwargs.get("default_value")

            mock_extract.side_effect = fake_extract

            CheckContainmentStatus.main()

            mock_siemplify.end.assert_called_once()
            args = mock_siemplify.end.call_args[0]
            assert args[1] == "false"
            assert args[2] == EXECUTION_STATE_FAILED

    def test_check_containment_status_missing_endpoint_id_multiple_entities(
        self,
        mock_siemplify,
    ):
        e1 = mock.MagicMock(entity_type="HOSTNAME", identifier="h1")
        e2 = mock.MagicMock(entity_type="HOSTNAME", identifier="h2")
        mock_siemplify.target_entities = [e1, e2]

        with mock.patch.object(CheckContainmentStatus, "SiemplifyAction", return_value=mock_siemplify), \
             mock.patch.object(CheckContainmentStatus, "get_manager", return_value=mock.MagicMock()), \
             mock.patch.object(CheckContainmentStatus, "extract_action_param") as mock_extract:

            def fake_extract(siemplify, param_name, **kwargs):
                return kwargs.get("default_value")

            mock_extract.side_effect = fake_extract

            CheckContainmentStatus.main()

            mock_siemplify.end.assert_called_once()
            args = mock_siemplify.end.call_args[0]
            assert args[1] == "false"
            assert args[2] == EXECUTION_STATE_FAILED

    def test_get_manager_config_extraction(
        self,
        mock_siemplify,
    ):
        with mock.patch.object(CheckContainmentStatus, "extract_configuration_param") as mock_extract_config, \
             mock.patch.object(CheckContainmentStatus, "CortexXDRResponseManager") as mock_manager_cls:

            def fake_extract_config(siemplify, provider_name, param_name, **kwargs):
                mapping = {
                    "Api Root": "https://api-xdr.paloaltonetworks.com",
                    "Api Key ID": "1001",
                    "Api Key": "secret-key-12345",
                    "Verify SSL": True,
                }
                return mapping.get(param_name, kwargs.get("default_value"))

            mock_extract_config.side_effect = fake_extract_config

            mgr = CheckContainmentStatus.get_manager(mock_siemplify)

            mock_extract_config.assert_any_call(
                mock_siemplify,
                provider_name="PaloAltoCortexXDR",
                param_name="Api Root",
                input_type=str,
                is_mandatory=True,
            )
            mock_extract_config.assert_any_call(
                mock_siemplify,
                provider_name="PaloAltoCortexXDR",
                param_name="Api Key ID",
                input_type=str,
                is_mandatory=True,
            )
            mock_extract_config.assert_any_call(
                mock_siemplify,
                provider_name="PaloAltoCortexXDR",
                param_name="Api Key",
                input_type=str,
                is_mandatory=True,
            )
            mock_extract_config.assert_any_call(
                mock_siemplify,
                provider_name="PaloAltoCortexXDR",
                param_name="Verify SSL",
                input_type=bool,
                is_mandatory=False,
                default_value=True,
            )

            mock_manager_cls.assert_called_once_with(
                api_root="https://api-xdr.paloaltonetworks.com",
                api_key_id="1001",
                api_key="secret-key-12345",
                verify_ssl=True,
                siemplify_logger=mock_siemplify.LOGGER,
            )
            assert mgr == mock_manager_cls.return_value
