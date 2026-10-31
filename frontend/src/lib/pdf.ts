// The single place pdf.js is set up. The viewer bundle (TextLayerBuilder) reads the core library
// from globalThis.pdfjsLib when it loads, so set that first and load the viewer afterwards;
// otherwise two copies of pdf.js can end up talking past each other.
import * as pdfjsLib from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import 'pdfjs-dist/web/pdf_viewer.css'

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl
;(globalThis as { pdfjsLib?: typeof pdfjsLib }).pdfjsLib = pdfjsLib

// Image decoders (JBIG2 / CCITT fax in scans, JPEG 2000) load from here; without it scans draw blank.
// shortcut: served by the Vite dev server from node_modules; copy the folder into the build if one is added.
const wasmUrl = '/node_modules/pdfjs-dist/wasm/'
export const getDocument = (src: { url: string }) => pdfjsLib.getDocument({ ...src, wasmUrl })
export const viewer = import('pdfjs-dist/web/pdf_viewer.mjs')
