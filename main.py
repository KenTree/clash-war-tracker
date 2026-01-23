# main.py
from config import COC_API_KEY, CLAN_TAG, COC_BASE_URL
from coc.client import ClashOfClansClient
from coc.war_logic import parse_war_data, members_with_remaining_attacks


def main():
    client = ClashOfClansClient(COC_API_KEY, COC_BASE_URL)
    raw_war = client.get_current_war(CLAN_TAG)

    if not raw_war:
        print("No active war.")
        return

    war = parse_war_data(raw_war)
    remaining = members_with_remaining_attacks(war)

    print(f"War State: {war.state}")
    print("Members with remaining attacks:")
    for m in remaining:
        print(f"- {m.name} ({m.attacks_remaining} attacks left)")


if __name__ == "__main__":
    main()
