import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import Layout from './components/Layout'
import EvaluationPage from './pages/EvaluationPage'
import DiffPage from './pages/DiffPage'
import ChatPage from './pages/ChatPage'
import ArchivePage from './pages/ArchivePage'
import SettingsPage from './pages/SettingsPage'
import InitializationPage from './pages/InitializationPage'
import CostsPage from './pages/CostsPage'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout><EvaluationPage /></Layout>} />
          <Route path="/diff" element={<Layout><DiffPage /></Layout>} />
          <Route path="/chat" element={<Layout><ChatPage /></Layout>} />
          <Route path="/archive" element={<Layout><ArchivePage /></Layout>} />
          <Route path="/settings" element={<Layout><SettingsPage /></Layout>} />
          <Route path="/init" element={<Layout><InitializationPage /></Layout>} />
          <Route path="/costs" element={<Layout><CostsPage /></Layout>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
