# coc/war_logic.py
from coc.models import War, Member


def parse_war_data(raw_data: dict) -> War:
    clan_data = raw_data["clan"]
    members = []

    for m in clan_data["members"]:
        attacks_used = len(m.get("attacks", []))
        members.append(
            Member(
                name=m["name"],
                tag=m["tag"],
                attacks_used=attacks_used,
                map_position=m["mapPosition"]  # Get war position from API
            )
        )

    return War(
        state=raw_data["state"],
        start_time=raw_data["startTime"],
        end_time=raw_data["endTime"],
        members=members
    )


def members_with_remaining_attacks(war: War) -> list[Member]:
    if war.state != "inWar":
        return []

    return [
        member
        for member in war.members
        if member.attacks_remaining > 0
    ]
