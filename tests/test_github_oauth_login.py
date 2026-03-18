from __future__ import annotations

import os
from urllib.parse import parse_qs, quote, urlsplit

import pytest
from fastapi.testclient import TestClient

from app.config import reload_settings
from app.main import app
from app.database import get_db


@pytest.fixture()
def hosted_github_client(tmp_path):
    db_path = tmp_path / 'test.db'

    orig_env = {}
    env_overrides = {
        'DEPLOY_MODE': 'hosted',
        'INVITE_CODE': 'TEST-CODE-123',
        'JWT_SECRET_KEY': 'test-secret-key-for-hosted-mode-32b',
        'INITIAL_QUOTA': '5',
        'FEEDBACK_BONUS_QUOTA': '20',
        'GITHUB_OAUTH_CLIENT_ID': 'github-client-id',
        'GITHUB_OAUTH_CLIENT_SECRET': 'github-client-secret',
    }
    for key, val in env_overrides.items():
        orig_env[key] = os.environ.get(key)
        os.environ[key] = val
    reload_settings()

    saved_overrides = dict(app.dependency_overrides)
    app.dependency_overrides.clear()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base

    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)
    yield client

    for key, orig_val in orig_env.items():
        if orig_val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = orig_val

    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved_overrides)
    reload_settings()


def _begin_github_oauth(client: TestClient, *, redirect_to: str | None = None) -> str:
    url = '/api/auth/github/start'
    if redirect_to is not None:
        url = f"{url}?redirect_to={quote(redirect_to, safe='')}"
    resp = client.get(url, follow_redirects=False)
    assert resp.status_code == 302

    parsed = urlsplit(resp.headers['location'])
    assert parsed.scheme == 'https'
    assert parsed.netloc == 'github.com'
    assert parsed.path == '/login/oauth/authorize'

    params = parse_qs(parsed.query)
    assert params['client_id'] == ['github-client-id']
    assert params['scope'] == ['read:user']
    assert params['code_challenge_method'] == ['S256']
    return params['state'][0]


def _mock_github_identity(monkeypatch, *, provider_user_id: str, login: str, display_name: str, email: str | None = None):
    import app.api.auth as auth_api

    def fake_exchange_github_code_for_identity(*, request, code: str, code_verifier: str):
        assert code
        assert code_verifier
        return auth_api.GitHubOAuthIdentity(
            provider_user_id=provider_user_id,
            login=login,
            display_name=display_name,
            email=email,
        )

    monkeypatch.setattr(auth_api, 'exchange_github_code_for_identity', fake_exchange_github_code_for_identity)


class TestGitHubOAuthLogin:
    def test_first_github_login_creates_hosted_user_and_session(self, hosted_github_client, monkeypatch):
        from app.core.auth import AUTH_PROVIDER_GITHUB, AUTH_PROVIDER_INVITE, SESSION_COOKIE_NAME
        from app.models import AuthIdentity, User

        _mock_github_identity(
            monkeypatch,
            provider_user_id='12345',
            login='octocat',
            display_name='The Octocat',
            email='octocat@example.com',
        )
        state = _begin_github_oauth(hosted_github_client, redirect_to='/novel/7?stage=write')

        callback_resp = hosted_github_client.get(
            f'/api/auth/github/callback?code=test-code&state={quote(state, safe="")}',
            follow_redirects=False,
        )
        assert callback_resp.status_code == 303
        assert callback_resp.headers['location'] == '/novel/7?stage=write'
        assert SESSION_COOKIE_NAME in callback_resp.cookies

        me_resp = hosted_github_client.get('/api/auth/me')
        assert me_resp.status_code == 200
        user = me_resp.json()
        assert user['nickname'] == 'The Octocat'
        assert user['generation_quota'] == 5

        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            db_user = db.query(User).filter(User.id == user['id']).one()
            identities = (
                db.query(AuthIdentity)
                .filter(AuthIdentity.user_id == db_user.id)
                .order_by(AuthIdentity.provider.asc())
                .all()
            )
            assert [(identity.provider, identity.provider_user_id) for identity in identities] == [
                (AUTH_PROVIDER_GITHUB, '12345'),
                (AUTH_PROVIDER_INVITE, 'The Octocat'),
            ]

            github_identity = (
                db.query(AuthIdentity)
                .filter(AuthIdentity.user_id == db_user.id, AuthIdentity.provider == AUTH_PROVIDER_GITHUB)
                .one()
            )
            assert github_identity.provider_user_id == '12345'
            assert github_identity.provider_login == 'octocat'
            assert github_identity.provider_email == 'octocat@example.com'
            assert github_identity.last_login_at is not None
        finally:
            db.close()

    def test_repeat_github_login_resolves_same_user_and_preserves_quota(self, hosted_github_client, monkeypatch):
        from app.core.auth import decrement_quota
        from app.models import AuthIdentity, User

        _mock_github_identity(
            monkeypatch,
            provider_user_id='12345',
            login='octocat',
            display_name='The Octocat',
            email='octocat@example.com',
        )
        first_state = _begin_github_oauth(hosted_github_client)
        first_callback = hosted_github_client.get(
            f'/api/auth/github/callback?code=first-code&state={quote(first_state, safe="")}',
            follow_redirects=False,
        )
        assert first_callback.status_code == 303

        first_me = hosted_github_client.get('/api/auth/me')
        user_id = first_me.json()['id']

        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            user = db.query(User).filter(User.id == user_id).one()
            decrement_quota(db, user, count=2)
        finally:
            db.close()

        _mock_github_identity(
            monkeypatch,
            provider_user_id='12345',
            login='octocat-renamed',
            display_name='Renamed Octocat',
            email='octocat+new@example.com',
        )
        second_state = _begin_github_oauth(hosted_github_client)
        second_callback = hosted_github_client.get(
            f'/api/auth/github/callback?code=second-code&state={quote(second_state, safe="")}',
            follow_redirects=False,
        )
        assert second_callback.status_code == 303
        assert second_callback.headers['location'] == '/library'

        second_me = hosted_github_client.get('/api/auth/me')
        assert second_me.status_code == 200
        second_user = second_me.json()
        assert second_user['id'] == user_id
        assert second_user['generation_quota'] == 3

        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            identity = (
                db.query(AuthIdentity)
                .filter(AuthIdentity.provider == 'github', AuthIdentity.provider_user_id == '12345')
                .one()
            )
            assert identity.user_id == user_id
            assert identity.provider_login == 'octocat-renamed'
            assert identity.provider_email == 'octocat+new@example.com'
        finally:
            db.close()

    def test_callback_redirect_rejects_open_redirect_targets(self, hosted_github_client, monkeypatch):
        _mock_github_identity(
            monkeypatch,
            provider_user_id='12345',
            login='octocat',
            display_name='The Octocat',
        )
        state = _begin_github_oauth(hosted_github_client, redirect_to='https://evil.example/phish')

        callback_resp = hosted_github_client.get(
            f'/api/auth/github/callback?code=test-code&state={quote(state, safe="")}',
            follow_redirects=False,
        )
        assert callback_resp.status_code == 303
        assert callback_resp.headers['location'] == '/library'

    def test_callback_rejects_invalid_state_without_authenticating(self, hosted_github_client, monkeypatch):
        _mock_github_identity(
            monkeypatch,
            provider_user_id='12345',
            login='octocat',
            display_name='The Octocat',
        )
        state = _begin_github_oauth(hosted_github_client)

        callback_resp = hosted_github_client.get(
            f'/api/auth/github/callback?code=test-code&state={quote(state + "-tampered", safe="")}',
            follow_redirects=False,
        )
        assert callback_resp.status_code == 303
        assert callback_resp.headers['location'].startswith('/login?')
        assert 'oauth_error=github_oauth_state_invalid' in callback_resp.headers['location']

        me_resp = hosted_github_client.get('/api/auth/me')
        assert me_resp.status_code == 401

    def test_github_created_user_can_recover_via_invite_fallback_identity(self, hosted_github_client, monkeypatch):
        from app.core.auth import decrement_quota
        from app.models import AuthIdentity, User

        _mock_github_identity(
            monkeypatch,
            provider_user_id='77777',
            login='rollback-cat',
            display_name='回滚用户',
            email='rollback@example.com',
        )
        github_state = _begin_github_oauth(hosted_github_client)
        github_callback = hosted_github_client.get(
            f'/api/auth/github/callback?code=test-code&state={quote(github_state, safe="")}',
            follow_redirects=False,
        )
        assert github_callback.status_code == 303
        github_user_id = hosted_github_client.get('/api/auth/me').json()['id']

        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            user = db.query(User).filter(User.id == github_user_id).one()
            decrement_quota(db, user, count=2)
        finally:
            db.close()

        hosted_github_client.post('/api/auth/logout')
        invite_relogin = hosted_github_client.post(
            '/api/auth/invite',
            json={'invite_code': 'TEST-CODE-123', 'nickname': '回滚用户'},
        )
        assert invite_relogin.status_code == 201

        recovered_user = hosted_github_client.get('/api/auth/me').json()
        assert recovered_user['id'] == github_user_id
        assert recovered_user['generation_quota'] == 3

        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            identities = (
                db.query(AuthIdentity)
                .filter(AuthIdentity.user_id == github_user_id)
                .order_by(AuthIdentity.provider.asc())
                .all()
            )
            assert [(identity.provider, identity.provider_user_id) for identity in identities] == [
                ('github', '77777'),
                ('invite', '回滚用户'),
            ]
        finally:
            db.close()

    def test_github_signup_rejects_visible_name_owned_by_existing_invite_identity(self, hosted_github_client, monkeypatch):
        from app.models import AuthIdentity, User

        invite_resp = hosted_github_client.post(
            '/api/auth/invite',
            json={'invite_code': 'TEST-CODE-123', 'nickname': '共享用户'},
        )
        assert invite_resp.status_code == 201
        invite_user_id = hosted_github_client.get('/api/auth/me').json()['id']

        hosted_github_client.post('/api/auth/logout')

        _mock_github_identity(
            monkeypatch,
            provider_user_id='99999',
            login='octocat',
            display_name='共享用户',
            email='octocat@example.com',
        )
        github_state = _begin_github_oauth(hosted_github_client)
        github_callback = hosted_github_client.get(
            f'/api/auth/github/callback?code=test-code&state={quote(github_state, safe="")}',
            follow_redirects=False,
        )
        assert github_callback.status_code == 303
        assert github_callback.headers['location'].startswith('/login?')
        assert 'oauth_error=github_oauth_failed' in github_callback.headers['location']

        me_resp = hosted_github_client.get('/api/auth/me')
        assert me_resp.status_code == 401

        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            users = db.query(User).order_by(User.id.asc()).all()
            identities = db.query(AuthIdentity).order_by(AuthIdentity.provider.asc()).all()
            assert [user.id for user in users] == [invite_user_id]
            assert [(identity.provider, identity.user_id) for identity in identities] == [
                ('invite', invite_user_id),
            ]
        finally:
            db.close()
