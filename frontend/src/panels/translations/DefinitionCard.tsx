import { useEffect, useState } from 'react'
import { api, type Definition } from '../../api'

/** Offline English dictionary entry (WordNet). */
export default function DefinitionCard({ word }: { word: string }) {
  const [entry, setEntry] = useState<Definition | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {  // keyed by its word, so it starts empty for each
    api.define(word).then(setEntry).catch((e) => setError(e.message))
  }, [word])

  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <h3 className="text-base font-semibold text-ink">{entry?.lemma ?? word}</h3>
        {entry && entry.lemma !== entry.word && <span className="text-xs text-muted">from “{entry.word}”</span>}
      </div>
      {!entry && !error && <p className="text-xs text-muted">Looking up…</p>}
      {error && <p className="text-xs text-rose-600">{error}</p>}
      {entry && entry.senses.length === 0 && <p className="text-xs text-muted">No dictionary entry for “{word}”.</p>}
      <ol className="space-y-2 list-decimal list-inside">
        {entry?.senses.map((s, i) => (
          <li key={i} className="text-sm text-ink">
            <span className="text-xs italic text-muted mr-1">{s.pos}</span>{s.definition}
            {s.examples[0] && <p className="ml-5 text-xs text-muted">“{s.examples[0]}”</p>}
            {s.synonyms.length > 0 && <p className="ml-5 text-xs text-muted">Similar: {s.synonyms.join(', ')}</p>}
          </li>
        ))}
      </ol>
    </div>
  )
}
