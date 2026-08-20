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
from unittest.mock import MagicMock
import pytest
import requests

# Set up mock SDK modules in sys.modules for standalone unit testing if not installed
class MockSiemplifyAction:
    def __init__(self, *args, **kwargs):
        self.script_name = ""
        self.parameters = {}
        self.target_entities = []
        self.result = MagicMock()
        self.LOGGER = MagicMock()

    def end(self, *args, **kwargs):
        pass


if "SiemplifyAction" not in sys.modules:
    mock_action_mod = MagicMock()
    mock_action_mod.SiemplifyAction = MockSiemplifyAction
    sys.modules["SiemplifyAction"] = mock_action_mod

if "soar_sdk" not in sys.modules:
    mock_sdk = MagicMock()
    mock_sdk.SiemplifyAction = MagicMock()
    mock_sdk.SiemplifyAction.SiemplifyAction = MockSiemplifyAction
    sys.modules["soar_sdk"] = mock_sdk
    sys.modules["soar_sdk.SiemplifyAction"] = sys.modules["SiemplifyAction"]

if "ScriptResult" not in sys.modules:
    mock_res = MagicMock()
    mock_res.EXECUTION_STATE_COMPLETED = 0
    mock_res.EXECUTION_STATE_FAILED = 1
    mock_res.EXECUTION_STATE_INPROGRESS = 2
    mock_res.EXECUTION_STATE_TIMEDOUT = 3
    sys.modules["ScriptResult"] = mock_res
    sys.modules["soar_sdk.ScriptResult"] = mock_res

if "SiemplifyUtils" not in sys.modules:
    mock_utils = MagicMock()
    mock_utils.output_handler = lambda func: func
    mock_utils.unix_now = lambda: 1000000000000
    sys.modules["SiemplifyUtils"] = mock_utils
    sys.modules["soar_sdk.SiemplifyUtils"] = mock_utils

if "SiemplifyDataModel" not in sys.modules:
    mock_dm = MagicMock()
    mock_dm.EntityTypes = MagicMock()
    mock_dm.EntityTypes.HOSTNAME = "HOSTNAME"
    mock_dm.EntityTypes.IPADDRESS = "IPADDRESS"
    sys.modules["SiemplifyDataModel"] = mock_dm

if "TIPCommon" not in sys.modules:
    mock_tip = MagicMock()
    mock_tip.extract_action_param = lambda siemplify, param_name, input_type=None, is_mandatory=False, default_value=None: default_value
    mock_tip.extract_configuration_param = lambda siemplify, provider_name, param_name, input_type=None, is_mandatory=False, default_value=None: default_value
    sys.modules["TIPCommon"] = mock_tip

try:
    import OverflowManager
    pytest_plugins = ("integration_testing.conftest",)
except ImportError:
    pass


class MockResponse:
    """Mock requests.Response object for unit testing."""

    def __init__(self, json_data=None, status_code=200, text="", raw_bytes=b""):
        self._json_data = json_data
        self.status_code = status_code
        self.text = text or ("" if json_data is None else str(json_data))
        self.headers = {}
        self.content = raw_bytes or b"dummy-stream-content"
        self._raw_bytes = raw_bytes or b"dummy-stream-content"

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON object could be decoded")
        return self._json_data

    def iter_content(self, chunk_size=1024):
        data = self._raw_bytes
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]


@pytest.fixture
def mock_response():
    return MockResponse


@pytest.fixture
def api_root():
    return "https://api-gw.paloaltonetworks.com"


@pytest.fixture
def api_key_id():
    return "101"


@pytest.fixture
def api_key():
    return "test-cortex-secret-api-key-99887766"


@pytest.fixture
def manager(api_root, api_key_id, api_key):
    from ..core.CortexXDRResponseManager import CortexXDRResponseManager

    return CortexXDRResponseManager(
        api_root=api_root,
        api_key_id=api_key_id,
        api_key=api_key,
        verify_ssl=True,
    )
