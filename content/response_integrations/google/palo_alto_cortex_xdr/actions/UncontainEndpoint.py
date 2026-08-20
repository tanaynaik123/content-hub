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
SCRIPT_NAME = "Uncontain Endpoint"
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
    result: Any = "false"
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

        endpoint_id = str(endpoint_id).strip()

        json_result["operation_results"][endpoint_id] = {
            "operation": "uncontain",
            "result": None,
            "status": None,
            "action_id": None,
            "reason": None,
        }

        manager = get_manager(siemplify)

        if is_first_run:
            siemplify.LOGGER.info(f"Retrieving endpoint data for '{endpoint_id}'")
            endpoint_data = manager.get_endpoint_by_id(endpoint_id)

            siemplify.LOGGER.info(f"Requesting uncontainment for endpoint '{endpoint_id}'")
            action_id = manager.unisolate_endpoint(endpoint_id)

            json_result["operation_results"][endpoint_id]["action_id"] = action_id

            if not wait_for_confirmation:
                # Mode A: Fast Synchronous
                action_status = EXECUTION_STATE_COMPLETED
                result = "true"
                output_message = f"Successfully requested uncontainment for endpoint {endpoint_id} in Cortex XDR."
                json_result["operation_results"][endpoint_id]["result"] = "success"
                json_result["operation_results"][endpoint_id]["status"] = "uncontainment_requested"
                json_result["operation_results"][endpoint_id]["reason"] = None
                json_result["device_metadata"] = endpoint_data.to_json()
            else:
                # Mode B: Async First Run
                action_status = EXECUTION_STATE_INPROGRESS
                result = "true"
                output_message = (
                    f"Uncontainment initiated for endpoint {endpoint_id} (action ID: {action_id}). "
                    "Waiting for confirmation."
                )
                json_result["operation_results"][endpoint_id]["result"] = "success"
                json_result["operation_results"][endpoint_id]["status"] = "uncontainment_requested"
                json_result["operation_results"][endpoint_id]["reason"] = None
                json_result["device_metadata"] = endpoint_data.to_json()

                siemplify.result.additional_data = json.dumps({
                    "action_id": action_id,
                    "endpoint_id": endpoint_id,
                    "started_at": time.time(),
                })
        else:
            # Mode B: Async Subsequent Polling Run
            additional_data_raw = extract_action_param(
                siemplify,
                param_name="additional_data",
                input_type=str,
                is_mandatory=False,
                default_value=None,
            ) or getattr(siemplify.result, "additional_data", None)

            if not additional_data_raw and hasattr(siemplify, "parameters") and isinstance(siemplify.parameters, dict):
                additional_data_raw = siemplify.parameters.get("additional_data")

            additional_data = {}
            if additional_data_raw:
                try:
                    additional_data = json.loads(additional_data_raw)
                except Exception:
                    additional_data = {}

            action_id = additional_data.get("action_id")
            stored_endpoint_id = additional_data.get("endpoint_id") or endpoint_id
            started_at = additional_data.get("started_at", time.time())

            if stored_endpoint_id:
                endpoint_id = stored_endpoint_id
                if endpoint_id not in json_result["operation_results"]:
                    json_result["operation_results"][endpoint_id] = {
                        "operation": "uncontain",
                        "result": None,
                        "status": None,
                        "action_id": action_id,
                        "reason": None,
                    }

            if not action_id:
                raise ValueError("No action_id found in additional_data for async polling.")

            json_result["operation_results"][endpoint_id]["action_id"] = action_id

            # Check timeout
            elapsed_seconds = time.time() - started_at
            if elapsed_seconds > (timeout_minutes * 60):
                output_message = (
                    f"Uncontainment confirmation timed out for endpoint {endpoint_id} "
                    f"after {timeout_minutes} minutes."
                )
                siemplify.LOGGER.error(output_message)
                json_result["operation_results"][endpoint_id]["result"] = "failure"
                json_result["operation_results"][endpoint_id]["status"] = "unknown"
                json_result["operation_results"][endpoint_id]["reason"] = "Action confirmation timed out."
                action_status = EXECUTION_STATE_FAILED
                result = "false"
            else:
                siemplify.LOGGER.info(f"Checking status of action ID {action_id}")
                action_status_data = manager.get_action_status(action_id)
                status_str = action_status_data.status

                if status_str == "COMPLETED_SUCCESSFULLY":
                    siemplify.LOGGER.info(f"Action {action_id} completed successfully.")
                    endpoint_data = manager.get_endpoint_by_id(endpoint_id)
                    action_status = EXECUTION_STATE_COMPLETED
                    result = "true"
                    output_message = f"Successfully uncontained endpoint {endpoint_id} in Cortex XDR."
                    json_result["operation_results"][endpoint_id]["result"] = "success"
                    json_result["operation_results"][endpoint_id]["status"] = "uncontained"
                    json_result["operation_results"][endpoint_id]["reason"] = None
                    json_result["device_metadata"] = endpoint_data.to_json()
                elif status_str in ["IN_PROGRESS", "PENDING"]:
                    siemplify.LOGGER.info(f"Action {action_id} is still {status_str}.")
                    action_status = EXECUTION_STATE_INPROGRESS
                    result = "true"
                    output_message = f"Waiting for uncontainment to finish for endpoint {endpoint_id}."
                    json_result["operation_results"][endpoint_id]["result"] = "success"
                    json_result["operation_results"][endpoint_id]["status"] = "uncontainment_requested"
                    json_result["operation_results"][endpoint_id]["reason"] = None
                    siemplify.result.additional_data = json.dumps({
                        "action_id": action_id,
                        "endpoint_id": endpoint_id,
                        "started_at": started_at,
                    })
                elif status_str == "FAILED":
                    error_reason = str(action_status_data.error_reasons) or "Action failed in Cortex XDR"
                    output_message = f"Uncontainment action failed for endpoint {endpoint_id} in Cortex XDR: {error_reason}"
                    siemplify.LOGGER.error(output_message)
                    json_result["operation_results"][endpoint_id]["result"] = "failure"
                    json_result["operation_results"][endpoint_id]["status"] = "failed"
                    json_result["operation_results"][endpoint_id]["reason"] = error_reason
                    action_status = EXECUTION_STATE_FAILED
                    result = "false"
                else:
                    output_message = f"Unknown action status '{status_str}' for action ID {action_id}."
                    siemplify.LOGGER.error(output_message)
                    json_result["operation_results"][endpoint_id]["result"] = "failure"
                    json_result["operation_results"][endpoint_id]["status"] = status_str.lower()
                    json_result["operation_results"][endpoint_id]["reason"] = output_message
                    action_status = EXECUTION_STATE_FAILED
                    result = "false"

    except CortexXDRNotFoundError as e:
        output_message = f"Action was not able to find an endpoint with the given ID: {endpoint_id}"
        siemplify.LOGGER.error(output_message)
        if endpoint_id:
            if endpoint_id not in json_result["operation_results"]:
                json_result["operation_results"][endpoint_id] = {"operation": "uncontain"}
            json_result["operation_results"][endpoint_id]["result"] = "failure"
            json_result["operation_results"][endpoint_id]["status"] = "unknown"
            json_result["operation_results"][endpoint_id]["reason"] = "Could not find machine in Cortex XDR"
        action_status = EXECUTION_STATE_FAILED
        result = "false"

    except CortexXDRException as e:
        output_message = f"Error executing action '{SCRIPT_NAME}'. Reason: {e}"
        siemplify.LOGGER.error(output_message)
        siemplify.LOGGER.exception(e)
        if endpoint_id:
            if endpoint_id not in json_result["operation_results"]:
                json_result["operation_results"][endpoint_id] = {"operation": "uncontain"}
            json_result["operation_results"][endpoint_id]["result"] = "failure"
            json_result["operation_results"][endpoint_id]["status"] = "unknown"
            json_result["operation_results"][endpoint_id]["reason"] = str(e)
        action_status = EXECUTION_STATE_FAILED
        result = "false"

    except Exception as e:
        output_message = f"Error executing action '{SCRIPT_NAME}'. Reason: {e}"
        siemplify.LOGGER.error(output_message)
        siemplify.LOGGER.exception(e)
        if endpoint_id:
            if endpoint_id not in json_result["operation_results"]:
                json_result["operation_results"][endpoint_id] = {"operation": "uncontain"}
            json_result["operation_results"][endpoint_id]["result"] = "failure"
            json_result["operation_results"][endpoint_id]["status"] = "unknown"
            json_result["operation_results"][endpoint_id]["reason"] = str(e)
        action_status = EXECUTION_STATE_FAILED
        result = "false"

    siemplify.result.add_result_json(json_result)
    siemplify.LOGGER.info(f"----------------- {mode} - Finished -----------------")
    siemplify.LOGGER.info(
        f"\n  status: {action_status}\n  result: {result}\n  output_message: {output_message}"
    )
    siemplify.end(output_message, result, action_status)


if __name__ == "__main__":
    is_first_run = len(sys.argv) < 3 or sys.argv[2] == "True"
    main(is_first_run)
