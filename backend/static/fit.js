// Fit each block's text into its original box. Shared by the studio view and the PDF export.
//   data-fit="shrink": start at the original font size (data-size)
//   data-fit="fill":   size unknown or unreliable (OCR, scans): largest size up to data-max that fits
// A longer translation keeps as much of its size as it can:
//   1. the original size and line height, in the original box
//   2. the box grown down into the empty space below it (data-room, pt)
//   3. lines tightened, but never below 1.2 (TIGHTEST), then shrinking down to 80%, then to 55%, then to a
//      readable floor (floor(): 40%, not below 5.5pt)
//   4. translated blocks that started alike (data-group) that came out within 10% of their group's median all
//      take the smallest of those sizes, so neighbouring paragraphs match; one that had to shrink more keeps
//      its own size (a wider band left whole pages a fifth empty)
//   5. a block whose lines were tightened gets its original spacing back if it fits at its final size
// Table cells break only between words, so a number shrinks instead of splitting; if a cell still doesn't
// fit at 55% (a URL), it may break anywhere. Past the floor the block gets data-overflow, and render.css clips it
// to its box: text never spills over pictures or other sections (the studio tells the reader which were cut).
// The final ratio is left in data-scale so the studio and the evaluation can flag blocks that were squeezed
// a lot. Fitting again starts over.
var TIGHTEST = 1.2; // var: the studio may load this file again after a renderer change. Line height floor: tighter reads cramped next to the original's 1.3 or so
function dsFit(root) {
  const floor = (start) => Math.min(start * 0.55, Math.max(start * 0.4, 5.5)); // smallest size worth reading
  const fits = (el) => el.scrollHeight <= el.clientHeight + 1 && el.scrollWidth <= el.clientWidth + 1;
  const largest = (el, lo, hi) => { // largest size in [lo, hi] that fits, else lo
    el.style.fontSize = hi + "pt";
    if (fits(el)) return hi;
    while (hi - lo > 0.2) {
      const mid = (lo + hi) / 2;
      el.style.fontSize = mid + "pt";
      if (fits(el)) lo = mid; else hi = mid;
    }
    el.style.fontSize = lo + "pt";
    return lo;
  };
  root = root || document;
  const self = root.matches && root.matches("[data-fit]") ? [root] : [];
  const els = [...self, ...root.querySelectorAll("[data-fit]")];
  els.forEach((el) => {
    if (el.dataset.box === undefined) el.dataset.box = el.style.height + "|" + el.style.lineHeight;
    [el.style.height, el.style.lineHeight] = el.dataset.box.split("|");
    el.style.overflowWrap = "";
    if (el.dataset.fit === "fill") {
      const max = parseFloat(el.dataset.max) || 10, size = parseFloat(el.dataset.size);
      return largest(el, Math.min(4, size ? size * 0.55 : 4), max);
    }
    const start = parseFloat(el.dataset.size) || 10;
    if (largest(el, start, start) === start && fits(el)) return;
    const room = parseFloat(el.dataset.room) || 0;
    if (room) {
      el.style.height = parseFloat(el.style.height) + room + "pt";
      if (largest(el, start, start) === start && fits(el)) return;
    }
    const tightest = parseFloat(el.dataset.tightest) || TIGHTEST; // a tall script's own floor (render.TALL_SCRIPTS)
    if ((parseFloat(el.style.lineHeight) || 1.22) > tightest) el.style.lineHeight = String(tightest);
    const size = largest(el, start * 0.8, start);
    if (!fits(el)) largest(el, start * 0.55, size);
    if (!fits(el) && getComputedStyle(el).overflowWrap === "normal") {
      el.style.overflowWrap = "anywhere"; // a table cell's URL or long word: break it rather than spill over
      largest(el, start * 0.55, start);
    }
    if (!fits(el)) largest(el, floor(start), parseFloat(el.style.fontSize));
  });
  const groups = {};
  els.forEach((el) => {
    const block = el.closest("[data-status]");
    if (el.dataset.group && block && block.dataset.status === "translated") (groups[el.dataset.group] ||= []).push(el);
  });
  Object.values(groups).filter((g) => g.length > 1).forEach((g) => {
    const scale = (el) => parseFloat(el.style.fontSize) / parseFloat(el.dataset.size);
    const scales = g.map(scale).sort((a, b) => a - b);
    const median = scales[Math.floor(scales.length / 2)];
    const common = Math.min(...scales.filter((s) => s >= 0.9 * median)); // outliers keep their own size
    g.forEach((el) => {
      if (scale(el) > common + 0.005) el.style.fontSize = parseFloat(el.dataset.size) * common + "pt";
      // Wrapping around a picture (.ds-wrap-*) isn't monotonic: a smaller size can need one more line.
      if (!fits(el)) largest(el, floor(parseFloat(el.dataset.size)), parseFloat(el.style.fontSize));
    });
  });
  els.forEach((el) => {
    const original = (el.dataset.box || "").split("|")[1];
    if (original && el.style.lineHeight !== original) { // tightened, but its final size may not need it
      const tight = el.style.lineHeight;
      el.style.lineHeight = original;
      if (!fits(el)) el.style.lineHeight = tight;
    }
    const size = parseFloat(el.style.fontSize);
    el.style.fontSize = size.toFixed(2) + "pt";
    el.dataset.scale = (size / (parseFloat(el.dataset.size) || parseFloat(el.dataset.max) || 10)).toFixed(3);
    if (fits(el)) delete el.dataset.overflow; else el.dataset.overflow = "1";
  });
}
if (typeof window !== "undefined") window.dsFit = dsFit;
