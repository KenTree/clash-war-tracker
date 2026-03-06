# coc/war_logic.py
from coc.models import War, Member


def parse_war_data(raw_data: dict) -> War:
    clan_data = raw_data.get("clan", {})
    raw_members = clan_data.get("members", [])

    if not raw_members:
        print("No members found in war data. Check API key IP whitelist.")
        return None

    members = []  # Clean list for parsed Member objects

    for m in raw_members:
        attacks_used = len(m.get("attacks", []))
        members.append(
            Member(
                name=m["name"],
                tag=m["tag"],
                attacks_used=attacks_used,
                map_position=m["mapPosition"]
            )
        )

    is_cwl = raw_data.get("isWarLogPublic") is None or "warLeague" in raw_data

    return War(
        state=raw_data["state"],
        start_time=raw_data["startTime"],
        end_time=raw_data["endTime"],
        members=members,
        is_cwl=is_cwl
    )


def members_with_remaining_attacks(war: War) -> list[Member]:
    if war.state != "inWar":
        return []

    return [
        member
        for member in war.members
        if member.attacks_remaining > 0
    ]
