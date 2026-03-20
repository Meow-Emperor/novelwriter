// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Outlet, Navigate, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import { PerformanceModeProvider } from '@/contexts/PerformanceModeContext'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { PageShell } from '@/components/layout/PageShell'
import { Home } from '@/pages/Home'

const Login = lazy(() => import('@/pages/Login'))
const Settings = lazy(() => import('@/pages/Settings'))
const Terms = lazy(() => import('@/pages/Terms'))
const Privacy = lazy(() => import('@/pages/Privacy'))
const CopyrightNotice = lazy(() => import('@/pages/CopyrightNotice'))
const LibraryPage = lazy(() => import('@/pages/LibraryPage').then((module) => ({ default: module.LibraryPage })))
const NovelStudioPage = lazy(() => import('@/pages/NovelStudioPage').then((module) => ({ default: module.NovelStudioPage })))
const GenerationResults = lazy(() => import('@/pages/GenerationResults').then((module) => ({ default: module.GenerationResults })))
const NovelAtlasPage = lazy(() => import('@/pages/NovelAtlasPage').then((module) => ({ default: module.NovelAtlasPage })))
const NovelShell = lazy(() => import('@/components/novel-shell/NovelShell').then((module) => ({ default: module.NovelShell })))

const queryClient = new QueryClient()

/** Shared shell (animated background + navbar). */
function Layout() {
  const { pathname } = useLocation()
  const isWorld = pathname.startsWith('/world/')
  return (
    <PageShell
      // Atlas manages its own full-height layout + scroll containers.
      // Make the shell fixed-height to avoid the whole page scrolling when sidebars overflow.
      showNavbar={!isWorld}
      className={isWorld ? 'h-screen overflow-hidden' : undefined}
      mainClassName={isWorld ? 'min-h-0 overflow-hidden' : undefined}
    >
      <Outlet />
    </PageShell>
  )
}

function RequireAuth() {
  const { isLoggedIn, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) return null
  if (!isLoggedIn) {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />
  }
  return <Outlet />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <UiLocaleProvider>
        <BrowserRouter>
          <PerformanceModeProvider>
            <AuthProvider>
              <Suspense fallback={null}>
                <Routes>
                  {/* Old-layout pages */}
                  <Route element={<Layout />}>
                    <Route path="/" element={<Home />} />
                    <Route path="/terms" element={<Terms />} />
                    <Route path="/privacy" element={<Privacy />} />
                    <Route path="/copyright" element={<CopyrightNotice />} />
                    <Route element={<RequireAuth />}>
                      <Route path="/settings" element={<Settings />} />
                    </Route>
                  </Route>

                  <Route element={<RequireAuth />}>
                    <Route path="/library" element={<LibraryPage />} />
                    {/* Novel routes share one Studio/Atlas shell so shell state and agent sessions survive surface switches. */}
                    <Route element={<NovelShell />}>
                      <Route element={<Layout />}>
                        <Route path="/world/:novelId" element={<NovelAtlasPage />} />
                      </Route>
                      <Route path="/novel/:novelId" element={<NovelStudioPage />} />
                      <Route path="/novel/:novelId/chapter/:chapterNum/results" element={<GenerationResults />} />
                    </Route>
                  </Route>
                  {/* Login (standalone) */}
                  <Route path="/login" element={<Login />} />
                </Routes>
              </Suspense>
            </AuthProvider>
          </PerformanceModeProvider>
        </BrowserRouter>
      </UiLocaleProvider>
    </QueryClientProvider>
  )
}
