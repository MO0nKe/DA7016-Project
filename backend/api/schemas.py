"""Request bodies. Responses are the core models (`Document`, `Job`, `Annotation`…) or small dicts."""

from pydantic import BaseModel


class PagesRequest(BaseModel):
    """A list of page indexes."""

    pages: list[int]


class TranslateRequest(BaseModel):
    """Which languages, pages and blocks to translate."""

    langs: list[str]
    pages: list[int] | None = None  # None = all pages
    block_ids: list[str] | None = None  # None = every block on those pages
    force: bool = False  # re-translate blocks that already have a translation (keeps nothing)
    include_figures: bool = False  # also text inside images and figures (often doesn't fit)


class TextRequest(BaseModel):
    """A selected snippet to translate into each of `langs`."""

    text: str
    langs: list[str]


class RomaniseRequest(BaseModel):
    """Text to write in Latin letters."""

    text: str
    lang: str  # the language the text is written in


class EditRequest(BaseModel):
    """A prompt edit of one block's translation."""

    lang: str
    instruction: str
    regenerate: bool = False  # ask the model again instead of reusing a cached answer


class LangRequest(BaseModel):
    """A request naming one language."""

    lang: str


class FolderUpdate(BaseModel):
    """A folder's new name, new parent, or both."""

    name: str | None = None
    parent: str | None = None
    move: bool = False  # true: set `parent` (None = top level); false: leave the parent alone


class Placement(BaseModel):
    """The folder to put a document in; None for the top level."""

    folder_id: str | None = None
