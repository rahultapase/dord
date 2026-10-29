import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Fonts are bundled (SIL Open Font License); nothing is fetched from the internet.
import '@fontsource/im-fell-english/400.css'
import '@fontsource/im-fell-english/400-italic.css'
import '@fontsource/im-fell-english-sc/400.css'
import '@fontsource/eb-garamond/400.css'
import '@fontsource/eb-garamond/400-italic.css'
import '@fontsource/eb-garamond/600.css'
import './styles/base.css'
import './styles/paper.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
