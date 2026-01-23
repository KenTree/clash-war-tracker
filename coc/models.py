# coc/models.py
from dataclasses import dataclass
from typing import List


@dataclass
class Member:
    name: str
    tag: str
    attacks_used: int

    @property
    def attacks_remaining(self) -> int:
        return max(0, 2 - self.attacks_used)


@dataclass
class War:
    state: str
    start_time: str
    end_time: str
    members: List[Member]
