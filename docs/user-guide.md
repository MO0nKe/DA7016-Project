# User guide

## The library

The home page is laid out like Zotero's:

- **Folders** (left): My library (everything), your folders, and Unfiled.
  - Right-click a folder for New subfolder, Rename and Delete folder; deleting moves its documents up a level.
  - Right-click the pane for New folder. Drag documents or folders onto a folder to move them.
- **Documents** (middle): a table you can sort by Title, Pages, Added or Opened.
  - Click a row to select it, and double-click or press Enter to open it.
  - The arrow keys move the selection, and Delete deletes the selected document.
  - Right-click a row for Open and Delete.
- **Details** (right, on wide screens): the first page, the document's language, its translations, when it was
  added and last read, its folder, and **Open**.
- **Search** in the top bar filters by file name.
- **Adding a PDF:** drop it anywhere on the table, or use the **Add a PDF** button in the top bar. It goes into the
  open folder. A small dialog offers to translate it right away: pick a language and press **Translate**, or choose
  **Not now**.

## The studio

```text
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ☰  ‹ 1/2 ›  Fit width   [ Original | Bengali | Hindi ] +              Translations │
├───────────────┬────────────────────────────────────────────────────┬─────────────────┤
│ Contents      │                                                    │ Translations    │
│ Pages         │                  the pages                         │ panel: the      │
│ Search        │                                                    │ document, or    │
│ Notes         │                                                    │ the selected    │
│ Glossary      │        ┌──── prompt box ─────────────┐             │ section         │
│               │        │ Describe a change         ↑ │             │                 │
└───────────────┴────────┴─────────────────────────────┴─────────────┴─────────────────┘
```

### Views: Original and one per language

The tabs above the pages switch views.

- **Original** is the PDF as it is. Nothing is ever drawn over it. Select text there (or in a language view) to
  highlight it, comment on it or translate it.
- **A language view** (Bengali, Hindi…) is the original page with every section translated into that language
  drawn over it, in the same place and style. Sections not translated yet show the original exactly as printed.
  - A view can be partial: three paragraphs you put into Tamil with a prompt make a Tamil view with just those.
  - Translations keep clear of pictures and wrap around them. A longer translation is made smaller to fit; one
    that still doesn't fit is cut off at its box and outlined in amber, and a message says so. **Show** opens it
    in the Translations panel, which always has the full text.
- **+** adds a language. Its view starts with every section in the original until you translate. A tab with nothing
  in it yet shows **×** to remove it.
- Switching views keeps your place on the page.
- **Hold Alt** (Option on a Mac) over a language view to see the original in place; let go to see the translation
  again.

### Translating

- **The whole document or one page:** open the Translations panel (top right), choose **Whole document** or
  **Page n**, then **Translate into …**. It translates into the language view you're on (from the Original view,
  the last one you had open), and shows the estimated time.
  - Text inside images and figures is skipped unless you turn on **Text in images**, because it rarely fits.
- **Some sections:** hold **Shift** and click sections, release Shift, and choose **Translate n sections** in the
  bar that appears.
- **Selected text:** select it and press **Translate** in the toolbar. The translation shows in the panel and isn't
  stored in the document.
- **Scanned pages** have no text to translate until you press **Run OCR** above them (one Bodhan call per page).

Translation runs in the background. The top bar shows its progress, and a message says when it's done. Closing the
document doesn't stop it.

### Selecting sections

- Click a section to select it. Ctrl/⌘-click adds or removes a section.
- Selecting text selects every section it covers; hold Ctrl/⌘ while selecting to add them.
- A click on the page around the sections lets them go.
- In a language view, clicking a section also opens it in the panel, with its original text and every translation.
  From there you can copy a translation, romanise it, or undo an edit.

### Prompt edits

With sections selected, type a change in the box under the pages and press Enter (Shift+Enter starts a new line).
Each section is revised separately, all at once.

- **Wording:** "more formal", "simpler", "use विद्यालय instead of स्कूल".
- **Language:** "put this in Tamil" sends the result to the Tamil view, created if needed, and the pages switch to
  it; the view you were in doesn't change. Bodhan does the translating, as everywhere else; any look you asked for
  ("in Tamil, bold") is applied too. "Keep this in English", on an English document, puts the original text
  back in the view you're on.
- **Maths:** "fix the formula" rewrites LaTeX or garbled maths as plain symbols (x², √2).
- **Look:** bold, italic, a colour, alignment ("centre it"), text size ("make it smaller"), or "make the bullets hang" (wrapped lines start under
  the text, not the bullet).

**Undo** (next to the send button) undoes the last edit of each selected section. An edit that created a section's
translation removes it again. If some sections fail (a rate limit), only those stay selected, so sending again
retries just them.

Edits follow your pinned glossary terms, and show on the page at once.

### Reading aids

- **Contents:** the PDF's bookmarks, or its headings, with the section you're reading highlighted.
- **Pages:** thumbnails.
- **Search:** the original text and every translation.
- **Define:** an English word or short phrase, from an offline dictionary (no API call).
- **Romanise:** a translation in Latin script (Bodhan transliteration), from the panel.

### Notes

- **Highlights and comments:** on the Original or any language view, select text and pick a highlight colour, or
  **Comment** to add a note to it. A note stays on the view it was made on.
- **Text boxes** (Original only): **Add text box** at the top of the Notes tab, then click on the page where it
  goes; Escape cancels. Drag its corner to resize it.

The Notes tab lists every note, grouped by view (Original, then each language), and clicking one shows its view.
Notes are saved with the document.

### Glossary

Pin how a term is always translated ("enrolment" → "नामांकन"). Pinned terms apply to every document and every
prompt edit. The Glossary tab lists translated sections that don't use a pinned term, and fixes them with a prompt
edit.
