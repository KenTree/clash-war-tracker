# coc/models.py
from dataclasses import dataclass


@dataclass
class Member:
    name: str
    tag: str
    attacks_used: int
    map_position: int
    is_cwl: bool = False

    @property
    def attacks_remaining(self) -> int:
        max_attacks = 1 if self.is_cwl else 2
        return max_attacks - self.attacks_used


@dataclass
class War:
    state: str
    start_time: str
    end_time: str
    members: list[Member]
    is_cwl: bool = False
