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
import sys
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
SCRIPT_NAME = "Check Containment Status"
SUPPORTED_ENTITY_TYPES = ["HOSTNAME", "IPADDRESS", "ADDRESS", "IP_ADDRESS"]


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
def main():
    siemplify = SiemplifyAction()
    siemplify.script_name = SCRIPT_NAME

    siemplify.LOGGER.info("----------------- Main - Starting -----------------")

    endpoint_id = extract_action_param(
        siemplify,
        param_name="Endpoint ID",
        input_type=str,
        is_mandatory=False,
        default_value=None,
    )

    json_result: Dict[str, Any] = {
        "endpoint_containment_status": {},
    }

    action_status = EXECUTION_STATE_COMPLETED
    result = "true"
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
            elif getattr(siemplify, "target_entities", []) and len(siemplify.target_entities) == 1:
                entity = siemplify.target_entities[0]
                endpoint_id = (
                    getattr(entity, "identifier", None)
                    or getattr(entity, "original_identifier", None)
                    or str(entity)
                )
            else:
                raise ValueError(
                    "If not passing in an endpoint id, your case/alert needs to be associated "
                    f"with exactly one HOSTNAME or IPADDRESS entity containing the endpoint id. Found {len(suitable_entities)} valid entities."
                )

        manager = get_manager(siemplify)

        siemplify.LOGGER.info(f"Fetching endpoint details for ID: {endpoint_id}")
        endpoint_data = manager.get_endpoint_by_id(endpoint_id)
        containment_status = manager.get_containment_status(endpoint_id)
        endpoint_details = (
            endpoint_data.to_json()
            if hasattr(endpoint_data, "to_json")
            else endpoint_data.__dict__
        )

        json_result["endpoint_containment_status"][endpoint_id] = {
            "status": containment_status,
            "raw_status": endpoint_data.is_isolated,
            "reason": None,
            "endpoint_details": endpoint_details,
        }

        output_message = f"Containment status of endpoint {endpoint_id} is: {containment_status}"
        action_status = EXECUTION_STATE_COMPLETED
        result = "true"
        siemplify.LOGGER.info(output_message)

    except CortexXDRNotFoundError as e:
        output_message = f"Action was not able to find an endpoint with the given ID: {endpoint_id}"
        siemplify.LOGGER.error(output_message)
        if endpoint_id:
            json_result["endpoint_containment_status"][endpoint_id] = {
                "status": "unknown",
                "raw_status": None,
                "reason": "Could not find machine in Cortex XDR",
                "endpoint_details": None,
            }
        action_status = EXECUTION_STATE_FAILED
        result = "false"

    except Exception as e:
        output_message = f"Action did not complete due to error: {e}"
        siemplify.LOGGER.error(output_message)
        siemplify.LOGGER.exception(e)
        if endpoint_id:
            json_result["endpoint_containment_status"][endpoint_id] = {
                "status": "unknown",
                "raw_status": None,
                "reason": str(e),
                "endpoint_details": None,
            }
        action_status = EXECUTION_STATE_FAILED
        result = "false"

    siemplify.LOGGER.info("----------------- Main - Finished -----------------")
    siemplify.LOGGER.info(f"Status: {action_status}")
    siemplify.LOGGER.info(f"Result: {result}")
    siemplify.LOGGER.info(f"Output Message: {output_message}")
    siemplify.result.add_result_json(json_result)
    siemplify.end(output_message, result, action_status)


if __name__ == "__main__":
    main()
