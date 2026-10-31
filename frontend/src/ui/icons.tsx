// A few 16px line icons (inline SVG, so no icon library is needed). They inherit the text colour.

const icon = (d: string, size = 16) => (props: { className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden className={props.className}>
    <path d={d} />
  </svg>
)

export const FolderIcon = icon('M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z')
export const UploadIcon = icon('M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2', 20)
export const MenuIcon = icon('M4 6h16M4 12h16M4 18h16')
export const ChevronLeftIcon = icon('m15 18-6-6 6-6')
export const ChevronRightIcon = icon('m9 18 6-6-6-6')
export const ChevronDownIcon = icon('m6 9 6 6 6-6')
export const CheckIcon = icon('m5 12 5 5 9-10')
export const TranslateIcon = icon('M4 5h8M8 3v2m2.5 0C10 9 7 12 4 13m3-4c1 2 3 3.5 5 4m1 8 4-10 4 10m-1.5-3.5h-5')
export const DownloadIcon = icon('M12 4v12m0 0-4-4m4 4 4-4M4 20h16')
export const CloseIcon = icon('M6 6l12 12M18 6 6 18')
export const PencilIcon = icon('M4 20h4L19 9l-4-4L4 16zM14 6l4 4')
export const UndoIcon = icon('M9 14 4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3')
export const CopyIcon = icon('M9 9h10v10H9zM5 15V5h10')
export const EyeIcon = icon('M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6z')
export const TrashIcon = icon('M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3')
export const TextIcon = icon('M5 6V4h14v2M12 4v16m-3 0h6')
export const SparkleIcon = icon('M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z')
export const LanguagesIcon = icon('M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0m0 0h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3')
export const PinIcon = icon('M12 17v5M8 3h8l-1 6 3 4H6l3-4z')
export const FolderPlusIcon = icon('M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zm9 3v6m-3-3h6')
export const FilePlusIcon = icon('M14 3H6v18h12V7zm0 0v4h4M12 11v6m-3-3h6')
export const LibraryIcon = icon('M4 4v16M8 4v16M12 4l4 16M17 4h3v16h-3z')
export const SearchIcon = icon('M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zm9 2-4-4')
export const SendIcon = icon('M12 19V5m0 0-6 6m6-6 6 6')
export const ListIcon = icon('M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01')
export const GridIcon = icon('M4 4h7v7H4zm9 0h7v7h-7zM4 13h7v7H4zm9 0h7v7h-7z')
