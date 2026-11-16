import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import '@xyflow/react/dist/style.css'
import './styles.css'
import './error.css'
import './approval.css'
import './management.css'
import './assistant.css'
import './run-detail.css'
import './acceptance.css'
import './review.css'
import './knowledge.css'
import './global-layout.css'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary><BrowserRouter><App /></BrowserRouter></ErrorBoundary>
  </StrictMode>,
)

