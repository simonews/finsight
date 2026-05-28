async def test_create_portfolio(async_client, token_headers):
    response = await async_client.post(
        "/api/v1/portfolios/",
        json={"name": "Test Portfolio", "description": "desc"},
        headers=token_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Test Portfolio"
    assert "id" in body and "user_id" in body


async def test_read_portfolios(async_client, token_headers):
    await async_client.post(
        "/api/v1/portfolios/",
        json={"name": "P1", "description": None},
        headers=token_headers,
    )
    response = await async_client.get("/api/v1/portfolios/", headers=token_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "P1"


async def test_ownership_enforced(async_client, token_headers):
    created = await async_client.post(
        "/api/v1/portfolios/",
        json={"name": "Owner Only", "description": None},
        headers=token_headers,
    )
    portfolio_id = created.json()["id"]

    await async_client.post(
        "/api/v1/auth/register",
        json={"email": "user2@test.com", "password": "Password123"},
    )
    login = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "user2@test.com", "password": "Password123"},
    )
    user2_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await async_client.get(
        f"/api/v1/portfolios/{portfolio_id}", headers=user2_headers
    )
    assert response.status_code == 403