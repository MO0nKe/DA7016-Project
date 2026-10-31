"""Translate a document's blocks with Bodhan indic-translate.

Each block is split into the units actually sent: table cells one by one, the text nodes of OCR table HTML, and plain
text otherwise. In text blocks, inline formulas travel as numbered placeholders (⟦1⟧) and are put back as their
original text, where the model moved them. Footnote and citation markers ("¹", "[²][³]") are kept out of the text the
model sees and put back after the sentence they belonged to (the end of a cell). Runs styled apart from their block
(bold, italics, colour) travel as their HTML tags; if the model breaks them, the words are kept without them. A
truncated result is retried sentence by sentence. Short headings are then revised with OpenRouter (`headings`).

Modules: `units` (what is sent), `headings` (the heading pass), `run` (the Bodhan calls and the document job).
"""

from .run import estimate, translate_document, translate_text

__all__ = ["estimate", "translate_document", "translate_text"]
