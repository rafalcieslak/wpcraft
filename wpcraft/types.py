from typing import NamedTuple, List, NewType, Tuple

WPScope = NewType('WPScope', str)
WPID = NewType('WPID', str)


class WPData(NamedTuple):
    id: WPID
    tags: List[str]


class Resolution(NamedTuple):
    w: int
    h: int


__all__ = ["WPScope", "WPID", "WPData", "Resolution"]
