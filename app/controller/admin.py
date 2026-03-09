from fastapi import Request, Depends, HTTPException
from starlette.responses import StreamingResponse
from urllib.parse import quote
from app.service.admin import AdminAttendeeService
from fastapi.templating import Jinja2Templates
from datetime import datetime, timezone
from app.util.auth import AuthHandler
from fastapi.security import OAuth2PasswordBearer

templates = Jinja2Templates(directory="./template")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
auth_handler = AuthHandler()


async def get_current_user(request: Request):
    token = request.cookies.get("token", '')
    user_id = auth_handler.decode_token(token)

    if not user_id:
        raise HTTPException(status_code=401, detail='Could not validate credentials')
    return user_id


async def admin_attendee_get_default(
        request: Request,
        service=Depends(AdminAttendeeService),
        user: str = Depends(get_current_user)
):
    cur_date = datetime.now(timezone.utc)
    return await service.get_attendee_table(request=request, date_str=cur_date.strftime('%Y%m'))


async def admin_attendee_get_year_month(
        request: Request,
        cal_date: str,
        service=Depends(AdminAttendeeService),
        user: str = Depends(get_current_user)
):
    return await service.get_attendee_table(request=request, date_str=cal_date)


async def admin_attendee_post(
        request: Request,
        service=Depends(AdminAttendeeService),
        user: str = Depends(get_current_user)
):
    return await service.post_attendee(request=request)


async def admin_attendee_export_excel(
        service=Depends(AdminAttendeeService),
        cal_date: str = None,
        user: str = Depends(get_current_user)
):
    """관리자 데이터를 Excel로 export"""
    # cal_date가 없으면 현재 달로 처리
    if not cal_date:
        cur_date = datetime.now(timezone.utc)
        cal_date = cur_date.strftime('%Y%m')

    excel_file = await service.export_to_excel(date_str=cal_date)

    # 파일명 생성
    year = cal_date[:4]
    month = cal_date[4:6]
    filename = f'보람교사현황_{year}년{month}월.xlsx'

    # 한글 파일명을 URL 인코딩으로 변환
    encoded_filename = quote(filename.encode('utf-8'))

    return StreamingResponse(
        iter([excel_file.getvalue()]),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
    )
