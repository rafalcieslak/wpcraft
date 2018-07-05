from typing import NamedTuple, List, NewType, Tuple, Optional

WPScope = NewType('WPScope', str)
WPID = NewType('WPID', str)


class WPData(NamedTuple):
    id: WPID
    tags: List[str]
    score: float
    author: Optional[str]
    license: Optional[str]
    source: Optional[str]


class Resolution(NamedTuple):
    w: int
    h: int


__all__ = ["WPScope", "WPID", "WPData", "Resolution"]
