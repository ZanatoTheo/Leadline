"""A behavioral tendency: a short instruction or belief that shapes how the agent acts. Tendencies drafted from web
research carry the URLs they came from in `sources`."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Tendency:
    id: str
    text: str
    sources: tuple = ()

    @classmethod
    def from_dict(cls, d: dict) -> "Tendency":
        return cls(id=d["id"], text=d["text"], sources=tuple(d.get("sources", ())))

    def to_dict(self) -> dict:
        d = {"id": self.id, "text": self.text}
        if self.sources:
            d["sources"] = list(self.sources)
        return d
