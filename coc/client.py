# coc/client.py
import requests
from urllib.parse import quote


class ClashOfClansClient:
    def __init__(self, api_key: str, base_url: str):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }

    def get_current_war(self, clan_tag: str) -> dict | None:
        encoded_tag = quote(clan_tag)
        url = f"{self.base_url}/clans/{encoded_tag}/currentwar"

        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            return response.json()

        # No active war OR error
        return None
