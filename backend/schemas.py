from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PRIORITY_PATTERN = r"^(low|medium|high)$"
DEFAULT_PRIORITY = "medium"
GENDER_VALUES = ("male", "female", "other")


class UserBase(BaseModel):
    email: str = Field(min_length=1)


class UserCreate(UserBase):
    password: str = Field(min_length=1)


class UserRead(BaseModel):
    id: int
    email: str
    phone: str | None = None
    username: str | None = None
    display_name: str | None = None
    gender: str | None = None
    provider: str = "local"
    model_config = ConfigDict(from_attributes=True)


class SignupCreate(BaseModel):
    """Sign up with email, phone, or username — at least one is required."""
    email: str | None = None
    phone: str | None = None
    username: str | None = None
    password: str = Field(min_length=1)
    display_name: str | None = None
    gender: str | None = Field(default="other", pattern=r"^(male|female|other)$")

    @field_validator("email")
    @classmethod
    def email_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None

    @field_validator("phone")
    @classmethod
    def phone_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None

    @field_validator("username")
    @classmethod
    def username_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None

    @field_validator("display_name")
    @classmethod
    def name_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None


class LoginRequest(BaseModel):
    """Log in with email, username, phone number, or numeric user id."""
    identifier: str = Field(min_length=1)
    password: str = Field(min_length=1)


class OAuthRequest(BaseModel):
    """OAuth sign-in. With GOOGLE_CLIENT_ID/GITHUB_CLIENT_ID configured the
    supplied id_token/code is verified; otherwise a demo profile is used."""
    provider: Literal["google", "github"]
    id_token: str | None = None
    code: str | None = None
    email: str | None = None
    name: str | None = None
    gender: str | None = Field(default=None, pattern=r"^(male|female|other)$")


class AuthResponse(BaseModel):
    token: str
    user: UserRead


class MeUpdate(BaseModel):
    display_name: str | None = None
    gender: str | None = Field(default=None, pattern=r"^(male|female|other)$")

    @field_validator("display_name")
    @classmethod
    def name_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        return value or None


class ProjectBase(BaseModel):
    title: str = Field(min_length=1)
    content: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class ProjectCreate(ProjectBase):
    pass


class ProjectRead(ProjectBase):
    id: int
    owner_id: int
    model_config = ConfigDict(from_attributes=True)


class TaskBase(BaseModel):
    title: str
    priority: str = Field(default=DEFAULT_PRIORITY, pattern=PRIORITY_PATTERN)
    due_date: str | None = None
    content: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = None
    priority: str | None = Field(default=None, pattern=PRIORITY_PATTERN)
    due_date: str | None = None
    content: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class TaskRead(TaskBase):
    id: int
    project_id: int
    model_config = ConfigDict(from_attributes=True)


class QuickAddCreate(BaseModel):
    description: str
    project_id: int


class PriorityCounts(BaseModel):
    low: int = 0
    medium: int = 0
    high: int = 0


class ProjectStats(BaseModel):
    project_id: int
    project_title: str
    task_count: int
    counts_by_priority: PriorityCounts
