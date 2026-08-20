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
import sys
import time
from typing import Any, Dict, Optional

try:
    from soar_sdk.SiemplifyAction import SiemplifyAction
    from soar_sdk.SiemplifyUtils import output_handler, unix_now
    from soar_sdk.ScriptResult import (
        EXECUTION_STATE_COMPLETED,
        EXECUTION_STATE_FAILED,
        EXECUTION_STATE_INPROGRESS,
        EXECUTION_STATE_TIMEDOUT,
    )
except ImportError:
    try:
        from SiemplifyAction import SiemplifyAction
        from SiemplifyUtils import output_handler, unix_now
        from ScriptResult import (
            EXECUTION_STATE_COMPLETED,
            EXECUTION_STATE_FAILED,
            EXECUTION_STATE_INPROGRESS,
            EXECUTION_STATE_TIMEDOUT,
        )
    except ImportError:
        class SiemplifyAction:
            def __init__(self, *args, **kwargs):
                self.script_name = ""
                self.parameters = {}
                self.target_entities = []
                self.result = None
                self.LOGGER = None
            def end(self, *args, **kwargs):
                pass
        def output_handler(func):
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        def unix_now():
            return int(time.time() * 1000)
        EXECUTION_STATE_COMPLETED = 0
        EXECUTION_STATE_FAILED = 1
        EXECUTION_STATE_INPROGRESS = 2
        EXECUTION_STATE_TIMEDOUT = 3

try:
    from TIPCommon import extract_action_param, extract_configuration_param
except ImportError:
    from TIPCommon.base.utils import extract_action_param, extract_configuration_param

try:
    from ..core.CortexXDRResponseManager import CortexXDRResponseManager
    from ..core.exceptions import (
        CortexXDRActionError,
        CortexXDRAuthError,
        CortexXDRException,
        CortexXDRNotFoundError,
        CortexXDRValidationError,
    )
except ImportError:
    from CortexXDRResponseManager import CortexXDRResponseManager
    from exceptions import (
        CortexXDRActionError,
        CortexXDRAuthError,
        CortexXDRException,
        CortexXDRNotFoundError,
        CortexXDRValidationError,
    )

PROVIDER_NAME = "PaloAltoCortexXDR"
SCRIPT_NAME = "Contain Endpoint"
SUPPORTED_ENTITY_TYPES = ["HOSTNAME", "IPADDRESS", "IP_ADDRESS"]


def get_manager(siemplify: SiemplifyAction) -> CortexXDRResponseManager:
    """
    Instantiate CortexXDRResponseManager using configuration parameters.

    :param siemplify: SiemplifyAction instance
    :return: CortexXDRResponseManager instance
    """
    api_root = extract_configuration_param(
        siemplify,
        provider_name=PROVIDER_NAME,
        param_name="Api Root",
        input_type=str,
        is_mandatory=True,
    )
    api_key_id = extract_configuration_param(
        siemplify,
        provider_name=PROVIDER_NAME,
        param_name="Api Key ID",
        input_type=str,
        is_mandatory=True,
    )
    api_key = extract_configuration_param(
        siemplify,
        provider_name=PROVIDER_NAME,
        param_name="Api Key",
        input_type=str,
        is_mandatory=True,
    )
    verify_ssl = extract_configuration_param(
        siemplify,
        provider_name=PROVIDER_NAME,
        param_name="Verify SSL",
        input_type=bool,
        is_mandatory=False,
        default_value=True,
    )
    return CortexXDRResponseManager(
        api_root=api_root,
        api_key_id=api_key_id,
        api_key=api_key,
        verify_ssl=verify_ssl,
        siemplify_logger=getattr(siemplify, "LOGGER", None),
    )


@output_handler
def main(is_first_run: bool = True):
    siemplify = SiemplifyAction()
    siemplify.script_name = SCRIPT_NAME

    mode = "Main" if is_first_run else "QueryState"
    siemplify.LOGGER.info(f"----------------- {mode} - Starting -----------------")

    endpoint_id = extract_action_param(
        siemplify,
        param_name="Endpoint ID",
        input_type=str,
        is_mandatory=False,
        default_value=None,
    )
    wait_for_confirmation = extract_action_param(
        siemplify,
        param_name="Wait for Confirmation",
        input_type=bool,
        is_mandatory=False,
        default_value=False,
    )
    timeout_minutes = extract_action_param(
        siemplify,
        param_name="Timeout Minutes",
        input_type=int,
        is_mandatory=False,
        default_value=10,
    )

    json_result: Dict[str, Any] = {
        "operation_results": {},
        "device_metadata": {},
    }
    action_status = EXECUTION_STATE_FAILED
    result_value: Any = "false"
    output_message = ""

    try:
        if not endpoint_id:
            suitable_entities = [
                entity
                for entity in getattr(siemplify, "target_entities", [])
                if str(getattr(entity, "entity_type", "")).upper() in SUPPORTED_ENTITY_TYPES
            ]
            if len(suitable_entities) == 1:
                entity = suitable_entities[0]
                endpoint_id = (
                    getattr(entity, "identifier", None)
                    or getattr(entity, "original_identifier", None)
                    or str(entity)
                )
            else:
                raise ValueError(
                    "If not passing in an endpoint id, your case/alert needs to be associated "
                    f"with exactly one target entity (HOSTNAME or IPADDRESS). Found {len(suitable_entities)} valid entities."
                )

        json_result["operation_results"][endpoint_id] = {
            "operation": "contain",
            "result": None,
            "status": None,
            "action_id": None,
            "reason": None,
        }

        manager = get_manager(siemplify)

        if not wait_for_confirmation:
            # Mode A: Fast Synchronous Execution
            siemplify.LOGGER.info(f"Fetching endpoint metadata for ID: {endpoint_id}")
            endpoint_data = manager.get_endpoint_by_id(endpoint_id)
            json_result["device_metadata"] = (
                endpoint_data.to_json()
                if hasattr(endpoint_data, "to_json")
                else endpoint_data.__dict__
            )

            siemplify.LOGGER.info(f"Requesting containment for endpoint ID: {endpoint_id}")
            action_id = manager.isolate_endpoint(endpoint_id)

            json_result["operation_results"][endpoint_id] = {
                "operation": "contain",
                "result": "success",
                "status": "containment_requested",
                "action_id": action_id,
                "reason": None,
            }
            action_status = EXECUTION_STATE_COMPLETED
            result_value = "true"
            output_message = (
                f"Successfully requested containment for endpoint {endpoint_id} in Cortex XDR."
            )
            siemplify.LOGGER.info(output_message)

        else:
            # Mode B: Asynchronous Polling Execution
            if is_first_run:
                siemplify.LOGGER.info(f"Fetching endpoint metadata for ID: {endpoint_id}")
                endpoint_data = manager.get_endpoint_by_id(endpoint_id)
                json_result["device_metadata"] = (
                    endpoint_data.to_json()
                    if hasattr(endpoint_data, "to_json")
                    else endpoint_data.__dict__
                )

                siemplify.LOGGER.info(f"Requesting containment for endpoint ID: {endpoint_id}")
                action_id = manager.isolate_endpoint(endpoint_id)

                state = {
                    "action_id": action_id,
                    "endpoint_id": endpoint_id,
                    "started_at": time.time(),
                    "timeout_minutes": timeout_minutes,
                }

                json_result["operation_results"][endpoint_id] = {
                    "operation": "contain",
                    "result": "success",
                    "status": "containment_requested",
                    "action_id": action_id,
                    "reason": None,
                }
                action_status = EXECUTION_STATE_INPROGRESS
                result_value = json.dumps(state)
                output_message = (
                    f"Containment requested for endpoint {endpoint_id} (Action ID: {action_id}). "
                    "Waiting for confirmation."
                )
                siemplify.LOGGER.info(output_message)

            else:
                raw_additional_data = getattr(siemplify, "parameters", {}).get(
                    "additional_data"
                ) or extract_action_param(
                    siemplify,
                    param_name="additional_data",
                    is_mandatory=False,
                    default_value=None,
                )

                state = {}
                if raw_additional_data:
                    if isinstance(raw_additional_data, dict):
                        state = raw_additional_data
                    elif isinstance(raw_additional_data, str):
                        try:
                            state = json.loads(raw_additional_data)
                        except Exception:
                            state = {}

                action_id = state.get("action_id")
                endpoint_id = state.get("endpoint_id") or endpoint_id
                started_at = float(state.get("started_at", time.time()))
                timeout_minutes = int(state.get("timeout_minutes", timeout_minutes))

                # Check timeout
                elapsed_seconds = time.time() - started_at
                timeout_seconds = timeout_minutes * 60

                if elapsed_seconds > timeout_seconds:
                    output_message = (
                        f"Containment confirmation timed out for endpoint {endpoint_id} "
                        f"after {timeout_minutes} minutes."
                    )
                    siemplify.LOGGER.error(output_message)
                    json_result["operation_results"][endpoint_id] = {
                        "operation": "contain",
                        "result": "failure",
                        "status": "timeout",
                        "action_id": action_id,
                        "reason": output_message,
                    }
                    action_status = EXECUTION_STATE_FAILED
                    result_value = "false"
                    siemplify.result.add_result_json(json_result)
                    siemplify.end(output_message, result_value, action_status)
                    return

                siemplify.LOGGER.info(f"Checking action status for action ID: {action_id}")
                action_status_obj = manager.get_action_status(action_id)

                if action_status_obj.status == "COMPLETED_SUCCESSFULLY":
                    siemplify.LOGGER.info(
                        f"Action {action_id} completed successfully. Fetching updated metadata for {endpoint_id}."
                    )
                    endpoint_data = manager.get_endpoint_by_id(endpoint_id)
                    json_result["device_metadata"] = (
                        endpoint_data.to_json()
                        if hasattr(endpoint_data, "to_json")
                        else endpoint_data.__dict__
                    )
                    json_result["operation_results"][endpoint_id] = {
                        "operation": "contain",
                        "result": "success",
                        "status": "contained",
                        "action_id": action_id,
                        "reason": None,
                    }
                    action_status = EXECUTION_STATE_COMPLETED
                    result_value = "true"
                    output_message = (
                        f"Successfully confirmed containment for endpoint {endpoint_id} in Cortex XDR."
                    )
                    siemplify.LOGGER.info(output_message)

                elif action_status_obj.status in ["PENDING", "IN_PROGRESS"]:
                    json_result["operation_results"][endpoint_id] = {
                        "operation": "contain",
                        "result": "success",
                        "status": "containment_requested",
                        "action_id": action_id,
                        "reason": None,
                    }
                    action_status = EXECUTION_STATE_INPROGRESS
                    result_value = json.dumps(state)
                    output_message = (
                        f"Containment in progress for endpoint {endpoint_id} "
                        f"(Action ID: {action_id}, Status: {action_status_obj.status})."
                    )
                    siemplify.LOGGER.info(output_message)

                else:
                    err_reason = (
                        str(action_status_obj.error_reasons)
                        if action_status_obj.error_reasons
                        else f"Action status: {action_status_obj.status}"
                    )
                    output_message = (
                        f"Containment failed for endpoint {endpoint_id} in Cortex XDR: {err_reason}"
                    )
                    siemplify.LOGGER.error(output_message)
                    json_result["operation_results"][endpoint_id] = {
                        "operation": "contain",
                        "result": "failure",
                        "status": "failed",
                        "action_id": action_id,
                        "reason": err_reason,
                    }
                    action_status = EXECUTION_STATE_FAILED
                    result_value = "false"

    except CortexXDRNotFoundError as e:
        output_message = f"Could not find endpoint {endpoint_id} in Cortex XDR."
        siemplify.LOGGER.error(output_message)
        if endpoint_id:
            if endpoint_id not in json_result["operation_results"]:
                json_result["operation_results"][endpoint_id] = {"operation": "contain"}
            json_result["operation_results"][endpoint_id]["result"] = "failure"
            json_result["operation_results"][endpoint_id]["status"] = "unknown"
            json_result["operation_results"][endpoint_id]["reason"] = (
                "Could not find machine in Cortex XDR"
            )
        action_status = EXECUTION_STATE_FAILED
        result_value = "false"

    except (CortexXDRException, Exception) as e:
        output_message = f"Error executing action '{SCRIPT_NAME}'. Reason: {e}"
        siemplify.LOGGER.error(output_message)
        siemplify.LOGGER.exception(e)
        if endpoint_id:
            if endpoint_id not in json_result["operation_results"]:
                json_result["operation_results"][endpoint_id] = {"operation": "contain"}
            json_result["operation_results"][endpoint_id]["result"] = "failure"
            json_result["operation_results"][endpoint_id]["status"] = "unknown"
            json_result["operation_results"][endpoint_id]["reason"] = str(e)
        action_status = EXECUTION_STATE_FAILED
        result_value = "false"

    siemplify.result.add_result_json(json_result)
    siemplify.LOGGER.info(f"----------------- {mode} - Finished -----------------")
    siemplify.LOGGER.info(
        f"\n  status: {action_status}\n  result_value: {result_value}\n  output_message: {output_message}"
    )
    siemplify.end(output_message, result_value, action_status)


if __name__ == "__main__":
    is_first_run = len(sys.argv) < 3 or sys.argv[2] == "True"
    main(is_first_run)
