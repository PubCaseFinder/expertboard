import os

import requests


class PubCaseFinderClient:
    def __init__(self, base_url=None, timeout=8):
        self.base_url = (base_url or os.environ.get("PUBCASEFINDER_BASE_URL", "")).rstrip("/")
        self.timeout = timeout

    def is_configured(self):
        return bool(self.base_url)

    def health_hint(self):
        if not self.is_configured():
            return {
                "status": "not_configured",
                "label": "PubCaseFinder URL is not configured",
            }
        return {
            "status": "configured",
            "label": f"Configured: {self.base_url}",
        }

    def get(self, path, params=None):
        if not self.is_configured():
            return None
        response = requests.get(
            f"{self.base_url}/{path.lstrip('/')}",
            params=params or {},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

