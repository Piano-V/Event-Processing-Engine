import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """
    Test user registration.
    """
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "testuser", "password": "password123"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "testuser"
    assert "id" in data

@pytest.mark.asyncio
async def test_register_duplicate_user(client: AsyncClient):
    """
    Test registering an already existing user returns a 400 error.
    """
    # Create the user first
    await client.post(
        "/api/v1/auth/register",
        json={"username": "dupuser", "password": "password123"}
    )
    
    # Attempt to create again
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "dupuser", "password": "password123"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already registered"

@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """
    Test successful login flow returning access token.
    """
    # Register user
    await client.post(
        "/api/v1/auth/register",
        json={"username": "loginuser", "password": "password123"}
    )
    
    # Log in
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": "loginuser", "password": "password123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient):
    """
    Test login failures due to wrong password.
    """
    # Register user
    await client.post(
        "/api/v1/auth/register",
        json={"username": "badloginuser", "password": "password123"}
    )
    
    # Log in with wrong credentials
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": "badloginuser", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect username or password"
