"""PageModel: the rich intermediate representation that is the single source of
truth for both preview rendering and (future SP-B) export."""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any


@dataclass
class FontSpec:
    size: float            # points, in page-point space
    weight: int            # 400 normal, 700 bold
    italic: bool
    color: str             # "#rrggbb"
    align: str             # left|center|right|justify
    family_class: str      # serif|sans|mono


@dataclass
class Block:
    span_id: str
    role: str              # heading|body|list|code|table|caption
    bbox: List[float]      # [l, t, w, h] top-left points
    text: str
    font: Optional[FontSpec]


@dataclass
class Figure:
    bbox: List[float]      # [l, t, w, h] top-left points
    img: str               # filename only


@dataclass
class PageModel:
    page_w: float
    page_h: float
    kind: str              # text|image|mixed
    background: Dict[str, Any]   # {"color": "#rrggbb", "image": filename|None}
    blocks: List[Block]
    figures: List[Figure]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_w": self.page_w, "page_h": self.page_h, "kind": self.kind,
            "background": self.background,
            "blocks": [asdict(b) for b in self.blocks],
            "figures": [asdict(f) for f in self.figures],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PageModel":
        blocks = []
        for b in d.get("blocks", []):
            f = b.get("font")
            blocks.append(Block(
                span_id=b["span_id"], role=b.get("role", "body"),
                bbox=list(b["bbox"]), text=b.get("text", ""),
                font=FontSpec(**f) if f else None,
            ))
        figures = [Figure(bbox=list(f["bbox"]), img=f["img"]) for f in d.get("figures", [])]
        return cls(
            page_w=d["page_w"], page_h=d["page_h"], kind=d.get("kind", "text"),
            background=d.get("background", {"color": "#ffffff", "image": None}),
            blocks=blocks, figures=figures,
        )

    @classmethod
    def from_json(cls, s: str) -> "PageModel":
        return cls.from_dict(json.loads(s))
