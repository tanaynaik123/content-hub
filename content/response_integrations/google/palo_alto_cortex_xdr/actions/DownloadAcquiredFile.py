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
import os
import sys
import time
from typing import Any, Dict, Optional

try:
    from soar_sdk.SiemplifyAction import SiemplifyAction
    from soar_sdk.SiemplifyUtils import output_handler, unix_now
    from soar_sdk.ScriptResult import (
        EXECUTION_STATE_COMPLETED,
        EXECUTION_STATE_FAILED,
    )
except ImportError:
    try:
        from SiemplifyAction import SiemplifyAction
        from SiemplifyUtils import output_handler, unix_now
        from ScriptResult import (
            EXECUTION_STATE_COMPLETED,
            EXECUTION_STATE_FAILED,
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
SCRIPT_NAME = "Download Acquired File"
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
def main():
    siemplify = SiemplifyAction()
    siemplify.script_name = SCRIPT_NAME
    siemplify.LOGGER.info(f"----------------- {SCRIPT_NAME} - Starting -----------------")

    status = EXECUTION_STATE_FAILED
    result: Any = "false"
    output_message = ""
    json_result: Dict[str, Any] = {}

    try:
        manager = get_manager(siemplify)

        raw_group_action_id = extract_action_param(
            siemplify,
            param_name="Group Action ID",
            input_type=str,
            is_mandatory=True,
        )
        group_action_id = int(str(raw_group_action_id).strip())

        raw_endpoint_id = extract_action_param(
            siemplify,
            param_name="Endpoint ID",
            input_type=str,
            is_mandatory=False,
            default_value=None,
        )
        endpoint_id = resolve_endpoint_id(siemplify, raw_endpoint_id)

        siemplify.LOGGER.info(
            f"Retrieving file retrieval details for action ID {group_action_id} and endpoint '{endpoint_id}'..."
        )
        retrieval_details = manager.get_file_retrieval_details(group_action_id)
        download_url = retrieval_details.get_download_url(endpoint_id)

        if not download_url:
            raise CortexXDRNotFoundError(
                f"Download URL for endpoint '{endpoint_id}' was not found in file retrieval details for action ID {group_action_id}."
            )

        siemplify.LOGGER.info(f"Streaming file download from '{download_url}'...")
        local_file_path, sha256_hash, file_size = manager.download_file_stream(download_url)
        downloaded_at = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

        json_result = {
            "sha256": sha256_hash,
            "local_package_file": local_file_path,
            "downloaded_at": downloaded_at,
            "bytes_written": file_size,
            "download_url": download_url,
        }

        status = EXECUTION_STATE_COMPLETED
        result = local_file_path
        output_message = (
            f"Successfully downloaded acquired file from endpoint {endpoint_id} "
            f"(Action ID: {group_action_id}, File: {local_file_path}, SHA-256: {sha256_hash}, Size: {file_size} bytes)."
        )

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
        output_message = f"Error executing Download Acquired File action: {e}"
        siemplify.LOGGER.error(output_message)

    siemplify.LOGGER.info(f"Status: {status}")
    siemplify.LOGGER.info(f"Result: {result}")
    siemplify.LOGGER.info(f"Output Message: {output_message}")
    if json_result:
        siemplify.result.add_result_json(json_result)
    siemplify.end(output_message, result, status)


if __name__ == "__main__":
    main()
