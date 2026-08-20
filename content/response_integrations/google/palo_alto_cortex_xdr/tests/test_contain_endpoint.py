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

from ..actions import ContainEndpoint
from ..core.datamodels import ActionStatusData, EndpointData
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
    siemplify.script_name = "Contain Endpoint"
    siemplify.execution_deadline_unix_time_ms = 0
    siemplify.target_entities = []
    siemplify.parameters = {}
    siemplify.LOGGER = mock.MagicMock()
    siemplify.result = mock.MagicMock()
    siemplify.end = mock.MagicMock()
    return siemplify


@pytest.fixture
def sample_endpoint_connected():
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


@pytest.fixture
def sample_endpoint_isolated():
    return EndpointData(
        endpoint_id="cortex-ep-12345",
        endpoint_name="WORKSTATION-01",
        os_type="windows",
        is_isolated="AGENT_ISOLATED",
        ip_addresses=["10.0.0.15"],
        endpoint_status="CONNECTED",
        raw_data={
            "endpoint_id": "cortex-ep-12345",
            "endpoint_name": "WORKSTATION-01",
            "os_type": "windows",
            "is_isolated": "AGENT_ISOLATED",
            "ip": ["10.0.0.15"],
            "endpoint_status": "CONNECTED",
        },
    )


class TestContainEndpointAction:
    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_contain_endpoint_sync_success(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
        sample_endpoint_connected,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint_connected
        mock_manager.isolate_endpoint.return_value = 998877
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-ep-12345"
            if param_name == "Wait for Confirmation":
                return False
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=True)

        mock_manager.get_endpoint_by_id.assert_called_once_with("cortex-ep-12345")
        mock_manager.isolate_endpoint.assert_called_once_with("cortex-ep-12345")

        mock_siemplify.result.add_result_json.assert_called_once()
        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        assert "operation_results" in result_json
        assert "cortex-ep-12345" in result_json["operation_results"]
        op_res = result_json["operation_results"]["cortex-ep-12345"]
        assert op_res["operation"] == "contain"
        assert op_res["result"] == "success"
        assert op_res["status"] == "containment_requested"
        assert op_res["action_id"] == 998877
        assert op_res["reason"] is None
        assert result_json["device_metadata"]["endpoint_id"] == "cortex-ep-12345"

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "Successfully requested containment for endpoint cortex-ep-12345" in args[0]
        assert args[1] == "true" or args[1] is True
        assert args[2] == EXECUTION_STATE_COMPLETED

    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_contain_endpoint_async_first_run(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
        sample_endpoint_connected,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint_connected
        mock_manager.isolate_endpoint.return_value = 998877
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-ep-12345"
            if param_name == "Wait for Confirmation":
                return True
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=True)

        mock_manager.get_endpoint_by_id.assert_called_once_with("cortex-ep-12345")
        mock_manager.isolate_endpoint.assert_called_once_with("cortex-ep-12345")

        mock_siemplify.result.add_result_json.assert_called_once()
        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-ep-12345"]
        assert op_res["operation"] == "contain"
        assert op_res["result"] == "success"
        assert op_res["status"] == "containment_requested"
        assert op_res["action_id"] == 998877

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "Waiting for confirmation" in args[0] or "Containment requested" in args[0]
        assert args[2] == EXECUTION_STATE_INPROGRESS

    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_contain_endpoint_async_subsequent_run_in_progress(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        mock_siemplify.parameters = {
            "additional_data": json.dumps(
                {
                    "action_id": 998877,
                    "endpoint_id": "cortex-ep-12345",
                    "started_at": time.time(),
                    "timeout_minutes": 10,
                }
            )
        }
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_action_status.return_value = ActionStatusData(
            action_id=998877,
            status="IN_PROGRESS",
            endpoint_statuses={"cortex-ep-12345": "IN_PROGRESS"},
        )
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-ep-12345"
            if param_name == "Wait for Confirmation":
                return True
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=False)

        mock_manager.get_action_status.assert_called_once_with(998877)
        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert args[2] == EXECUTION_STATE_INPROGRESS

    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_contain_endpoint_async_subsequent_run_completed(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
        sample_endpoint_isolated,
    ):
        mock_siemplify.parameters = {
            "additional_data": json.dumps(
                {
                    "action_id": 998877,
                    "endpoint_id": "cortex-ep-12345",
                    "started_at": time.time(),
                    "timeout_minutes": 10,
                }
            )
        }
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_action_status.return_value = ActionStatusData(
            action_id=998877,
            status="COMPLETED_SUCCESSFULLY",
            endpoint_statuses={"cortex-ep-12345": "COMPLETED_SUCCESSFULLY"},
        )
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint_isolated
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-ep-12345"
            if param_name == "Wait for Confirmation":
                return True
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=False)

        mock_manager.get_action_status.assert_called_once_with(998877)
        mock_manager.get_endpoint_by_id.assert_called_once_with("cortex-ep-12345")

        mock_siemplify.result.add_result_json.assert_called_once()
        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-ep-12345"]
        assert op_res["operation"] == "contain"
        assert op_res["result"] == "success"
        assert op_res["status"] == "contained"
        assert op_res["action_id"] == 998877

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "Successfully confirmed containment for endpoint cortex-ep-12345" in args[0]
        assert args[1] == "true" or args[1] is True
        assert args[2] == EXECUTION_STATE_COMPLETED

    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_contain_endpoint_async_subsequent_run_failed(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        mock_siemplify.parameters = {
            "additional_data": json.dumps(
                {
                    "action_id": 998877,
                    "endpoint_id": "cortex-ep-12345",
                    "started_at": time.time(),
                    "timeout_minutes": 10,
                }
            )
        }
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_action_status.return_value = ActionStatusData(
            action_id=998877,
            status="FAILED",
            endpoint_statuses={"cortex-ep-12345": "FAILED"},
            error_reasons={"cortex-ep-12345": "Host rejected containment command"},
        )
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-ep-12345"
            if param_name == "Wait for Confirmation":
                return True
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=False)

        mock_manager.get_action_status.assert_called_once_with(998877)

        mock_siemplify.result.add_result_json.assert_called_once()
        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-ep-12345"]
        assert op_res["operation"] == "contain"
        assert op_res["result"] == "failure"
        assert op_res["status"] == "failed"

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "Containment failed for endpoint cortex-ep-12345" in args[0]
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_contain_endpoint_async_timeout(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        mock_siemplify.parameters = {
            "additional_data": json.dumps(
                {
                    "action_id": 998877,
                    "endpoint_id": "cortex-ep-12345",
                    "started_at": time.time() - 700,
                    "timeout_minutes": 10,
                }
            )
        }
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-ep-12345"
            if param_name == "Wait for Confirmation":
                return True
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=False)

        mock_siemplify.result.add_result_json.assert_called_once()
        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-ep-12345"]
        assert op_res["result"] == "failure"
        assert op_res["status"] == "timeout"
        assert "timed out" in op_res["reason"]

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "timed out" in args[0]
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_contain_endpoint_not_found_404(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.side_effect = CortexXDRNotFoundError(
            "Endpoint cortex-ep-nonexistent was not found in Cortex XDR."
        )
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-ep-nonexistent"
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=True)

        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-ep-nonexistent"]
        assert op_res["operation"] == "contain"
        assert op_res["result"] == "failure"
        assert op_res["status"] == "unknown"
        assert op_res["reason"] == "Could not find machine in Cortex XDR"

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "Could not find endpoint cortex-ep-nonexistent" in args[0] or "not found" in args[0]
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_contain_endpoint_isolate_api_error(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
        sample_endpoint_connected,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint_connected
        mock_manager.isolate_endpoint.side_effect = CortexXDRActionError("Failed to isolate host: Internal Server Error")
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-ep-12345"
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=True)

        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-ep-12345"]
        assert op_res["operation"] == "contain"
        assert op_res["result"] == "failure"
        assert op_res["status"] == "unknown"
        assert "Failed to isolate host" in op_res["reason"]

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_contain_endpoint_auth_error(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.side_effect = CortexXDRAuthError("Invalid authorization key")
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-ep-12345"
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=True)

        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-ep-12345"]
        assert op_res["result"] == "failure"
        assert op_res["status"] == "unknown"
        assert "Invalid authorization key" in op_res["reason"]

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_fallback_to_target_entity_hostname(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
        sample_endpoint_connected,
    ):
        mock_entity = mock.MagicMock()
        mock_entity.entity_type = "HOSTNAME"
        mock_entity.identifier = "host-from-entity"
        mock_siemplify.target_entities = [mock_entity]
        mock_siemplify_cls.return_value = mock_siemplify

        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint_connected
        mock_manager.isolate_endpoint.return_value = 112233
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=True)

        mock_manager.get_endpoint_by_id.assert_called_once_with("host-from-entity")
        mock_manager.isolate_endpoint.assert_called_once_with("host-from-entity")
        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        assert "host-from-entity" in result_json["operation_results"]

    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_fallback_to_target_entity_ipaddress(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
        sample_endpoint_connected,
    ):
        mock_entity = mock.MagicMock()
        mock_entity.entity_type = "IPADDRESS"
        mock_entity.identifier = "10.0.0.15"
        mock_siemplify.target_entities = [mock_entity]
        mock_siemplify_cls.return_value = mock_siemplify

        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_endpoint_connected
        mock_manager.isolate_endpoint.return_value = 112233
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=True)

        mock_manager.get_endpoint_by_id.assert_called_once_with("10.0.0.15")
        mock_manager.isolate_endpoint.assert_called_once_with("10.0.0.15")
        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        assert "10.0.0.15" in result_json["operation_results"]

    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_missing_endpoint_id_and_no_target_entities(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        mock_siemplify.target_entities = []
        mock_siemplify_cls.return_value = mock_siemplify

        def fake_extract_action(siemplify, param_name, **kwargs):
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=True)

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(ContainEndpoint, "extract_action_param")
    @mock.patch.object(ContainEndpoint, "get_manager")
    @mock.patch.object(ContainEndpoint, "SiemplifyAction")
    def test_missing_endpoint_id_multiple_target_entities(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        e1 = mock.MagicMock(entity_type="HOSTNAME", identifier="host1")
        e2 = mock.MagicMock(entity_type="HOSTNAME", identifier="host2")
        mock_siemplify.target_entities = [e1, e2]
        mock_siemplify_cls.return_value = mock_siemplify

        def fake_extract_action(siemplify, param_name, **kwargs):
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        ContainEndpoint.main(is_first_run=True)

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(ContainEndpoint, "CortexXDRResponseManager")
    @mock.patch.object(ContainEndpoint, "extract_configuration_param")
    def test_get_manager_config_extraction(
        self,
        mock_extract_config,
        mock_manager_cls,
        mock_siemplify,
    ):
        def fake_extract_config(siemplify, provider_name, param_name, **kwargs):
            mapping = {
                "Api Root": "https://api-gw.paloaltonetworks.com",
                "Api Key ID": "101",
                "Api Key": "secret-key-123",
                "Verify SSL": False,
            }
            return mapping.get(param_name, kwargs.get("default_value"))

        mock_extract_config.side_effect = fake_extract_config

        mgr = ContainEndpoint.get_manager(mock_siemplify)

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
            api_root="https://api-gw.paloaltonetworks.com",
            api_key_id="101",
            api_key="secret-key-123",
            verify_ssl=False,
            siemplify_logger=mock_siemplify.LOGGER,
        )
        assert mgr == mock_manager_cls.return_value
