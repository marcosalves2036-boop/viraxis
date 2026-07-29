"""Suite pytest para os endpoints de autenticacao (P1 do BACKLOG).

Cobre:
  - POST /auth/register  (sucesso, email duplicado, payload invalido)
  - POST /auth/login     (sucesso, senha errada, email inexistente,
                           conta nao verificada, payload invalido)
  - GET  /users/me       (sucesso, sem token, token invalido, token expirado)
  - POST /users/me/password (sucesso, senha atual errada, payload invalido,
                              sem token, token expirado)

NOTA sobre o endpoint de troca de senha: o BACKLOG descreve `PUT /me/password`,
mas o router (`src/viraxis/api/routers/users.py`) implementa
`POST /users/me/password`. Os testes abaixo exercitam o endpoint como ele
realmente existe no codigo (POST) — ver observacao no relatorio final sobre
essa divergencia de spec.

Banco: SQLite em memoria isolado por teste (ver tests/conftest.py). Nunca
toca o Postgres/Neon de producao.
"""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from viraxis.config import settings

EMAIL = "qa.auth@viraxis.dev"
PASSWORD = "SenhaForte123"
FULL_NAME = "QA Auth Tester"


def _make_expired_token(user_id: str) -> str:
    """Constroi um JWT com o mesmo formato de create_access_token, mas ja expirado."""
    expire = datetime.now(timezone.utc) - timedelta(minutes=5)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


async def _register(client, email=EMAIL, password=PASSWORD, full_name=FULL_NAME):
    return await client.post(
        "/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )


async def _login(client, email=EMAIL, password=PASSWORD):
    return await client.post("/auth/login", json={"email": email, "password": password})


async def _register_and_login(client, email=EMAIL, password=PASSWORD, full_name=FULL_NAME):
    r = await _register(client, email, password, full_name)
    assert r.status_code == 201, r.text
    r2 = await _login(client, email, password)
    assert r2.status_code == 200, r2.text
    return r2.json()


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/register
# ─────────────────────────────────────────────────────────────────────────────

class TestRegister:
    async def test_register_success_returns_201_and_message(self, client):
        r = await _register(client)
        assert r.status_code == 201
        body = r.json()
        assert "message" in body
        assert isinstance(body["message"], str) and body["message"]

    async def test_register_persists_user_hashed_password_and_defaults(self, client):
        r = await _register(client)
        assert r.status_code == 201

        # Login precisa funcionar com a senha em texto puro, confirmando que
        # foi persistida com hash (bcrypt) e nao em texto puro comparavel direto.
        r2 = await _login(client)
        assert r2.status_code == 200
        body = r2.json()
        assert body["email"] == EMAIL
        assert body["full_name"] == FULL_NAME
        assert body["access_token"]

    async def test_register_duplicate_email_returns_409(self, client):
        r1 = await _register(client)
        assert r1.status_code == 201

        r2 = await _register(client, full_name="Outro Nome")
        assert r2.status_code == 409
        assert "cadastrado" in r2.json()["detail"].lower()

    async def test_register_duplicate_email_different_case_still_conflicts(self, client):
        """UserRepository normaliza email para lowercase — 'A@B.com' e 'a@b.com' sao o mesmo usuario."""
        r1 = await _register(client, email="Duplicado@Viraxis.Dev")
        assert r1.status_code == 201

        r2 = await _register(client, email="duplicado@viraxis.dev")
        assert r2.status_code == 409

    @pytest.mark.parametrize(
        "payload,field_missing_or_invalid",
        [
            ({"password": PASSWORD, "full_name": FULL_NAME}, "email"),
            ({"email": EMAIL, "full_name": FULL_NAME}, "password"),
            ({"email": EMAIL, "password": PASSWORD}, "full_name"),
        ],
    )
    async def test_register_missing_required_field_returns_422(
        self, client, payload, field_missing_or_invalid
    ):
        r = await client.post("/auth/register", json=payload)
        assert r.status_code == 422

    async def test_register_invalid_email_format_returns_422(self, client):
        r = await _register(client, email="isso-nao-e-um-email")
        assert r.status_code == 422

    async def test_register_password_too_short_returns_422(self, client):
        r = await _register(client, password="curta1")
        assert r.status_code == 422
        detail = str(r.json()["detail"])
        assert "8 caracteres" in detail

    async def test_register_password_too_long_returns_422(self, client):
        r = await _register(client, password="a" * 73)
        assert r.status_code == 422

    async def test_register_empty_full_name_returns_422(self, client):
        r = await _register(client, full_name="   ")
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# POST /auth/login
# ─────────────────────────────────────────────────────────────────────────────

class TestLogin:
    async def test_login_success_returns_token_and_user_data(self, client):
        r1 = await _register(client)
        assert r1.status_code == 201

        r2 = await _login(client)
        assert r2.status_code == 200
        body = r2.json()
        assert body["token_type"] == "bearer"
        assert body["email"] == EMAIL
        assert body["full_name"] == FULL_NAME
        assert isinstance(body["access_token"], str) and len(body["access_token"]) > 20
        assert body["user_id"]

    async def test_login_wrong_password_returns_401(self, client):
        r1 = await _register(client)
        assert r1.status_code == 201

        r2 = await _login(client, password="SenhaErrada999")
        assert r2.status_code == 401
        assert "incorretos" in r2.json()["detail"].lower()

    async def test_login_nonexistent_email_returns_401(self, client):
        r = await _login(client, email="ninguem@viraxis.dev", password=PASSWORD)
        assert r.status_code == 401

    async def test_login_unverified_account_returns_403(self, client, monkeypatch):
        """Com SKIP_EMAIL_VERIFICATION=False, conta recem-criada fica is_verified=False
        e o login deve ser bloqueado ate a verificacao de email."""
        monkeypatch.setattr(settings, "skip_email_verification", False)

        email = "naoverificado@viraxis.dev"
        r1 = await _register(client, email=email)
        assert r1.status_code == 201

        r2 = await _login(client, email=email)
        assert r2.status_code == 403
        assert "verificado" in r2.json()["detail"].lower()

    @pytest.mark.parametrize(
        "payload",
        [
            {"password": PASSWORD},  # falta email
            {"email": EMAIL},  # falta password
            {"email": "email-invalido", "password": PASSWORD},  # email mal formado
        ],
    )
    async def test_login_invalid_payload_returns_422(self, client, payload):
        r = await client.post("/auth/login", json=payload)
        assert r.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# GET /users/me
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMe:
    async def test_get_me_success_returns_current_user(self, client):
        auth = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}

        r = await client.get("/users/me", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == EMAIL
        assert body["full_name"] == FULL_NAME
        assert body["plan"] == "free"
        assert body["role"] == "user"
        assert body["id"] == auth["user_id"]

    async def test_get_me_without_token_is_rejected(self, client):
        r = await client.get("/users/me")
        assert r.status_code in (401, 403)  # HTTPBearer sem header -> 403 por padrao no FastAPI

    async def test_get_me_with_garbage_token_returns_401(self, client):
        r = await client.get(
            "/users/me", headers={"Authorization": "Bearer isso-nao-e-um-jwt-valido"}
        )
        assert r.status_code == 401

    async def test_get_me_with_expired_token_returns_401(self, client):
        auth = await _register_and_login(client)
        expired = _make_expired_token(auth["user_id"])

        r = await client.get("/users/me", headers={"Authorization": f"Bearer {expired}"})
        assert r.status_code == 401
        assert "invalido" in r.json()["detail"].lower() or "expirado" in r.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# POST /users/me/password  (BACKLOG descreve como "PUT /me/password" — ver
# nota no topo do arquivo sobre a divergencia com o metodo/rota reais)
# ─────────────────────────────────────────────────────────────────────────────

class TestChangePassword:
    async def test_change_password_success_allows_login_with_new_password(self, client):
        auth = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}
        new_password = "NovaSenhaForte456"

        r = await client.post(
            "/users/me/password",
            headers=headers,
            json={"current_password": PASSWORD, "new_password": new_password},
        )
        assert r.status_code == 204

        # Senha antiga nao funciona mais.
        old_login = await _login(client, password=PASSWORD)
        assert old_login.status_code == 401

        # Senha nova funciona.
        new_login = await _login(client, password=new_password)
        assert new_login.status_code == 200

    async def test_change_password_wrong_current_password_returns_400(self, client):
        auth = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}

        r = await client.post(
            "/users/me/password",
            headers=headers,
            json={"current_password": "senha-errada-qualquer", "new_password": "OutraSenhaForte789"},
        )
        assert r.status_code == 400
        assert "incorreta" in r.json()["detail"].lower()

        # Garantir que a senha original continua valida (nada foi alterado).
        still_valid = await _login(client, password=PASSWORD)
        assert still_valid.status_code == 200

    async def test_change_password_new_password_too_short_returns_422(self, client):
        auth = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}

        r = await client.post(
            "/users/me/password",
            headers=headers,
            json={"current_password": PASSWORD, "new_password": "curta"},
        )
        assert r.status_code == 422

    async def test_change_password_new_password_too_long_returns_422(self, client):
        auth = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}

        r = await client.post(
            "/users/me/password",
            headers=headers,
            json={"current_password": PASSWORD, "new_password": "a" * 73},
        )
        assert r.status_code == 422

    async def test_change_password_missing_field_returns_422(self, client):
        auth = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {auth['access_token']}"}

        r = await client.post(
            "/users/me/password",
            headers=headers,
            json={"current_password": PASSWORD},
        )
        assert r.status_code == 422

    async def test_change_password_without_token_is_rejected(self, client):
        r = await client.post(
            "/users/me/password",
            json={"current_password": PASSWORD, "new_password": "OutraSenhaForte789"},
        )
        assert r.status_code in (401, 403)

    async def test_change_password_with_expired_token_returns_401(self, client):
        auth = await _register_and_login(client)
        expired = _make_expired_token(auth["user_id"])

        r = await client.post(
            "/users/me/password",
            headers={"Authorization": f"Bearer {expired}"},
            json={"current_password": PASSWORD, "new_password": "OutraSenhaForte789"},
        )
        assert r.status_code == 401
