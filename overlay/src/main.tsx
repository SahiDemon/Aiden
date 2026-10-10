import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import OverlayPreview from './OverlayPreview.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {import.meta.env.DEV && new URLSearchParams(window.location.search).has('preview') ? <OverlayPreview /> : <App />}
  </StrictMode>,
)
