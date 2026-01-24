# coc/models.py
from dataclasses import dataclass


@dataclass
class Member:
    name: str
    tag: str
    attacks_used: int
    map_position: int

    @property
    def attacks_remaining(self) -> int:
        return 2 - self.attacks_used


@dataclass
class War:
    state: str
    start_time: str
    end_time: str
    members: list[Member]
    is_cwl: bool = False