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


class CortexXDRException(Exception):
    """Base exception for Palo Alto Cortex XDR."""
    pass


class CortexXDRNotFoundError(CortexXDRException):
    """Exception raised when an endpoint or resource is not found (HTTP 404)."""
    pass


class CortexXDRValidationError(CortexXDRException):
    """Exception raised when input parameters, file path, or request payload is invalid (HTTP 400)."""
    pass


class CortexXDRAuthError(CortexXDRException):
    """Exception raised when API authentication fails (HTTP 401 / 403)."""
    pass


class CortexXDRActionError(CortexXDRException):
    """Exception raised when a containment, uncontainment, or retrieval action fails."""
    pass


class CortexXDRAcquisitionPendingError(CortexXDRException):
    """Exception raised when an asynchronous file acquisition is still pending."""
    pass


# Backward compatibility aliases
XDRException = CortexXDRException
XDRFileNotFoundException = CortexXDRNotFoundError
