import asyncio
import traceback
from viraxis.infrastructure.database.session import AsyncSessionLocal
from viraxis.infrastructure.repositories.user import UserRepository
from viraxis.api.security import hash_password, create_access_token

async def test():
    try:
        async with AsyncSessionLocal() as session:
            repo = UserRepository(session)

            # 1. Check existing
            existing = await repo.get_by_email("marcosalves2036@gmail.com")
            print("Existing user:", existing)

            if existing:
                print("User already exists, skipping create")
                return

            # 2. Hash password
            hashed = hash_password("a12345678")
            print("Password hashed OK")

            # 3. Create user
            user = await repo.create_user(
                email="marcosalves2036@gmail.com",
                hashed_password=hashed,
                full_name="Marcos Teste",
            )
            print("User created:", user.id, user.email)

            await session.commit()
            print("Committed OK")

            token = create_access_token(str(user.id))
            print("Token:", token[:30], "...")

    except Exception:
        traceback.print_exc()

asyncio.run(test())
