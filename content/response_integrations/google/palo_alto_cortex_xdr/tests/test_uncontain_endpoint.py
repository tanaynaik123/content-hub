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

from ..actions import UncontainEndpoint
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
    siemplify.script_name = "Uncontain Endpoint"
    siemplify.execution_deadline_unix_time_ms = 0
    siemplify.target_entities = []
    siemplify.parameters = {}
    siemplify.LOGGER = mock.MagicMock()
    siemplify.result = mock.MagicMock()
    siemplify.result.additional_data = None
    siemplify.end = mock.MagicMock()
    return siemplify


@pytest.fixture
def sample_isolated_endpoint():
    return EndpointData(
        endpoint_id="cortex-endpoint-101",
        endpoint_name="WORKSTATION-01",
        os_type="windows",
        is_isolated="AGENT_ISOLATED",
        ip_addresses=["10.0.0.15"],
        endpoint_status="CONNECTED",
        raw_data={
            "endpoint_id": "cortex-endpoint-101",
            "endpoint_name": "WORKSTATION-01",
            "os_type": "windows",
            "is_isolated": "AGENT_ISOLATED",
            "ip": ["10.0.0.15"],
            "endpoint_status": "CONNECTED",
        },
    )


@pytest.fixture
def sample_unisolated_endpoint():
    return EndpointData(
        endpoint_id="cortex-endpoint-101",
        endpoint_name="WORKSTATION-01",
        os_type="windows",
        is_isolated="AGENT_UNISOLATED",
        ip_addresses=["10.0.0.15"],
        endpoint_status="CONNECTED",
        raw_data={
            "endpoint_id": "cortex-endpoint-101",
            "endpoint_name": "WORKSTATION-01",
            "os_type": "windows",
            "is_isolated": "AGENT_UNISOLATED",
            "ip": ["10.0.0.15"],
            "endpoint_status": "CONNECTED",
        },
    )


class TestUncontainEndpointAction:
    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_sync_uncontain_success(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
        sample_isolated_endpoint,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_isolated_endpoint
        mock_manager.unisolate_endpoint.return_value = 12346
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-endpoint-101"
            if param_name == "Wait for Confirmation":
                return False
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=True)

        mock_manager.get_endpoint_by_id.assert_called_once_with("cortex-endpoint-101")
        mock_manager.unisolate_endpoint.assert_called_once_with("cortex-endpoint-101")

        mock_siemplify.result.add_result_json.assert_called_once()
        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        assert "operation_results" in result_json
        assert "cortex-endpoint-101" in result_json["operation_results"]
        op_res = result_json["operation_results"]["cortex-endpoint-101"]
        assert op_res["operation"] == "uncontain"
        assert op_res["result"] == "success"
        assert op_res["status"] == "uncontainment_requested"
        assert op_res["action_id"] == 12346
        assert op_res["reason"] is None
        assert result_json["device_metadata"]["endpoint_id"] == "cortex-endpoint-101"

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "Successfully requested uncontainment" in args[0]
        assert args[1] == "true" or args[1] is True
        assert args[2] == EXECUTION_STATE_COMPLETED

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_async_first_run_initiate_uncontainment(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
        sample_isolated_endpoint,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_isolated_endpoint
        mock_manager.unisolate_endpoint.return_value = 12346
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-endpoint-101"
            if param_name == "Wait for Confirmation":
                return True
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=True)

        mock_manager.get_endpoint_by_id.assert_called_once_with("cortex-endpoint-101")
        mock_manager.unisolate_endpoint.assert_called_once_with("cortex-endpoint-101")

        assert mock_siemplify.result.additional_data is not None
        add_data = json.loads(mock_siemplify.result.additional_data)
        assert add_data["action_id"] == 12346
        assert add_data["endpoint_id"] == "cortex-endpoint-101"
        assert "started_at" in add_data

        mock_siemplify.result.add_result_json.assert_called_once()
        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-endpoint-101"]
        assert op_res["operation"] == "uncontain"
        assert op_res["result"] == "success"
        assert op_res["status"] == "uncontainment_requested"
        assert op_res["action_id"] == 12346

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "Waiting for" in args[0] or "initiated" in args[0]
        assert args[1] == "true" or args[1] is True
        assert args[2] == EXECUTION_STATE_INPROGRESS

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_async_polling_completed_successfully(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
        sample_unisolated_endpoint,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_status = ActionStatusData(
            action_id=12346,
            status="COMPLETED_SUCCESSFULLY",
            endpoint_statuses={"cortex-endpoint-101": "COMPLETED_SUCCESSFULLY"},
            error_reasons={},
        )
        mock_manager.get_action_status.return_value = mock_status
        mock_manager.get_endpoint_by_id.return_value = sample_unisolated_endpoint
        mock_get_manager.return_value = mock_manager

        additional_data_str = json.dumps({
            "action_id": 12346,
            "endpoint_id": "cortex-endpoint-101",
            "started_at": time.time(),
        })

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "additional_data":
                return additional_data_str
            if param_name == "Endpoint ID":
                return "cortex-endpoint-101"
            if param_name == "Wait for Confirmation":
                return True
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=False)

        mock_manager.get_action_status.assert_called_once_with(12346)
        mock_manager.get_endpoint_by_id.assert_called_once_with("cortex-endpoint-101")

        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-endpoint-101"]
        assert op_res["operation"] == "uncontain"
        assert op_res["result"] == "success"
        assert op_res["status"] == "uncontained"
        assert op_res["action_id"] == 12346
        assert result_json["device_metadata"]["is_isolated"] == "AGENT_UNISOLATED"

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "Successfully uncontained" in args[0]
        assert args[1] == "true" or args[1] is True
        assert args[2] == EXECUTION_STATE_COMPLETED

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_async_polling_still_in_progress(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_status = ActionStatusData(
            action_id=12346,
            status="IN_PROGRESS",
            endpoint_statuses={"cortex-endpoint-101": "IN_PROGRESS"},
            error_reasons={},
        )
        mock_manager.get_action_status.return_value = mock_status
        mock_get_manager.return_value = mock_manager

        additional_data_str = json.dumps({
            "action_id": 12346,
            "endpoint_id": "cortex-endpoint-101",
            "started_at": time.time(),
        })

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "additional_data":
                return additional_data_str
            if param_name == "Endpoint ID":
                return "cortex-endpoint-101"
            if param_name == "Wait for Confirmation":
                return True
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=False)

        mock_manager.get_action_status.assert_called_once_with(12346)

        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-endpoint-101"]
        assert op_res["result"] == "success"
        assert op_res["status"] == "uncontainment_requested"

        assert mock_siemplify.result.additional_data == additional_data_str

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "Waiting for uncontainment" in args[0]
        assert args[1] == "true" or args[1] is True
        assert args[2] == EXECUTION_STATE_INPROGRESS

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_async_polling_still_pending(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_status = ActionStatusData(
            action_id=12346,
            status="PENDING",
            endpoint_statuses={"cortex-endpoint-101": "PENDING"},
            error_reasons={},
        )
        mock_manager.get_action_status.return_value = mock_status
        mock_get_manager.return_value = mock_manager

        additional_data_str = json.dumps({
            "action_id": 12346,
            "endpoint_id": "cortex-endpoint-101",
            "started_at": time.time(),
        })

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "additional_data":
                return additional_data_str
            if param_name == "Endpoint ID":
                return "cortex-endpoint-101"
            if param_name == "Wait for Confirmation":
                return True
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=False)

        mock_manager.get_action_status.assert_called_once_with(12346)

        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-endpoint-101"]
        assert op_res["result"] == "success"
        assert op_res["status"] == "uncontainment_requested"

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert args[2] == EXECUTION_STATE_INPROGRESS

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_async_polling_action_failed(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_status = ActionStatusData(
            action_id=12346,
            status="FAILED",
            endpoint_statuses={"cortex-endpoint-101": "FAILED"},
            error_reasons={"cortex-endpoint-101": "Machine unreachable"},
        )
        mock_manager.get_action_status.return_value = mock_status
        mock_get_manager.return_value = mock_manager

        additional_data_str = json.dumps({
            "action_id": 12346,
            "endpoint_id": "cortex-endpoint-101",
            "started_at": time.time(),
        })

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "additional_data":
                return additional_data_str
            if param_name == "Endpoint ID":
                return "cortex-endpoint-101"
            if param_name == "Wait for Confirmation":
                return True
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=False)

        mock_manager.get_action_status.assert_called_once_with(12346)

        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-endpoint-101"]
        assert op_res["result"] == "failure"
        assert op_res["status"] == "failed"

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "failed" in args[0].lower()
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_async_polling_timeout_exceeded(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_get_manager.return_value = mock_manager

        started_at = time.time() - (20 * 60)
        additional_data_str = json.dumps({
            "action_id": 12346,
            "endpoint_id": "cortex-endpoint-101",
            "started_at": started_at,
        })

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "additional_data":
                return additional_data_str
            if param_name == "Endpoint ID":
                return "cortex-endpoint-101"
            if param_name == "Wait for Confirmation":
                return True
            if param_name == "Timeout Minutes":
                return 10
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=False)

        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-endpoint-101"]
        assert op_res["result"] == "failure"
        assert "timed out" in str(op_res["reason"]).lower()

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "timed out" in args[0].lower()
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_endpoint_not_found_404(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.side_effect = CortexXDRNotFoundError(
            "Endpoint with ID 'nonexistent' was not found"
        )
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "nonexistent"
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=True)

        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["nonexistent"]
        assert op_res["operation"] == "uncontain"
        assert op_res["result"] == "failure"
        assert op_res["status"] == "unknown"
        assert op_res["reason"] == "Could not find machine in Cortex XDR"

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert "not found" in args[0].lower() or "not able to find" in args[0].lower()
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_auth_error_401(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.side_effect = CortexXDRAuthError(
            "Cortex XDR authentication failed: Invalid authorization"
        )
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-endpoint-101"
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=True)

        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-endpoint-101"]
        assert op_res["result"] == "failure"
        assert op_res["status"] == "unknown"
        assert "authentication failed" in str(op_res["reason"]).lower()

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_unisolate_action_error(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
        sample_isolated_endpoint,
    ):
        mock_siemplify_cls.return_value = mock_siemplify
        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_isolated_endpoint
        mock_manager.unisolate_endpoint.side_effect = CortexXDRActionError(
            "Failed to unisolate endpoint: Server error 500"
        )
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            if param_name == "Endpoint ID":
                return "cortex-endpoint-101"
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=True)

        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        op_res = result_json["operation_results"]["cortex-endpoint-101"]
        assert op_res["result"] == "failure"
        assert op_res["status"] == "unknown"
        assert "Server error 500" in str(op_res["reason"])

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_fallback_to_target_entity_hostname(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
        sample_isolated_endpoint,
    ):
        mock_entity = mock.MagicMock()
        mock_entity.entity_type = "HOSTNAME"
        mock_entity.identifier = "host-from-entity"
        mock_siemplify.target_entities = [mock_entity]
        mock_siemplify_cls.return_value = mock_siemplify

        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_isolated_endpoint
        mock_manager.unisolate_endpoint.return_value = 12346
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=True)

        mock_manager.get_endpoint_by_id.assert_called_once_with("host-from-entity")
        mock_manager.unisolate_endpoint.assert_called_once_with("host-from-entity")
        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        assert "host-from-entity" in result_json["operation_results"]

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_fallback_to_target_entity_ipaddress(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
        sample_isolated_endpoint,
    ):
        mock_entity = mock.MagicMock()
        mock_entity.entity_type = "IPADDRESS"
        mock_entity.identifier = "10.0.0.15"
        mock_siemplify.target_entities = [mock_entity]
        mock_siemplify_cls.return_value = mock_siemplify

        mock_manager = mock.MagicMock()
        mock_manager.get_endpoint_by_id.return_value = sample_isolated_endpoint
        mock_manager.unisolate_endpoint.return_value = 12346
        mock_get_manager.return_value = mock_manager

        def fake_extract_action(siemplify, param_name, **kwargs):
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=True)

        mock_manager.get_endpoint_by_id.assert_called_once_with("10.0.0.15")
        mock_manager.unisolate_endpoint.assert_called_once_with("10.0.0.15")
        result_json = mock_siemplify.result.add_result_json.call_args[0][0]
        assert "10.0.0.15" in result_json["operation_results"]

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
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

        UncontainEndpoint.main(is_first_run=True)

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(UncontainEndpoint, "extract_action_param")
    @mock.patch.object(UncontainEndpoint, "get_manager")
    @mock.patch.object(UncontainEndpoint, "SiemplifyAction")
    def test_missing_endpoint_id_multiple_target_entities(
        self,
        mock_siemplify_cls,
        mock_get_manager,
        mock_extract_action_param,
        mock_siemplify,
    ):
        e1 = mock.MagicMock(entity_type="HOSTNAME", identifier="h1")
        e2 = mock.MagicMock(entity_type="HOSTNAME", identifier="h2")
        mock_siemplify.target_entities = [e1, e2]
        mock_siemplify_cls.return_value = mock_siemplify

        def fake_extract_action(siemplify, param_name, **kwargs):
            return kwargs.get("default_value")

        mock_extract_action_param.side_effect = fake_extract_action

        UncontainEndpoint.main(is_first_run=True)

        mock_siemplify.end.assert_called_once()
        args = mock_siemplify.end.call_args[0]
        assert args[1] == "false" or args[1] is False
        assert args[2] == EXECUTION_STATE_FAILED

    @mock.patch.object(UncontainEndpoint, "CortexXDRResponseManager")
    @mock.patch.object(UncontainEndpoint, "extract_configuration_param")
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
                "Api Key": "secret-key",
                "Verify SSL": False,
            }
            return mapping.get(param_name, kwargs.get("default_value"))

        mock_extract_config.side_effect = fake_extract_config

        mgr = UncontainEndpoint.get_manager(mock_siemplify)

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
            api_key="secret-key",
            verify_ssl=False,
            siemplify_logger=mock_siemplify.LOGGER,
        )
        assert mgr == mock_manager_cls.return_value
