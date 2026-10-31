import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import '@fontsource-variable/anek-latin'
import '@fontsource-variable/anek-devanagari'
import '@fontsource-variable/anek-bangla'
import '@fontsource-variable/anek-tamil'
import '@fontsource-variable/anek-telugu'
import '@fontsource-variable/anek-kannada'
import '@fontsource-variable/anek-malayalam'
import '@fontsource-variable/anek-gujarati'
import '@fontsource-variable/anek-gurmukhi'
import '@fontsource-variable/anek-odia'
import '@fontsource-variable/source-serif-4'
import './styles/index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
