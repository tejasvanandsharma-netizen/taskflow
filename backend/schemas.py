from pydantic import BaseModel, ConfigDict, Field, field_validator

PRIORITY_PATTERN = r"^(low|medium|high)$"
DEFAULT_PRIORITY = "medium"


class UserBase(BaseModel):
    email: str = Field(min_length=1)


class UserCreate(UserBase):
    password: str = Field(min_length=1)


class UserRead(UserBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ProjectBase(BaseModel):
    title: str = Field(min_length=1)


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
