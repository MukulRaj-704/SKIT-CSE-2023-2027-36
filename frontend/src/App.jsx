import { Navigate, Route, Routes } from 'react-router-dom'

import Layout from './components/Layout.jsx'
import { useAuth } from './auth.jsx'
import AuthPage from './pages/AuthPage.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Resumes from './pages/Resumes.jsx'
import ResumeDetail from './pages/ResumeDetail.jsx'
import JobBoard from './pages/JobBoard.jsx'
import JobDetail from './pages/JobDetail.jsx'
import MyPostings from './pages/MyPostings.jsx'
import Applications from './pages/Applications.jsx'

function RequireAuth({ children }) {
  const { token } = useAuth()
  if (!token) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />

      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Dashboard />} />
        <Route path="/resumes" element={<Resumes />} />
        <Route path="/resumes/:id" element={<ResumeDetail />} />
        <Route path="/jobs" element={<JobBoard />} />
        <Route path="/jobs/:id" element={<JobDetail />} />
        <Route path="/postings" element={<MyPostings />} />
        <Route path="/applications" element={<Applications />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
