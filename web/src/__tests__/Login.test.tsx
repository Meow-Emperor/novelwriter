import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const {
  loginMock,
  inviteRegisterMock,
  getGitHubLoginUrlMock,
} = vi.hoisted(() => ({
  loginMock: vi.fn(),
  inviteRegisterMock: vi.fn(),
  getGitHubLoginUrlMock: vi.fn((redirectTo: string) => `/api/auth/github/start?redirect_to=${encodeURIComponent(redirectTo)}`),
}))

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({
    login: loginMock,
    inviteRegister: inviteRegisterMock,
  }),
}))

vi.mock('@/hooks/useConfirmDialog', () => ({
  useConfirmDialog: () => ({
    alert: vi.fn(),
    dialogProps: {},
  }),
}))

vi.mock('@/components/ui/confirm-dialog', () => ({
  ConfirmDialog: () => null,
}))

vi.mock('@/components/layout/AnimatedBackground', () => ({
  AnimatedBackground: () => <div data-testid="animated-background" />,
}))

vi.mock('@/services/api', () => ({
  api: {
    login: loginMock,
    inviteRegister: inviteRegisterMock,
    getGitHubLoginUrl: getGitHubLoginUrlMock,
  },
  ApiError: class ApiError extends Error {
    status = 500
    code?: string
    requestId?: string
  },
}))

import Login, { getOAuthErrorMessage, getPostLoginDestination } from '@/pages/Login'

describe('Login', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubEnv('VITE_DEPLOY_MODE', 'hosted')
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('keeps only safe post-login destinations', () => {
    expect(getPostLoginDestination({ from: '/novel/1?stage=write' })).toBe('/novel/1?stage=write')
    expect(getPostLoginDestination({ from: 'https://evil.example/phish' })).toBe('/library')
    expect(getPostLoginDestination({ from: '//evil.example/phish' })).toBe('/library')
    expect(getPostLoginDestination(null, '?redirect_to=%2Fworld%2F7')).toBe('/world/7')
    expect(getPostLoginDestination(null, '?redirect_to=https%3A%2F%2Fevil.example')).toBe('/library')
  })

  it('maps GitHub OAuth callback errors to user-facing copy', () => {
    expect(getOAuthErrorMessage('github_oauth_state_invalid')).toContain('登录状态已失效')
    expect(getOAuthErrorMessage('github_oauth_signup_blocked')).toContain('暂不接受新的 GitHub 注册')
    expect(getOAuthErrorMessage(null)).toBeNull()
  })

  it('renders the hosted GitHub login entry and preserves the safe redirect target', () => {
    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: '/login',
            search: '?oauth_error=github_oauth_state_invalid&redirect_to=%2Fnovel%2F1',
          },
        ]}
      >
        <Login />
      </MemoryRouter>,
    )

    expect(screen.getByText('登录状态已失效，请重新点击 GitHub 登录。')).toBeVisible()
    expect(screen.getByTestId('login-github-link')).toHaveAttribute(
      'href',
      '/api/auth/github/start?redirect_to=%2Fnovel%2F1',
    )
    expect(getGitHubLoginUrlMock).toHaveBeenCalledWith('/novel/1')
    expect(screen.getByLabelText('邀请码')).toBeVisible()
  })
})
