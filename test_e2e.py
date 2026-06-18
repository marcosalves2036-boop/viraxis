"""
Teste E2E da API VIRAXIS — roda com a API no ar em localhost:8000
Usage: python test_e2e.py
"""
import asyncio
import httpx

BASE = "http://localhost:8000"
EMAIL = "e2e_test@viraxis.com"
PASSWORD = "Teste@123"


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        print("\n" + "="*55)
        print("VIRAXIS API — Teste E2E")
        print("="*55)

        # 1. Health
        r = await client.get("/health")
        assert r.status_code == 200, f"Health falhou: {r.text}"
        print("✅ GET /health")

        # 2. Register
        r = await client.post("/auth/register", json={
            "email": EMAIL, "password": PASSWORD, "full_name": "E2E Teste"
        })
        if r.status_code == 409:
            print("⚠️  Usuário já existe — pulando registro")
        else:
            assert r.status_code == 201, f"Register falhou: {r.text}"
            print(f"✅ POST /auth/register — user: {r.json()['email']}")

        # 3. Login
        r = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 200, f"Login falhou: {r.text}"
        token = r.json()["access_token"]
        print(f"✅ POST /auth/login — token: {token[:20]}...")
        headers = {"Authorization": f"Bearer {token}"}

        # 4. GET /users/me
        r = await client.get("/users/me", headers=headers)
        assert r.status_code == 200, f"GET /users/me falhou: {r.text}"
        print(f"✅ GET /users/me — {r.json()['full_name']} ({r.json()['plan']})")

        # 5. PATCH /users/me
        r = await client.patch("/users/me", headers=headers, json={"full_name": "E2E Atualizado"})
        assert r.status_code == 200, f"PATCH /users/me falhou: {r.text}"
        print(f"✅ PATCH /users/me — nome: {r.json()['full_name']}")

        # 6. GET /offices (inicial)
        r = await client.get("/offices", headers=headers)
        assert r.status_code == 200, f"GET /offices falhou: {r.text}"
        initial_offices = r.json()
        print(f"✅ GET /offices — {len(initial_offices)} escritórios")

        office_id = None

        if len(initial_offices) == 0:
            # 7. POST /offices
            r = await client.post("/offices", headers=headers, json={
                "name": "Finance Hacks BR",
                "niche": "Finanças pessoais",
                "platforms": ["tiktok", "instagram"],
                "target_audience": "Jovens 20-35 interessados em investimentos",
                "content_style": "educational",
            })
            assert r.status_code == 201, f"POST /offices falhou: {r.text}"
            office = r.json()
            print(f"✅ POST /offices — id: {office['id'][:8]}... nome: {office['name']}")
            office_id = office["id"]

            # 8. Limite Free: tenta criar segundo escritório
            r = await client.post("/offices", headers=headers, json={
                "name": "Segundo Escritório",
                "niche": "Saúde",
                "platforms": ["youtube"],
            })
            assert r.status_code == 402, f"Limite Free não aplicado: {r.status_code}"
            print("✅ Limite Free validado — 402 ao criar 2º escritório")

            # 9. GET /offices com dados
            r = await client.get("/offices", headers=headers)
            assert r.status_code == 200 and len(r.json()) == 1
            print(f"✅ GET /offices após criação — {r.json()[0]['name']}")
        else:
            office_id = initial_offices[0]["id"]
            print(f"⚠️  Usando escritório existente: {initial_offices[0]['name']}")

        # 10. GET /offices/{id}/decisions
        r = await client.get(f"/offices/{office_id}/decisions", headers=headers)
        assert r.status_code == 200, f"GET /offices/{office_id}/decisions falhou: {r.text}"
        decisions = r.json()
        print(f"✅ GET /offices/{{id}}/decisions — {len(decisions)} decisões")

        # 11. PATCH /offices/{id}
        r = await client.patch(f"/offices/{office_id}", headers=headers, json={
            "name": "Finance Hacks BR (editado)",
            "niche": "Finanças pessoais",
            "platforms": ["tiktok", "instagram", "youtube"],
            "content_style": "educational",
        })
        assert r.status_code == 200, f"PATCH /offices falhou: {r.text}"
        print(f"✅ PATCH /offices/{{id}} — nome: {r.json()['name']}, plataformas: {r.json()['platforms']}")

        # 12. Cleanup: DELETE /offices (only if we created it this run)
        if len(initial_offices) == 0:
            r = await client.delete(f"/offices/{office_id}", headers=headers)
            assert r.status_code == 204, f"DELETE /offices falhou: {r.text}"
            print(f"✅ DELETE /offices/{office_id[:8]}...")

        print("\n" + "="*55)
        print("✅ TODOS OS TESTES PASSARAM")
        print("="*55 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
