from pydantic import BaseModel, Field, model_validator


class AttendeeRow(BaseModel):
    """DAO get_attendee 결과 행. Oracle 대문자 컬럼명을 정규화."""

    atdc_date: str
    atde_name: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_oracle_columns(cls, data):
        if isinstance(data, dict):
            return {
                "atdc_date": data.get("atdc_date") or data.get("ATDC_DATE") or "",
                "atde_name": data.get("atde_name") or data.get("ATDE_NAME") or "",
            }
        return data


class NoticeRow(BaseModel):
    """DAO get_notice 결과 행. Oracle 대문자 컬럼명을 정규화."""

    atdc_date: str
    atdc_notice: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_oracle_columns(cls, data):
        if isinstance(data, dict):
            return {
                "atdc_date": data.get("atdc_date") or data.get("ATDC_DATE") or "",
                "atdc_notice": data.get("atdc_notice") or data.get("ATDC_NOTICE") or "",
            }
        return data


class DateRange(BaseModel):
    start_dt: str = Field(description="YYYYMMDD")
    end_dt: str = Field(description="YYYYMMDD")
    year: int
    month: int


class CalendarContext(BaseModel):
    year: int
    month: int
    weeks: list[list[int]]
    prev_month: str = Field(description="YYYYMM")
    next_month: str = Field(description="YYYYMM")


class AttendanceData(BaseModel):
    """데이터 서비스 응답. 에이전트/API 공용."""

    year: int
    month: int
    weeks: list[list[int]]
    prev_month: str
    next_month: str
    attendees: dict[str, str] = Field(
        default_factory=dict,
        description="날짜(YYYYMMDD) → 참석자 쉼표 구분 문자열",
    )
    notices: dict[str, str] = Field(
        default_factory=dict,
        description="날짜(YYYYMMDD) → 특이사항",
    )
