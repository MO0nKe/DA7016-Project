import { useEffect, useState } from 'react'
import { useMedia } from '../../lib/hooks'

/** The two side panels: beside the pages on wide screens (collapsible, remembered across documents), sliding over
 *  them on narrow ones. */
export function usePanels() {
  const leftInline = useMedia('(min-width: 1400px)')
  const rightInline = useMedia('(min-width: 1100px)')
  const [leftOpen, setLeftOpen] = useState(false)  // narrow screens: sliding over the pages
  const [rightOpen, setRightOpen] = useState(false)
  const [leftCollapsed, setLeftCollapsed] = useState(() => localStorage.getItem('leftCollapsed') === '1')
  const [rightCollapsed, setRightCollapsed] = useState(() => localStorage.getItem('rightCollapsed') === '1')
  useEffect(() => { localStorage.setItem('leftCollapsed', leftCollapsed ? '1' : '0') }, [leftCollapsed])
  useEffect(() => { localStorage.setItem('rightCollapsed', rightCollapsed ? '1' : '0') }, [rightCollapsed])

  return {
    leftInline, rightInline,
    leftShown: leftInline ? !leftCollapsed : leftOpen,
    rightShown: rightInline ? !rightCollapsed : rightOpen,
    sliding: (!leftInline && leftOpen) || (!rightInline && rightOpen),  // a panel covers the pages
    toggleLeft: () => (leftInline ? setLeftCollapsed(!leftCollapsed) : setLeftOpen(!leftOpen)),
    toggleRight: () => (rightInline ? setRightCollapsed(!rightCollapsed) : setRightOpen(!rightOpen)),
    showLeft: () => { setLeftOpen(true); setLeftCollapsed(false) },
    showRight: () => { setRightOpen(true); setRightCollapsed(false) },
    slideRightOpen: () => setRightOpen(true),
    /** After choosing something in the left panel: a sliding panel gets out of the way. */
    leftDone: () => { if (!leftInline) setLeftOpen(false) },
    closeSliding: () => { setLeftOpen(false); setRightOpen(false) },
  }
}
