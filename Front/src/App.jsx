import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import ProcessList from './pages/ProcessList'
import NewProcess from './pages/NewProcess'
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
          <Route path="processes" element={<ProcessList />} />
          <Route path="processes/new" element={<NewProcess />} />
          <Route path="processes/:id" element={<ProcessDetail />} />
          <Route path="processes/:id/results" element={<Results />} />
          <Route path="sftp" element={<SftpModule />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
