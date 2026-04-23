import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Contabilidad from './pages/Contabilidad'
import ProcessDetail from './pages/ProcessDetail'
import Results from './pages/Results'
import SftpModule from './pages/SftpModule'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="contabilidad" element={<Contabilidad />} />
          {/* Legacy redirects — /processes and /processes/new now live under Contabilidad */}
          <Route path="processes" element={<Navigate to="/contabilidad" replace />} />
          <Route path="processes/new" element={<Navigate to="/contabilidad" replace />} />
          <Route path="processes/:id" element={<ProcessDetail />} />
          <Route path="processes/:id/results" element={<Results />} />
          <Route path="sftp" element={<SftpModule />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
