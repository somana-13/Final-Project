import pytest
from httpx import AsyncClient
from uuid import uuid4
from app.main import app

@pytest.mark.asyncio
async def test_update_professional_status_admin_access(async_client, admin_user, admin_token):
    """Test that admins can update a user's professional status."""
    # Arrange
    headers = {"Authorization": f"Bearer {admin_token}"}
    status_update = {"is_professional": True}
    
    # Act
    response = await async_client.patch(
        f"/users/{admin_user.id}/professional-status", 
        json=status_update, 
        headers=headers
    )
    
    # Assert
    assert response.status_code == 200
    assert response.json()["is_professional"] is True

@pytest.mark.asyncio
async def test_update_professional_status_user_access_denied(async_client, user, verified_user, user_token):
    """Test that regular users cannot update professional status."""
    # Arrange
    headers = {"Authorization": f"Bearer {user_token}"}
    status_update = {"is_professional": True}
    
    # Act
    response = await async_client.patch(
        f"/users/{verified_user.id}/professional-status", 
        json=status_update, 
        headers=headers
    )
    
    # Assert
    assert response.status_code == 403  # Forbidden

@pytest.mark.asyncio
async def test_update_professional_status_nonexistent_user(async_client, admin_token):
    """Test updating professional status for a non-existent user."""
    # Arrange
    headers = {"Authorization": f"Bearer {admin_token}"}
    status_update = {"is_professional": True}
    non_existent_id = uuid4()
    
    # Act
    response = await async_client.patch(
        f"/users/{non_existent_id}/professional-status", 
        json=status_update, 
        headers=headers
    )
    
    # Assert
    assert response.status_code == 404  # Not Found

@pytest.mark.asyncio
async def test_update_own_profile_authenticated_user(async_client, verified_user, user_token):
    """Test that authenticated users can update their own profile."""
    # Arrange
    headers = {"Authorization": f"Bearer {user_token}"}
    profile_update = {
        "first_name": "Updated",
        "last_name": "User",
        "bio": "This is my updated profile bio"
    }
    
    # Act
    response = await async_client.put("/profile", json=profile_update, headers=headers)
    
    # Assert
    assert response.status_code == 200
    assert response.json()["first_name"] == "Updated"
    assert response.json()["last_name"] == "User"
    assert response.json()["bio"] == "This is my updated profile bio"

@pytest.mark.asyncio
async def test_update_profile_invalid_url(async_client, verified_user, user_token):
    """Test validation for invalid URLs in profile update."""
    # Arrange
    headers = {"Authorization": f"Bearer {user_token}"}
    profile_update = {
        "profile_picture_url": "invalid-url"  # Not a valid URL format
    }
    
    # Act
    response = await async_client.put("/profile", json=profile_update, headers=headers)
    
    # Assert
    assert response.status_code == 400  # Bad Request
