"""The document model: one JSON file per document, read and written by every stage.

Coordinates are PDF points with the origin at the top-left of the page.
"""

from typing import Literal

from pydantic import BaseModel, Field, computed_field

from .languages import detect_language

BlockSource = Literal["text_layer", "ocr"]
PageSource = Literal["text_layer", "ocr", "pending_ocr"]
TranslationStatus = Literal["done", "truncated", "error", "edited"]


class Style(BaseModel):
    """How a block's text looks on the original page."""

    font_size: float | None = None  # pt; None = unknown (OCR), the renderer fits text to the box
    bold: bool = False
    italic: bool = False
    color: str | None = None  # "#rrggbb"
    background: str | None = None  # box fill, for pages whose original text can't be removed (OCR)
    align: Literal["left", "center", "right", "justify"] = "left"
    line_height: float | None = None  # baseline-to-baseline distance / font size, from the PDF
    family: Literal["serif", "sans", "mono"] = "sans"
    font: str | None = None  # the PDF font name (subset prefix dropped); see Document.fonts
    mark_color: str | None = None  # footnote/citation markers' own colour, where it differs (links are often blue)
    hanging: bool = False  # lines after an item's first start under its text, past the bullet or number


class Cell(BaseModel):
    """One cell of a text-layer table."""

    row: int
    col: int
    bbox: list[float]
    text: str
    header: bool = False
    style: Style | None = None  # the cell's own bold, italic and colour ("ASSETS" in blue); None on older documents


class Edit(BaseModel):
    """One prompt edit of a translation, with what it replaced so it can be undone."""

    instruction: str
    before: str
    after: str
    model: str
    ts: str
    cost_usd: float = 0.0
    style_before: dict = Field(default_factory=dict)  # Translation.style before the edit, for undo
    created: bool = False  # the edit made the translation (a section edited before it was translated): undo removes it


class Translation(BaseModel):
    """A block's translation into one language, with its edit history."""

    text: str = ""  # text blocks
    html: str | None = None  # OCR tables: the table HTML with translated text nodes
    cells: list[str] | None = None  # text-layer tables: one entry per Block.cells, same order
    rich: str | None = None  # `text` with Block.rich's inline tags where they came back intact
    status: TranslationStatus = "done"
    error: str | None = None
    edits: list[Edit] = Field(default_factory=list)
    style: dict = Field(default_factory=dict)  # a reviewer's changes to Block.style for this translation (bold, align…)
    lang: str | None = None  # the language it is written in, when an edit asked for another one ("keep it in English")


class Maths(BaseModel):
    """An inline formula drawn from the original: its text inside the block's text (and translations), and a
    crop of the original glyphs that is drawn in its place, so it never goes through translation as words."""

    text: str
    bbox: list[float]
    descent: float  # pt from the line's baseline down to the bottom of bbox
    image: str  # crop of the original page, relative to the document dir


class Block(BaseModel):
    """A piece of a page (paragraph, heading, table, caption…) with its box, style and translations."""

    id: str
    order: int
    label: str  # Bodhan's 37-class layout taxonomy (text-layer blocks use a subset)
    type: str
    bbox: list[float]
    text: str = ""
    rich: str | None = None  # `text` with <b>, <i> and <span style="color:…"> around runs styled apart from `style`
    html: str | None = None  # OCR tables
    cells: list[Cell] | None = None  # text-layer tables
    style: Style = Field(default_factory=Style)
    source: BlockSource
    translatable: bool = True
    in_figure: bool = False  # text inside an image or figure: translated only when the user asks
    room: float = 0.0  # empty space below the box (pt) a longer translation may grow into
    continues: str | None = None  # id of the block its last sentence goes on in (structure review); translated together
    maths: list[Maths] = Field(default_factory=list)  # inline formulas, in reading order
    translations: dict[str, Translation] = Field(default_factory=dict)  # by target language


class Page(BaseModel):
    """One page: its size, rasters, where its text came from, and its blocks."""

    index: int
    width: float
    height: float
    source: PageSource
    dpi: int
    image: str  # raster of the original page, relative to the document dir
    background: str  # raster with the text removed (same as image for OCR pages)
    text_quality: float
    blocks: list[Block] = Field(default_factory=list)
    figure_text_kept: bool = False  # the background keeps figure text as drawn (ingested 2026-10-27 or later)
    obstacles: list[list[float]] = Field(default_factory=list)  # pictures and line art text must not run into
    review: dict | None = None  # the structure review's fixes that took effect (pipeline/structure.py)


class Document(BaseModel):
    """An ingested PDF: its pages and the fonts embedded in it. Saved as one doc.json."""

    id: str
    filename: str
    created: str
    pages: list[Page]
    fonts: dict[str, str] = Field(default_factory=dict)  # PDF font name -> embedded font file, reusable in the browser

    def _detected(self):
        return detect_language(" ".join(b.text for p in self.pages for b in p.blocks)[:20_000])

    @computed_field
    @property
    def source_lang(self) -> str | None:
        """The supported language the document is written in (None until it has text, or when unsure)."""
        return self._detected()[0]

    @computed_field
    @property
    def unsupported_lang(self) -> str | None:
        """The language it's written in when the app doesn't support it ("Spanish"): translations will be unreliable."""
        return self._detected()[1]


class DocumentSummary(BaseModel):
    """A document's library card: name, size and the languages it has been translated into."""

    id: str
    filename: str
    created: str
    page_count: int
    pending_ocr: list[int]
    languages: list[str]
    source_lang: str | None = None
    unsupported_lang: str | None = None

    @classmethod
    def of(cls, doc):
        """The summary of `doc`."""
        langs = sorted({lang for p in doc.pages for b in p.blocks for lang in b.translations})
        return cls(
            id=doc.id,
            filename=doc.filename,
            created=doc.created,
            page_count=len(doc.pages),
            pending_ocr=[p.index for p in doc.pages if p.source == "pending_ocr"],
            languages=langs,
            source_lang=doc.source_lang,
            unsupported_lang=doc.unsupported_lang,
        )


class Annotation(BaseModel):
    """A reader's mark on a page, in the view it was made on. Boxes are PDF points from the page's top-left."""

    id: str = ""
    kind: Literal["highlight", "note", "text", "slip"] = "highlight"
    page: int
    rects: list[list[float]]  # highlight: one box per line; note/text: a single box
    color: str = Field("#fde047", pattern=r"^#[0-9a-fA-F]{6}$")
    quote: str = ""  # the highlighted text
    comment: str = ""  # note on a highlight, or the content of a text box
    font_size: float = 11.0  # text boxes
    created: str = ""
    lang: str = ""  # the view it was made on: "" the original, else a language view (a slip: the language it shows)
    # Translation slips (removed): documents may still hold some; they are kept on disk but not shown.
    translations: dict[str, Translation] = Field(
        default_factory=dict
    )  # selection slips: by language, with edit history
    style: Style | None = None  # the original text's look (size, family, line height, page colour)
    block_id: str | None = None  # a section's slip: the block it covers
