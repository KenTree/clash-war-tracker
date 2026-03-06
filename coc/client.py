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

        return None

    def get_cwl_group(self, clan_tag: str) -> dict | None:
        """Get current CWL group containing round/war tags"""
        encoded_tag = quote(clan_tag)
        url = f"{self.base_url}/clans/{encoded_tag}/currentwar/leaguegroup"

        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            return response.json()

        print(f"CWL group fetch failed: {response.status_code} - {response.text}")
        return None

    def get_cwl_war(self, war_tag: str) -> dict | None:
        """Get a specific CWL war by its war tag"""
        encoded_tag = quote(war_tag)
        url = f"{self.base_url}/clanwarleagues/wars/{encoded_tag}"

        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            return response.json()

        print(f"CWL war fetch failed: {response.status_code} - {response.text}")
        return None

    def get_active_cwl_war(self, clan_tag: str) -> dict | None:
        group = self.get_cwl_group(clan_tag)

        if not group:
            return None

        rounds = group.get("rounds", [])
        preparation_war = None  # fallback if no inWar found

        for round_data in reversed(rounds):
            war_tags = round_data.get("warTags", [])
            for war_tag in war_tags:
                if war_tag == "#0":
                    continue

                war = self.get_cwl_war(war_tag)
                if not war:
                    continue

                clan_tag_in_war = war.get("clan", {}).get("tag", "")
                opponent_tag_in_war = war.get("opponent", {}).get("tag", "")
                our_tag_normalized = clan_tag.upper()

                if our_tag_normalized not in (clan_tag_in_war.upper(), opponent_tag_in_war.upper()):
                    continue

                state = war.get("state", "")

                if state == "inWar":
                    return war  # ← return immediately if actively in battle
                elif state == "preparation":
                    preparation_war = war  # ← save as fallback only

        return preparation_war  # only returned if no inWar found
