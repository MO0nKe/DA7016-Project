// fit.js (served by the backend, loaded by index.html) fits rendered text into its boxes.
declare global {
  interface Window { dsFit?: (root: Element | Document) => void }
}

export {}
