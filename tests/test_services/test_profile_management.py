import pytest
from datetime import datetime, timezone
from uuid import uuid4
from app.models.user_model import User, UserRole
from app.services.user_service import UserService
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.mark.asyncio
async def test_update_professional_status_success(db_session: AsyncSession, user: User):
    """Test successful update of a user's professional status."""
    # Arrange
    assert not user.is_professional  # Ensure user is not professional initially
    
    # Act
    updated_user = await UserService.update_professional_status(db_session, user.id, True)
    
    # Assert
    assert updated_user is not None
    assert updated_user.is_professional
    assert updated_user.professional_status_updated_at is not None
    assert (datetime.now(timezone.utc) - updated_user.professional_status_updated_at).total_seconds() < 5

@pytest.mark.asyncio
async def test_update_professional_status_nonexistent_user(db_session: AsyncSession):
    """Test updating professional status for a non-existent user."""
    # Arrange
    non_existent_id = uuid4()
    
    # Act
    result = await UserService.update_professional_status(db_session, non_existent_id, True)
    
    # Assert
    assert result is None

@pytest.mark.asyncio
async def test_profile_update_with_valid_data(db_session: AsyncSession, user: User):
    """Test updating user profile with valid data."""
    # Arrange
    update_data = {
        "first_name": "Updated First",
        "last_name": "Updated Last",
        "bio": "This is an updated bio for testing purposes."
    }
    
    # Act
    updated_user = await UserService.update(db_session, user.id, update_data)
    
    # Assert
    assert updated_user is not None
    assert updated_user.first_name == "Updated First"
    assert updated_user.last_name == "Updated Last"
    assert updated_user.bio == "This is an updated bio for testing purposes."

@pytest.mark.asyncio
async def test_profile_update_with_invalid_urls(db_session: AsyncSession, user: User):
    """Test validation for invalid URLs in profile update."""
    # Arrange
    update_data = {
        "linkedin_profile_url": "invalid-url",  # Not a valid URL
        "github_profile_url": "also-invalid-url"  # Not a valid URL
    }
    
    # Act & Assert
    try:
        updated_user = await UserService.update(db_session, user.id, update_data)
        assert updated_user is None, "Update should fail with invalid URLs"
    except ValueError:
        # This is expected due to our URL validation in user_schemas.py
        pass

@pytest.mark.asyncio
async def test_profile_update_with_valid_urls(db_session: AsyncSession, user: User):
    """Test updating profile with valid URLs."""
    # Arrange
    update_data = {
        "linkedin_profile_url": "https://linkedin.com/in/testuser",
        "github_profile_url": "https://github.com/testuser",
        "profile_picture_url": "https://example.com/profile.jpg"
    }
    
    # Act
    updated_user = await UserService.update(db_session, user.id, update_data)
    
    # Assert
    assert updated_user is not None
    assert updated_user.linkedin_profile_url == "https://linkedin.com/in/testuser"
    assert updated_user.github_profile_url == "https://github.com/testuser"
    assert updated_user.profile_picture_url == "https://example.com/profile.jpg"
