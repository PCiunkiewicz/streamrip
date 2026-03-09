from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("streamrip")


@dataclass(slots=True)
class LabelMetadata:
    name: str
    ids: list[str]

    def album_ids(self):
        return self.ids

    @classmethod
    def from_resp(cls, resp: dict) -> LabelMetadata:
        logger.debug(resp)
        return cls(resp["name"], [a["id"] for a in resp["albums"]])
