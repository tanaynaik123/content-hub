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
import datetime
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

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
        CortexXDRAcquisitionPendingError,
        CortexXDRAuthError,
        CortexXDRException,
        CortexXDRNotFoundError,
        CortexXDRValidationError,
    )
except ImportError:
    from CortexXDRResponseManager import CortexXDRResponseManager
    from exceptions import (
        CortexXDRActionError,
        CortexXDRAcquisitionPendingError,
        CortexXDRAuthError,
        CortexXDRException,
        CortexXDRNotFoundError,
        CortexXDRValidationError,
    )

PROVIDER_NAME = "PaloAltoCortexXDR"
SCRIPT_NAME = "Acquire File"
SUPPORTED_ENTITY_TYPES = ["HOSTNAME", "IP_ADDRESS", "IPADDRESS", "HOST", "ADDRESS"]


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


def resolve_endpoint_id(siemplify: SiemplifyAction, explicit_endpoint_id: Optional[str]) -> str:
    """
    Resolve endpoint ID from explicit parameter or target entities fallback.

    :param siemplify: SiemplifyAction instance
    :param explicit_endpoint_id: Explicit endpoint ID parameter string
    :return: Resolved endpoint ID string
    :raises ValueError: If endpoint ID cannot be resolved or multiple candidates found
    """
    if explicit_endpoint_id and str(explicit_endpoint_id).strip():
        return str(explicit_endpoint_id).strip()

    suitable_entities = [
        entity
        for entity in getattr(siemplify, "target_entities", [])
        if str(getattr(entity, "entity_type", "")).upper() in SUPPORTED_ENTITY_TYPES
    ]

    if len(suitable_entities) == 1:
        entity = suitable_entities[0]
        return str(
            getattr(entity, "identifier", None)
            or getattr(entity, "original_identifier", None)
            or entity
        ).strip()

    if len(suitable_entities) > 1:
        raise ValueError(
            f"Found {len(suitable_entities)} suitable target entities. Please specify 'Endpoint ID' explicitly."
        )

    raise ValueError(
        "Endpoint ID was not provided and no suitable target entities (HOSTNAME/IP_ADDRESS) were found."
    )


@output_handler
def main(is_first_run: bool = True):
    siemplify = SiemplifyAction()
    siemplify.script_name = SCRIPT_NAME
    siemplify.LOGGER.info(f"----------------- {SCRIPT_NAME} - Starting (is_first_run={is_first_run}) -----------------")

    status = EXECUTION_STATE_FAILED
    result: Any = "false"
    output_message = ""
    json_result: Dict[str, Any] = {}

    try:
        manager = get_manager(siemplify)

        if is_first_run:
            raw_endpoint_id = extract_action_param(
                siemplify,
                param_name="Endpoint ID",
                input_type=str,
                is_mandatory=False,
                default_value=None,
            )
            endpoint_id = resolve_endpoint_id(siemplify, raw_endpoint_id)

            file_path = extract_action_param(
                siemplify,
                param_name="File Path",
                input_type=str,
                is_mandatory=True,
            )
            target_os = extract_action_param(
                siemplify,
                param_name="Target OS",
                input_type=str,
                is_mandatory=False,
                default_value=None,
            )
            timeout_hours = extract_action_param(
                siemplify,
                param_name="Timeout Hours",
                input_type=int,
                is_mandatory=False,
                default_value=72,
            )

            # Auto-detect OS type via get_endpoint_by_id if Target OS is omitted
            if not target_os or not str(target_os).strip() or str(target_os).strip().lower() == "auto":
                siemplify.LOGGER.info(f"Target OS omitted or Auto. Auto-detecting OS for endpoint '{endpoint_id}'...")
                endpoint = manager.get_endpoint_by_id(endpoint_id)
                os_type = endpoint.os_type or "windows"
            else:
                os_type = str(target_os).strip()

            siemplify.LOGGER.info(
                f"Initiating file retrieval for '{file_path}' (OS: {os_type}) on endpoint '{endpoint_id}'..."
            )
            group_action_id = manager.initiate_file_retrieval(endpoint_id, os_type, file_path)

            additional_data = {
                "group_action_id": group_action_id,
                "endpoint_id": endpoint_id,
                "file_path": file_path,
                "timeout_hours": timeout_hours,
                "started_at": time.time(),
            }

            status = EXECUTION_STATE_INPROGRESS
            result = json.dumps(additional_data)
            output_message = (
                f"File acquisition initiated with action ID {group_action_id} for '{file_path}' "
                f"on endpoint {endpoint_id}. Polling for completion."
            )
            json_result = {
                "group_action_id": group_action_id,
                "endpoint_id": endpoint_id,
                "file_path": file_path,
                "status": "IN_PROGRESS",
            }

        else:
            raw_additional_data = extract_action_param(
                siemplify,
                param_name="additional_data",
                input_type=str,
                is_mandatory=False,
                default_value=None,
            ) or getattr(siemplify, "parameters", {}).get("additional_data") or "{}"

            additional_data = (
                json.loads(raw_additional_data)
                if isinstance(raw_additional_data, str)
                else (raw_additional_data or {})
            )

            group_action_id = additional_data.get("group_action_id")
            endpoint_id = additional_data.get("endpoint_id")
            file_path = additional_data.get("file_path")
            started_at = float(additional_data.get("started_at", time.time()))
            timeout_hours = int(
                extract_action_param(
                    siemplify,
                    param_name="Timeout Hours",
                    input_type=int,
                    is_mandatory=False,
                    default_value=additional_data.get("timeout_hours", 72),
                )
            )

            # Check timeout
            elapsed_hours = (time.time() - started_at) / 3600.0
            if elapsed_hours >= timeout_hours:
                output_message = (
                    f"File acquisition timed out after {timeout_hours} hours "
                    f"(Action ID: {group_action_id}, Endpoint: {endpoint_id}, File: {file_path})."
                )
                siemplify.LOGGER.error(output_message)
                status = EXECUTION_STATE_FAILED
                result = "false"
                json_result = {
                    "group_action_id": group_action_id,
                    "endpoint_id": endpoint_id,
                    "file_path": file_path,
                    "status": "FAILED",
                    "error": output_message,
                }
                siemplify.result.add_result_json(json_result)
                siemplify.end(output_message, result, status)
                return

            siemplify.LOGGER.info(f"Polling action status for group_action_id {group_action_id}...")
            action_status = manager.get_action_status(group_action_id)
            endpoint_status = (
                action_status.endpoint_statuses.get(endpoint_id)
                or action_status.status
            )

            if endpoint_status in ("PENDING", "IN_PROGRESS", "COMPLETED_PARTIAL", "PENDING_ABORT"):
                status = EXECUTION_STATE_INPROGRESS
                result = json.dumps(additional_data)
                output_message = f"File acquisition in progress: {endpoint_status}"
                json_result = {
                    "group_action_id": group_action_id,
                    "endpoint_id": endpoint_id,
                    "file_path": file_path,
                    "status": endpoint_status,
                }

            elif endpoint_status in ("COMPLETED_SUCCESSFULLY", "SUCCEEDED"):
                siemplify.LOGGER.info(
                    f"Action {group_action_id} completed successfully. Retrieving download details..."
                )
                retrieval_details = manager.get_file_retrieval_details(group_action_id)
                download_url = retrieval_details.get_download_url(endpoint_id)

                if not download_url:
                    raise CortexXDRNotFoundError(
                        f"Download URL for endpoint '{endpoint_id}' was not found in action {group_action_id} details."
                    )

                siemplify.LOGGER.info(f"Downloading file from '{download_url}'...")
                local_file_path, sha256_hash, file_size = manager.download_file_stream(download_url)
                file_name = os.path.basename(file_path.replace("\\", "/"))
                downloaded_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

                json_result = {
                    "group_action_id": group_action_id,
                    "endpoint_id": endpoint_id,
                    "file_path": file_path,
                    "file_name": file_name,
                    "sha256": sha256_hash,
                    "file_size_bytes": file_size,
                    "local_package_file": local_file_path,
                    "download_url": download_url,
                    "downloaded_at": downloaded_at,
                    "status": "COMPLETED_SUCCESSFULLY",
                }
                status = EXECUTION_STATE_COMPLETED
                result = local_file_path
                output_message = (
                    f"Successfully acquired and downloaded file '{file_path}' "
                    f"from endpoint {endpoint_id} (SHA-256: {sha256_hash}, Size: {file_size} bytes)."
                )

            elif endpoint_status == "FAILED":
                error_reasons = (
                    action_status.error_reasons.get(endpoint_id)
                    or action_status.error_reasons
                )
                if isinstance(error_reasons, dict) and error_reasons.get("missing_files"):
                    missing_list = error_reasons.get("missing_files")
                    target_missing = (
                        missing_list[0]
                        if isinstance(missing_list, list) and missing_list
                        else file_path
                    )
                    output_message = f"File not found on endpoint: {target_missing}"
                elif "missing_files" in str(error_reasons):
                    output_message = f"File not found on endpoint: {file_path}"
                else:
                    output_message = (
                        f"File acquisition failed on endpoint {endpoint_id}: "
                        f"{error_reasons or 'Unknown error'}"
                    )

                status = EXECUTION_STATE_FAILED
                result = "false"
                json_result = {
                    "group_action_id": group_action_id,
                    "endpoint_id": endpoint_id,
                    "file_path": file_path,
                    "status": "FAILED",
                    "error": output_message,
                    "error_reasons": action_status.error_reasons,
                }

            else:
                output_message = f"Unknown or unexpected action status '{endpoint_status}' for action {group_action_id}"
                status = EXECUTION_STATE_FAILED
                result = "false"
                json_result = {
                    "group_action_id": group_action_id,
                    "endpoint_id": endpoint_id,
                    "file_path": file_path,
                    "status": endpoint_status,
                    "error": output_message,
                }

    except CortexXDRNotFoundError as e:
        status = EXECUTION_STATE_FAILED
        result = "false"
        output_message = f"Resource not found: {e}"
        siemplify.LOGGER.error(output_message)
    except CortexXDRValidationError as e:
        status = EXECUTION_STATE_FAILED
        result = "false"
        output_message = f"Validation error: {e}"
        siemplify.LOGGER.error(output_message)
    except CortexXDRAuthError as e:
        status = EXECUTION_STATE_FAILED
        result = "false"
        output_message = f"Authentication error: {e}"
        siemplify.LOGGER.error(output_message)
    except CortexXDRException as e:
        status = EXECUTION_STATE_FAILED
        result = "false"
        output_message = f"Cortex XDR error: {e}"
        siemplify.LOGGER.error(output_message)
    except Exception as e:
        status = EXECUTION_STATE_FAILED
        result = "false"
        output_message = f"Error executing Acquire File action: {e}"
        siemplify.LOGGER.error(output_message)

    siemplify.LOGGER.info(f"Status: {status}")
    siemplify.LOGGER.info(f"Result: {result}")
    siemplify.LOGGER.info(f"Output Message: {output_message}")
    if json_result:
        siemplify.result.add_result_json(json_result)
    siemplify.end(output_message, result, status)


if __name__ == "__main__":
    is_first = True
    if len(sys.argv) >= 2:
        is_first = sys.argv[1].lower() == "true"
    main(is_first_run=is_first)
