from builtins import Exception, bool, classmethod, int, str
from datetime import datetime, timezone
import secrets
from typing import Optional, Dict, List
from pydantic import ValidationError
from sqlalchemy import func, null, update, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_email_service, get_settings
from app.models.user_model import User
from app.schemas.user_schemas import UserCreate, UserUpdate
from app.utils.nickname_gen import generate_nickname
from app.utils.security import generate_verification_token, hash_password, verify_password
from uuid import UUID
from app.services.email_service import EmailService
from app.models.user_model import UserRole
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

class UserService:
    @classmethod
    async def _execute_query(cls, session: AsyncSession, query):
        try:
            result = await session.execute(query)
            await session.commit()
            return result
        except SQLAlchemyError as e:
            logger.error(f"Database error: {e}")
            await session.rollback()
            return None

    @classmethod
    async def _fetch_user(cls, session: AsyncSession, **filters) -> Optional[User]:
        query = select(User).filter_by(**filters)
        result = await cls._execute_query(session, query)
        return result.scalars().first() if result else None

    @classmethod
    async def get_by_id(cls, session: AsyncSession, user_id: UUID) -> Optional[User]:
        return await cls._fetch_user(session, id=user_id)

    @classmethod
    async def get_by_nickname(cls, session: AsyncSession, nickname: str) -> Optional[User]:
        return await cls._fetch_user(session, nickname=nickname)

    @classmethod
    async def get_by_email(cls, session: AsyncSession, email: str) -> Optional[User]:
        return await cls._fetch_user(session, email=email)

    @classmethod
    async def create(cls, session: AsyncSession, user_data: Dict[str, str], email_service: EmailService) -> Optional[User]:
        try:
            validated_data = UserCreate(**user_data).model_dump()
            existing_user = await cls.get_by_email(session, validated_data['email'])
            if existing_user:
                logger.error("User with given email already exists.")
                return None
            validated_data['hashed_password'] = hash_password(validated_data.pop('password'))
            new_user = User(**validated_data)
            new_nickname = generate_nickname()
            while await cls.get_by_nickname(session, new_nickname):
                new_nickname = generate_nickname()
            new_user.nickname = new_nickname
            logger.info(f"User Role: {new_user.role}")
            user_count = await cls.count(session)
            new_user.role = UserRole.ADMIN if user_count == 0 else UserRole.ANONYMOUS            
            if new_user.role == UserRole.ADMIN:
                new_user.email_verified = True

            else:
                new_user.verification_token = generate_verification_token()
                await email_service.send_verification_email(new_user)

            session.add(new_user)
            await session.commit()
            return new_user
        except ValidationError as e:
            logger.error(f"Validation error during user creation: {e}")
            return None

    @classmethod
    async def update(cls, session: AsyncSession, user_id: UUID, update_data: Dict[str, str]) -> Optional[User]:
        try:
            # First check if user exists before attempting update
            existing_user = await cls.get_by_id(session, user_id)
            if not existing_user:
                logger.error(f"User {user_id} not found for update.")
                return None
                
            # Validate the update data
            try:
                validated_data = UserUpdate(**update_data).model_dump(exclude_unset=True)
            except ValidationError as ve:
                logger.error(f"Validation error during user update: {ve}")
                return None

            # Handle password updates securely
            if 'password' in validated_data:
                validated_data['hashed_password'] = hash_password(validated_data.pop('password'))
                
            # Perform the update
            query = update(User).where(User.id == user_id).values(**validated_data).execution_options(synchronize_session="fetch")
            result = await cls._execute_query(session, query)
            if not result:
                logger.error(f"Database error during update for user {user_id}")
                return None
                
            # Get the updated user
            updated_user = await cls.get_by_id(session, user_id)
            if updated_user:
                session.refresh(updated_user)  # Explicitly refresh the updated user object
                logger.info(f"User {user_id} updated successfully.")
                return updated_user
            else:
                logger.error(f"User {user_id} not found after update attempt.")
                return None
                
        except ValidationError as e:
            logger.error(f"Validation error during user update: {e}")
            return None
        except SQLAlchemyError as e:
            logger.error(f"Database error during user update: {e}")
            return None
        except Exception as e:  # Catch-all for unexpected errors
            logger.error(f"Unexpected error during user update: {e}")
            return None

    @classmethod
    async def delete(cls, session: AsyncSession, user_id: UUID) -> bool:
        user = await cls.get_by_id(session, user_id)
        if not user:
            logger.info(f"User with ID {user_id} not found.")
            return False
        await session.delete(user)
        await session.commit()
        return True

    @classmethod
    async def list_users(cls, session: AsyncSession, skip: int = 0, limit: int = 10) -> List[User]:
        query = select(User).offset(skip).limit(limit)
        result = await cls._execute_query(session, query)
        return result.scalars().all() if result else []

    @classmethod
    async def register_user(cls, session: AsyncSession, user_data: Dict[str, str], get_email_service) -> Optional[User]:
        return await cls.create(session, user_data, get_email_service)
    

    @classmethod
    async def login_user(cls, session: AsyncSession, email: str, password: str) -> Optional[User]:
        user = await cls.get_by_email(session, email)
        if not user:
            # Don't reveal that the email doesn't exist for security
            logger.warning(f"Login attempt with non-existent email: {email}")
            return None
            
        # Check if email is verified
        if user.email_verified is False:
            logger.warning(f"Login attempt with unverified email: {email}")
            return None
            
        # Check if account is locked
        if user.is_locked:
            # Calculate time since last failed attempt to possibly unlock
            current_time = datetime.now(timezone.utc)
            # If there's no last_login_at, use creation time
            last_attempt = user.last_login_at or user.created_at
            
            # If more than 24 hours have passed, unlock the account automatically
            if current_time - last_attempt > timedelta(hours=24):
                user.is_locked = False
                user.failed_login_attempts = 0
                logger.info(f"Account unlocked after 24-hour timeout: {email}")
            else:
                logger.warning(f"Login attempt on locked account: {email}")
                # Update timestamp to track attempted login on locked account
                user.last_login_at = current_time
                session.add(user)
                await session.commit()
                return None
            
        # Verify password
        if verify_password(password, user.hashed_password):
            # Successful login - reset failed attempts
            user.failed_login_attempts = 0
            user.last_login_at = datetime.now(timezone.utc)
            session.add(user)
            await session.commit()
            logger.info(f"Successful login: {email}")
            return user
        else:
            # Failed login - increment counter
            user.failed_login_attempts += 1
            current_time = datetime.now(timezone.utc)
            user.last_login_at = current_time
            
            # Lock account if max attempts reached
            if user.failed_login_attempts >= settings.max_login_attempts:
                user.is_locked = True
                logger.warning(f"Account locked after {settings.max_login_attempts} failed attempts: {email}")
                
            session.add(user)
            await session.commit()
            logger.warning(f"Failed login attempt {user.failed_login_attempts} for: {email}")
            return None

    @classmethod
    async def is_account_locked(cls, session: AsyncSession, email: str) -> bool:
        user = await cls.get_by_email(session, email)
        return user.is_locked if user else False


    @classmethod
    async def reset_password(cls, session: AsyncSession, user_id: UUID, new_password: str) -> bool:
        hashed_password = hash_password(new_password)
        user = await cls.get_by_id(session, user_id)
        if user:
            user.hashed_password = hashed_password
            user.failed_login_attempts = 0  # Resetting failed login attempts
            user.is_locked = False  # Unlocking the user account, if locked
            session.add(user)
            await session.commit()
            return True
        return False

    @classmethod
    async def verify_email_with_token(cls, session: AsyncSession, user_id: UUID, token: str) -> bool:
        user = await cls.get_by_id(session, user_id)
        if user and user.verification_token == token:
            user.email_verified = True
            user.verification_token = None  # Clear the token once used
            user.role = UserRole.AUTHENTICATED
            session.add(user)
            await session.commit()
            return True
        return False

    @classmethod
    async def count(cls, session: AsyncSession) -> int:
        """
        Count the number of users in the database.

        :param session: The AsyncSession instance for database access.
        :return: The count of users.
        """
        query = select(func.count()).select_from(User)
        result = await session.execute(query)
        count = result.scalar()
        return count
    
    @classmethod
    async def unlock_user_account(cls, session: AsyncSession, user_id: UUID) -> bool:
        user = await cls.get_by_id(session, user_id)
        if user and user.is_locked:
            user.is_locked = False
            user.failed_login_attempts = 0  # Optionally reset failed login attempts
            session.add(user)
            await session.commit()
            return True
        return False
        
    @classmethod
    async def update_professional_status(cls, session: AsyncSession, user_id: UUID, is_professional: bool) -> Optional[User]:
        """
        Update a user's professional status.
        
        :param session: The AsyncSession instance for database access.
        :param user_id: The UUID of the user to update.
        :param is_professional: Boolean indicating whether the user should have professional status.
        :return: The updated User if successful, None otherwise.
        """
        user = await cls.get_by_id(session, user_id)
        if not user:
            logger.error(f"User with ID {user_id} not found for professional status update.")
            return None
            
        user.is_professional = is_professional
        user.professional_status_updated_at = datetime.now(timezone.utc)
        
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        logger.info(f"Professional status updated for user {user_id} to {is_professional}")
        return user
