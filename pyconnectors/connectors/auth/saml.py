from typing import Any

from pyconnectors.models.base import BaseConnector
from pyconnectors.adapters.registry.memory import connector

try:
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
except ImportError:
    OneLogin_Saml2_Auth = None


@connector("auth.saml")
class SAMLConnector(BaseConnector):
    """SAML 2.0 Single Sign-On Connector using python3-saml."""

    def execute(
        self, request_data: dict[str, Any], action: str = "process_response"
    ) -> dict[str, Any]:
        if OneLogin_Saml2_Auth is None:
            raise ImportError(
                "SAML connector requires python3-saml. Install with: pip install pyconnectors[saml]"
            )

        saml_settings = self.config.params.get("saml_settings")
        if not saml_settings:
            raise ValueError("SAMLConnector requires 'saml_settings' dictionary in configuration.")

        auth = OneLogin_Saml2_Auth(request_data, custom_base_path=saml_settings)

        if action == "login_url":
            return {"status": "success", "url": auth.login()}

        elif action == "process_response":
            auth.process_response()
            errors = auth.get_errors()
            if errors:
                return {"status": "error", "errors": errors, "reason": auth.get_last_error_reason()}

            if not auth.is_authenticated():
                return {"status": "error", "error": "Not authenticated"}

            return {
                "status": "success",
                "attributes": auth.get_attributes(),
                "nameid": auth.get_nameid(),
                "session_index": auth.get_session_index(),
            }

        elif action == "logout_url":
            return {"status": "success", "url": auth.logout()}

        else:
            raise ValueError(f"Action '{action}' is not supported.")
