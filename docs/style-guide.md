# UI Design System & Style Guide

This document is the visual, design and structural spec for **Panna** (पन्ना, Hindi for "page"), a PDF translator for Indian languages. When implementing UI, follow these tokens, components and layout rules. The look is **editorial**, a printed page's restraint: paper and ink, hairline rules instead of boxes and shadows, square corners, a serif for headings, small mono capitals for labels, and **one terracotta accent**. The PDF pages are the hero; the chrome stays quiet around them. Translated sections are shown by drawing the page again in the chosen language (a language view), with their details in the Translations panel.

The tokens live in `frontend/src/styles/index.css` (`@theme`). The shared component classes are in the same file, in `@layer components`.

---

## 1. Theme: paper, ink and one accent (light only)

There is one theme, flat: no textures. Panes and the desk are the same paper, set apart by hairline rules; the PDF pages are white on it, set off by a hairline (`shadow-page`), not a shadow. The top bar ends in an ink rule. Corners are square (radius tokens of 1–4px). There is no dark mode. (Chosen from three directions sketched in Open Design, 2026-10-31.)

| Role | Class | Value | Use |
| :--- | :--- | :--- | :--- |
| **Paper** | `bg-ground`, `bg-surface` | `oklch(98% 0.004 95)` | The desk behind the pages; top bar, sidebars, the Translations panel, the library |
| **Well** | `bg-well` | `oklch(95.5% 0.006 95)` | Tracks, hovered and alternate rows, script letters |
| **Line** | `border-line` | `oklch(90% 0.006 95)` | Hairline rules and dividers |
| **Bark** | `bg-bark` | `oklch(98% 0.004 95)`, the paper (lifted by a hairline and a faint shadow, never white) | `.popover` (menus, dropdowns, dialogs, the selection and pick bars), `.toast`, the prompt box |
| **Ink** | `text-ink`, `border-ink`, `bg-ink` | `oklch(20% 0.018 70)` | Primary text; the top bar's rule; the shown tab's underline; the rule over the shown translation; the primary button |
| **Muted** | `text-muted` | `oklch(48% 0.012 70)` | Secondary text, labels (about 6:1 on paper) |
| **Faint** | `text-faint` | `#8c8e9c` | Placeholders, empty states and disabled text |
| **Accent** | `bg-accent` / `ring-accent` | `oklch(52% 0.10 28)` terracotta (hover `oklch(45% 0.10 28)`) | Focus, selected sections, a running translation's progress, toggles that are on, the mark |
| **Accent wash** | `bg-wash` | `oklch(95% 0.02 28)` | The selected library row and outline item |
| **White** | `bg-paper` / `bg-white` | `#ffffff` | PDF pages |

**Rules**
**Rules**
- **Accent:** terracotta is the only colour, used sparingly (focus, selection, progress, the mark). Everything else is paper and ink. Status uses small amounts of emerald, amber and rose text; clipped sections keep their amber dashed outline, a warning rather than decoration.
- **Rules, not boxes:** what is active is marked in ink: the shown view's tab is underlined (`.views .hang`), the translation the pages show has a 2px ink rule over it. A running translation fills its tab's underline in the accent instead of showing a percentage. The mark is प on a terracotta tile with its headline across the top (`ui/PannaMark.tsx`, also `public/panna.svg` and the icons `scripts/make_assets.py` writes), followed by "Panna" in the serif.
- **Edges:** panes meet at hairlines (`border-line`), not gaps; nothing is defined by shadow alone.
- **Contrast:** body and muted text keep at least 4.5:1.
- **Focus ring:** always visible for keyboard users. The global rule is `:focus-visible { outline: 2px solid accent; offset 2px }`, except on `.field`, which draws its own accent ring (the prompt box rings its card).

### Shadow levels

| Token | Use |
| :--- | :--- |
| `shadow-raised-sm`, `shadow-raised`, `shadow-inset` | None (kept as names, so older markup stays flat) |
| `shadow-raised-lg` | Popovers, menus, dialogs, toasts and slide-over panels: a faint lift plus a hairline |
| `shadow-page` | PDF pages and library cards: a hairline ring, no shadow |

## 2. Typography

- **Sans:** Anek (Ek Type), one family drawn for Latin and ten Indian scripts, bundled from `@fontsource-variable/anek-*` (no network font). Base size 14px (`text-sm`); tables, facts and secondary labels 12px (`text-xs`); never smaller (Anek is a little narrow), except `.kicker`. Language names in the UI are English.
- **Serif:** Source Serif 4, bundled from `@fontsource-variable/source-serif-4` (`font-serif`, falling back to Anek for Indian scripts), for the wordmark and pane titles (`font-serif text-xl`, regular weight); there are no page titles.
- **Labels:** `.kicker`, mono capitals at 10.5px with wide tracking, for metadata only: the sidebar's tabs, "Original" and the language over each translation, Live/Mock.
- **Page text:** the PDF's own fonts, with the metric-compatible stacks in `backend/static/render.css`. Never restyle page text with the UI font.

## 3. Components (`index.css`)

| Class | What it is | States |
| :--- | :--- | :--- |
| `.btn` | White button, `rounded-md`, hairline border (`h-8`) | Hover grey; pressed (`:active`, `aria-pressed="true"`) darker grey; disabled faint |
| `.btn-primary` | Blue: the one main action on a screen | Hover `accent-strong`; disabled 40% blue |
| `.btn-ghost` | No fill or border; hover tints | Toolbars and icon buttons |
| `.btn-sm`, `.btn-icon` | Small (`h-7`), square icon button | — |
| `.card` | White surface, `rounded-lg`, hairline border | — |
| `.popover` | Floating card (`shadow-raised-lg`) | Selection toolbar, context menus, dialogs |
| `.field` | White input or select, `rounded-md`, hairline border | Focus: accent border and a light ring |
| `.views` | Tabs as words: the view tabs (Original, languages) and the Translations panel's two tabs. The shown one is underlined in ink with a faint wash rising from the rule | `aria-selected`; `.hang` is the underline; `data-running` turns a translating tab the accent with a band of it sweeping across (`ds-working`) and a 3px track under it that `.hang-progress` fills in the accent, the percentage in its tooltip |
| `.script` | A language as the first letter of its own name in its script (हि Hindi, म Marathi, த Tamil; `lib/scripts.ts`), on the well; the English name in its `title` | — |
| `PannaMark` | The mark (प on terracotta) and "Panna" in the serif, top left; returns to the library | — |
| `.doc-card` | A document in the library's card view: its first page, set off by a hairline | `aria-selected`: accent outline |
| `LanguagePicker` | The app's dropdown: languages, zoom and folders (`code` is the value). Never a native `<select>` | Popover list; arrows, Home/End, Enter, Escape, type-ahead |
| `useConfirm` (`ui/ConfirmDialog.tsx`) | The app's questions: `confirm` (a serif question, an optional muted line, **Cancel** focused, an ink action button: "Remove", "Delete") and `prompt` (the same with a text field, focused and selected: folder names). Never the browser's `confirm()` or `prompt()` | Enter answers; Escape or a click outside cancels; the action is disabled while the field is empty |
| `.seg` | Segmented control: grey track, chosen option white | Buttons use `aria-pressed` |
| `.tab-row` | The left sidebar's tabs: `.kicker` words spread across its width, the chosen one underlined | `aria-pressed` |
| `.list-row` | Navigation row (folders, contents) | `aria-current="true"`: light blue with blue text |
| `.chip` | Small grey tag (languages) | — |
| `.toggle` | Switch (`role="switch"`, `aria-checked`) | On turns blue |
| `.toast` | Bottom-right message after background work | Auto-dismisses after about 12 s |

**Icons:** 16px line icons, inline SVG, in `frontend/src/ui/icons.tsx` (stroke 1.8, `currentColor`). No icon library.

## Library (home page)

Laid out like Zotero's main window, under the top bar:

```text
+------------------------------------------------------------------------------------------+
| TOP BAR: Logo | [new folder] [add PDF] …                                   [Search] Live |
+---------------+------------------------------------------------------+-------------------+
| FOLDERS       | DOCUMENTS (table)                                    | DETAILS           |
| My library    | Title ▲ | Pages | Translations | Added | Opened      | page 1 preview    |
|   Folder      | row (selected row: blue, white text)                 | Title             |
|   Folder      | row                                                  | Pages, Language,  |
| Unfiled       | drop PDFs anywhere here                              | Translations, …   |
|               |                                                      | Folder · [Open]   |
+---------------+------------------------------------------------------+-------------------+
```

- **Folders** (left, grey well): My library, the folder tree, Unfiled. No counts. Right-click a folder for New subfolder, Rename, Delete folder; right-click the pane for New folder. Drag documents or folders onto a folder to move them.
- **List or cards** (toolbar icons, remembered): the list is a table; cards show each document's first page with its name, script letters and page count, straight on the paper. Both keep the sort, selection, keyboard, drag-to-folder and right-click behaviour; in cards a Sort dropdown stands in for the column headers. Nothing shows in an empty folder until the first list has loaded.
- **Documents** (table): sortable by clicking a column (Title, Pages, Added, Opened); alternate rows faintly grey, the selected one on the accent wash. Each document is listed by its file name. Translations are script letters, each named in its tooltip. Click selects, double-click or Enter opens, arrows move, Delete deletes; right-click for Open and Delete. Drop PDFs anywhere on the table to add them (into the open folder). Empty: "Drop PDFs here", or "No matches" while searching.
- **Details** (right, from 1100px wide): the first page, the title, a few facts (pages, language, translations, added, last read, scanned pages needing OCR), the folder, **Open** and **Delete**. Nothing selected: "3 documents".
- **Search** filters by file name.

## 4. Layout

```text
+--------------------------------------------------------------------------------------------------+
| TOP BAR: Logo | ☰ | ‹ page › | Zoom | [Original|Bengali|Hindi] + | …              | (Translations)   |
+----------------------+-------------------------------------------------+-------------------------+
| LEFT SIDEBAR (pane)  | STAGE: the pages, original or translated        | TRANSLATIONS (pane)     |
| [Contents|Pages|     |   Language view: click a section to see it      |  the selected section:  |
|  Search|Notes|       |   in the panel                                  |  the selected section:  |
|  Glossary]           |   select lines → toolbar → Translate            |  original + translations|
|                      |   Shift-click sections → Translate              |  nothing selected:      |
|                      |                                                 |  translate the document |
|                      | PROMPT BOX (floating, centred under the pages): |                         |
|                      |   grayed out until a section is selected        |                         |
+----------------------+-------------------------------------------------+-------------------------+
```

- **One view per language,** as tabs in the top bar: `Original | Bengali | Hindi | +`. Every view is exactly one language, and an edit appears in exactly one view. The shown tab is underlined in ink; a running translation fills its tab's underline in the accent.
- **Peek:** holding Alt (Option on a Mac) over a language view fades its translated sections out, so the original page shows in place; letting go brings them back. A tap of Alt, Alt in a shortcut, or Alt typed into a field doesn't peek. The Original tab's tooltip mentions it.
  - **Original:** the PDF as pdf.js draws it, with its text layer for exact selection, highlights, notes and text boxes. Nothing is ever drawn over it.
  - **A language view:** the original page, with each section translated into that language drawn over its own patch of the text-free page. Sections not translated into it yet are the original's own pixels, exactly as in Original (their text is there, invisible, for selecting and clicking). A view can be partial (a few sections put into Tamil by a prompt). Translating the document fills a view in.
  - **Tabs:** one for each language the document has translations in, and each language added to this document, in name order. **+** adds a language (its view starts all original); every tab but a running one shows **×** on hover to remove it; a language with translations asks first (`useConfirm`: "Remove the Hindi translation?" / "Its edits go too.") and deletes them, edits included. The languages are the tabs: there is no separate "translate into" list. A new document starts with the language last chosen (the upload dialog, or **+**).
  - **Switching** keeps the scroll position and cross-fades the pages in once they're ready.
- **Language lists** use the app's own dropdown (`LanguagePicker`: a field- or chip-style button opening a popover list, with arrows, Enter, Escape and type-ahead), never a native select. The document's own language is greyed out in every "translate into" list with the note "Original language". It is detected from the text (`languages.detect_language`): the script, then for shared scripts the languages' common words (Hindi, Marathi, Nepali, Sanskrit… in Devanagari; Assamese by its own letters). When the words don't settle it, nothing is greyed out.
- **Unsupported source languages** (Spanish, French, Persian, Cyrillic or Chinese text…): the upload dialog and the Translations panel say the document "seems to be in Spanish, which the app doesn't support. Translations from it will be unreliable." Translating is still allowed.
- **After an upload,** a small dialog ("Translate", the file name, a language, the estimated time) offers **Translate**, which starts it and opens the document, or **Not now**, which opens the original. No API counts or costs anywhere in the app. Scanned pages are noted as skipped until OCR.
- **While a translation runs,** its language tab's underline fills in the accent over a hairline track (the percentage in its tooltip); there is no other progress bar. The original stays readable. A reopened document picks up its running translation.
- **When it finishes,** a toast says the translation is ready (and if some parts stayed in the original), with **Show translation**. The pages don't switch on their own.
- **Cut-off sections:** a translation too long for its place even at its smallest size is clipped to its box, outlined with an amber dashed line, with a tooltip saying the full text is in the Translations panel. The first time a view shows such sections, a toast says how many ("3 sections are too long to fit and are cut off.") with **Show**, which opens the first in the panel.
- **Selected lines** are translated into every tab's language and shown as cards in the panel. Shift-picked sections are translated into the language view shown.
- **One place for details: the Translations panel** (right; it slides over the page below 1100px).
  - **A selected section** (click one in the Translation view): its original text and one card per language (Translate a missing one; Copy and Edit as icons; Romanise; Edit opens presets, Try again, Undo, history). **Show** shows the pages in that language. An edit swaps just that section on the page.
  - **Two tabs:** **Translations** (what is selected, below; "Select a section" when nothing is) and **Translate**: a language (the view shown by default, any other from the list), Whole document or this page, "Text in images" opt-in, the estimated time, and **Translate into Hindi**, or "Translated into Hindi" when it's done. Starting adds and shows that language's tab. Selecting something switches to Translations; a document opens on Translate.
  - **Define** results also appear here.
- **The prompt box** floats centred under the pages (at most 2xl wide), like a chat input: one line, an Undo icon while the sections have edits, and a square ink send button. It is grayed out until a section is selected. **While an edit or undo runs,** each section it changes keeps a solid accent outline with a band of the accent shimmering across it (`.ds-working`, a layer over the drawn section) until its new text lands, and the send button pulses in the accent. Nothing else: no progress bar or status text in the box. Reduced motion keeps the shimmer still. Its placeholder is all the text it has: "Select a section to edit", "Translate it first", or "Describe a change".
  - **Selecting sections:** a click on a section (either view) selects it; Ctrl/⌘-click adds or removes one; selected text selects every section it covers (Ctrl/⌘ held: added). They stay selected while the prompt is typed. A click on the page around them lets them go. Selected sections are outlined in every view. A click in a language view also opens the section in the panel; in the Original view the panel only follows if it's open.
  - **Where an edit lands:** in the language view shown (from the Original view: the last one shown). A section not translated yet is edited from its original. Enter applies, Shift+Enter breaks the line. Each section is its own request, all at once.
  - **A prompt** may reword the translation, fix garbled maths, or change its look (bold, italic, colour, alignment, a hanging indent for bullets, font size). One asking for another language ("put this in Tamil") lands in that language's view, created if needed; the view you were in is unchanged. One asking for the document's own language ("keep it in English") stays in the view.
  - **After an edit** the pages switch to the view it landed in, at the same spot, with the sections still selected and outlined. No toast.
  - **Undo** undoes each selected section's last edit in the view shown (an edit that created a section's translation removes it; a view left empty loses its tab). If some sections fail (a rate limit), only those stay selected, with the prompt still in the box, so sending again tries just them.
- **The selection toolbar:** highlight colours, Comment, Define and **Translate** (primary). Highlights are made on any view and show only on that view. It is centred under the selection but kept 8px inside the window.
- **The left sidebar** sits beside the pages from 1400px wide, and slides over them below that. Its tabs are Contents, Pages, Search, Notes and Glossary (no counts). Notes are grouped under a `.kicker` per view (Original first, then languages by name); clicking one shows its view. **Add text box** at the top of Notes switches to the Original view (closing the slide-over) and places a text box where the page is next clicked ("Click on the page…" meanwhile; Escape cancels).
- **Collapsing:** the top bar's menu button and **Translations** button show and hide the two panels: collapsing them when they sit beside the pages (remembered), opening and closing them when they slide over. The panel's × does the same.
- **Browser Back** returns from a document to the library (opening one adds a history entry); Forward reopens it.
- **Shared code:** the translated page is drawn by `backend/pipeline/render.py` with `backend/static/render.css` and `fit.js` (text shrinks to fit its box, down to 55%). Interaction outlines (selected, picked, Shift held) are studio-only, in `frontend/src/styles/index.css`.
- **Pages** have no captions; a scanned page waiting for OCR gets one line ("Scanned page" and **Run OCR**).
