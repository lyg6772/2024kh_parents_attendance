from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Type

from pydantic import BaseModel, Field


class FunctionCategory(str, Enum):
    READ = "read"
    WRITE = "write"


class ToolArgs(BaseModel):
    pass


@dataclass
class ToolDefinition:
    name: str
    summary: str
    description: str
    category: FunctionCategory
    args_schema: Type[ToolArgs]
    handler: Callable[..., Awaitable[dict]]


class GetAttendanceArgs(ToolArgs):
    yyyymm: str = Field(
        description="조회할 월. YYYYMM 형식.",
        examples=["202604"],
    )


class SaveAttendanceArgs(ToolArgs):
    date: str = Field(
        description="날짜. YYYYMMDD 형식.",
        examples=["20260403"],
    )
    attendee: str | None = Field(
        default=None,
        description="참석자. 쉼표 구분 문자열. 미지정 시 기존 값 유지.",
        examples=["김철수,이영희"],
    )
    notice: str | None = Field(
        default=None,
        description="특이사항. 미지정 시 기존 값 유지.",
    )


class ExportExcelArgs(ToolArgs):
    yyyymm: str = Field(
        description="대상 월. YYYYMM 형식.",
        examples=["202604"],
    )


class NavigateMonthArgs(ToolArgs):
    yyyymm: str = Field(
        description="이동할 월. YYYYMM 형식.",
        examples=["202604"],
    )


class LogoutArgs(ToolArgs):
    pass


async def _stub(**kwargs) -> dict:
    raise NotImplementedError("데이터 서비스 연결 전 stub")


get_attendance_tool = ToolDefinition(
    name="get_attendance",
    summary="특정 월의 출석 현황 조회",
    description=(
        "지정 월(YYYYMM)의 날짜별 참석자 명단과 특이사항을 반환한다. "
        "결과 형식: {dates: [{date, attendee, notice}, ...]}. "
        "사용 시점: 출석 현황 질문, 특정 날짜 참석자 확인, 저장/수정 전 기존 데이터 파악."
    ),
    category=FunctionCategory.READ,
    args_schema=GetAttendanceArgs,
    handler=_stub,
)

save_attendance_tool = ToolDefinition(
    name="save_attendance",
    summary="특정 날짜 참석자/특이사항 저장",
    description=(
        "지정 날짜(YYYYMMDD)의 참석자 또는 특이사항을 저장한다. "
        "부분 수정 가능: attendee만 보내면 참석자만, notice만 보내면 특이사항만 업데이트되고 나머지는 기존 값 유지. "
        "참석자는 쉼표 구분 문자열(예: '김철수,이영희'). "
        "전제조건: 반드시 이 도구 호출 전에 get_attendance로 해당 월 현황을 먼저 조회해야 한다."
    ),
    category=FunctionCategory.WRITE,
    args_schema=SaveAttendanceArgs,
    handler=_stub,
)

export_excel_tool = ToolDefinition(
    name="export_excel",
    summary="특정 월 출석부 Excel 파일 다운로드",
    description=(
        "지정 월(YYYYMM)의 출석부를 Excel(.xlsx) 파일로 다운로드한다. "
        "사용 시점: '엑셀로 뽑아줘', '엑셀 다운로드', 'Excel로 내보내기' 등 파일 다운로드 요청."
    ),
    category=FunctionCategory.READ,
    args_schema=ExportExcelArgs,
    handler=_stub,
)

navigate_month_tool = ToolDefinition(
    name="navigate_month",
    summary="특정 월 출석 페이지로 이동",
    description=(
        "지정 월(YYYYMM)의 출석 현황 캘린더 페이지로 이동한다. "
        "사용 시점: '4월로 이동', '5월 출석부 보여줘', '다음 달로 가줘', '출석 현황 페이지 보고싶다' 등 페이지 이동 요청."
    ),
    category=FunctionCategory.READ,
    args_schema=NavigateMonthArgs,
    handler=_stub,
)

logout_tool = ToolDefinition(
    name="logout",
    summary="로그아웃",
    description=(
        "현재 사용자를 로그아웃시킨다. "
        "사용 시점: '로그아웃', '로그아웃 해줘', '나갈게' 등의 요청. "
        "결과: 로그아웃 후 로그인 페이지로 이동."
    ),
    category=FunctionCategory.READ,
    args_schema=LogoutArgs,
    handler=_stub,
)

class HelpArgs(ToolArgs):
    pass


get_help_tool = ToolDefinition(
    name="get_help",
    summary="사용 가능한 기능 목록 조회",
    description=(
        "현재 제공 가능한 모든 기능의 목록과 설명을 반환한다. "
        "사용 시점: '도움말', '뭐 할 수 있어?', '기능 알려줘', '사용법', 'help' 등의 요청."
    ),
    category=FunctionCategory.READ,
    args_schema=HelpArgs,
    handler=_stub,
)

REGISTRY: dict[str, ToolDefinition] = {
    t.name: t for t in [
        get_attendance_tool,
        save_attendance_tool,
        export_excel_tool,
        navigate_month_tool,
        logout_tool,
        get_help_tool,
    ]
}


def registry_to_tools_param(registry: dict[str, ToolDefinition]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": f"{tool.summary}\n{tool.description}",
                "parameters": tool.args_schema.model_json_schema(),
            },
        }
        for tool in registry.values()
    ]


def build_registry(session) -> dict[str, ToolDefinition]:
    from dataclasses import replace

    from app.service import attendance_data as svc

    async def _handle_logout(**kw) -> dict:
        return {"redirect_url": "/logout"}

    async def _handle_navigate_month(**kw) -> dict:
        return {"redirect_url": f"/admin/attendee/{kw['yyyymm']}"}

    async def _handle_help(**kw) -> dict:
        return {
            "features": [
                t.summary for t in REGISTRY.values()
                if t.name != "get_help"
            ]
        }

    handlers = {
        "get_attendance": lambda **kw: svc.get_attendance_data(session, **kw),
        "save_attendance": lambda **kw: svc.save_attendance(session, **kw),
        "export_excel": lambda **kw: svc.export_attendance(session, **kw),
        "navigate_month": _handle_navigate_month,
        "logout": _handle_logout,
        "get_help": _handle_help,
    }

    return {
        name: replace(tool, handler=handlers[name])
        for name, tool in REGISTRY.items()
    }
