import { useEffect, useRef, useState } from 'react'
import { api, type Job } from '../../api'

const POLL_MS = 600

/** The document's running job (a translation, or the structure review that runs on upload), polled until it ends.
 *  A job started elsewhere (on upload, or before the document was closed) is picked up on open. `onEnded` runs once
 *  per finished job; after the structure review, the translation that waited for it is picked up. */
export function useTranslationJob(docId: string, onEnded: (job: Job) => Promise<void>) {
  const [job, setJob] = useState<Job | null>(null)
  const ended = useRef(onEnded)
  useEffect(() => { ended.current = onEnded })

  useEffect(() => { api.documentJob(docId).then((j) => { if (j) setJob(j) }).catch(() => {}) }, [docId])
  useEffect(() => {
    if (job?.status !== 'running') return
    const id = job.id
    const timer = setInterval(async () => {
      const next = await api.job(id).catch(() => null)
      if (!next) return
      setJob(next)
      if (next.status === 'running') return
      await ended.current(next)
      if (next.kind === 'structure') {  // the layout review from upload: a translation may have waited for it
        const waiting = await api.documentJob(docId).catch(() => null)
        if (waiting) setJob(waiting)
      }
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [docId, job?.id, job?.status])

  return { job, setJob }
}
