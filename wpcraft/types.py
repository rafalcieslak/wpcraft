from typing import NamedTuple, List, NewType

WPScope = NewType('WPScope', str)
WPID = NewType('WPID', str)


class WPData(NamedTuple):
    id: WPID
    tags: List[str]
