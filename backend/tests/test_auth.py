async def test_login_valid_credentials(async_client):
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "auth@test.com", "password": "Password123"},
    )
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "auth@test.com", "password": "Password123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


async def test_login_invalid_credentials(async_client):
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "auth2@test.com", "password": "Password123"},
    )
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "auth2@test.com", "password": "WrongPassword"},
    )
    assert response.status_code == 401