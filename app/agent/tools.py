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
    preview: Callable[..., Awaitable[dict]] | None = None


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
    mode: str = Field(
        default="add",
        description="참석자 수정 모드. add: 기존 명단에 추가, remove: 기존 명단에서 제거, set: 명단 전체 교체.",
        examples=["add", "remove", "set"],
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
    description="지정 월(YYYYMM)의 날짜별 참석자 명단과 특이사항을 반환한다.",
    category=FunctionCategory.READ,
    args_schema=GetAttendanceArgs,
    handler=_stub,
)

save_attendance_tool = ToolDefinition(
    name="save_attendance",
    summary="특정 날짜 참석자/특이사항 저장",
    description=(
        "지정 날짜(YYYYMMDD)의 참석자 또는 특이사항을 저장한다. "
        "mode별 동작: add=기존 명단에 추가(기본값), remove=기존 명단에서 제거, set=명단 전체 교체. "
        "부분 수정 가능: attendee만 보내면 참석자만, notice만 보내면 특이사항만 업데이트."
    ),
    category=FunctionCategory.WRITE,
    args_schema=SaveAttendanceArgs,
    handler=_stub,
)

export_excel_tool = ToolDefinition(
    name="export_excel",
    summary="특정 월 출석부 Excel 파일 다운로드",
    description="지정 월(YYYYMM)의 출석부를 Excel 파일로 다운로드한다.",
    category=FunctionCategory.READ,
    args_schema=ExportExcelArgs,
    handler=_stub,
)

navigate_month_tool = ToolDefinition(
    name="navigate_month",
    summary="특정 월 출석 페이지로 이동",
    description="지정 월(YYYYMM)의 출석 현황 페이지로 이동한다.",
    category=FunctionCategory.READ,
    args_schema=NavigateMonthArgs,
    handler=_stub,
)

logout_tool = ToolDefinition(
    name="logout",
    summary="로그아웃",
    description="현재 사용자를 로그아웃시키고 로그인 페이지로 이동한다.",
    category=FunctionCategory.READ,
    args_schema=LogoutArgs,
    handler=_stub,
)

class HelpArgs(ToolArgs):
    pass


get_help_tool = ToolDefinition(
    name="get_help",
    summary="사용 가능한 기능 목록 조회",
    description="제공 가능한 모든 기능의 목록과 설명을 반환한다.",
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
                "description": tool.description,
                "parameters": tool.args_schema.model_json_schema(),
            },
        }
        for tool in registry.values()
    ]


TOOLS_PARAM: list[dict] = registry_to_tools_param(REGISTRY)


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

    async def _preview_save_attendance(**kw) -> dict:
        from app.dao.functions import get_attendees, get_notices

        date = kw["date"]
        attendees_raw = await get_attendees(session, date, date)
        notices_raw = await get_notices(session, date, date)

        current_attendee = attendees_raw[0]["atde_name"] if attendees_raw else ""
        current_notice = notices_raw[0]["atdc_notice"] if notices_raw else ""

        new_attendee = kw.get("attendee")
        new_notice = kw.get("notice")

        date_display = f"{date[:4]}년 {int(date[4:6])}월 {int(date[6:])}일"

        items = []
        if new_attendee is not None:
            existing_names = {n.strip() for n in current_attendee.split(",") if n.strip()} if current_attendee else set()
            input_names = {n.strip() for n in new_attendee.split(",") if n.strip()}

            mode = kw.get("mode", "add")
            if mode == "remove":
                result_names = existing_names - input_names
            elif mode == "set":
                result_names = input_names
            else:
                result_names = existing_names | input_names

            items.append({
                "label": "참석자",
                "current": current_attendee or "(없음)",
                "new": ", ".join(sorted(result_names)) or "(없음)",
            })
        if new_notice is not None:
            items.append({
                "label": "특이사항",
                "current": current_notice or "(없음)",
                "new": new_notice or "(없음)",
            })

        return {"date_display": date_display, "items": items}

    handlers = {
        "get_attendance": lambda **kw: svc.get_attendance_data(session, **kw),
        "save_attendance": lambda **kw: svc.save_attendance(session, **kw),
        "export_excel": lambda **kw: svc.export_attendance(session, **kw),
        "navigate_month": _handle_navigate_month,
        "logout": _handle_logout,
        "get_help": _handle_help,
    }

    previews = {
        "save_attendance": _preview_save_attendance,
    }

    return {
        name: replace(tool, handler=handlers[name], preview=previews.get(name))
        for name, tool in REGISTRY.items()
    }
