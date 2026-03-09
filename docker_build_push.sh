#!/bin/zsh

# pyproject.toml에서 버전 파싱 (Python tomllib 사용)
VERSION=$(python3 -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
print(data['tool']['poetry']['version'])
")

IMAGE_NAME="lyg6772/2024_kh_attendee"

if [ -z "$VERSION" ]; then
    echo "❌ 버전을 찾을 수 없습니다. pyproject.toml을 확인하세요."
    exit 1
fi

echo "========================================"
echo "  버전: $VERSION"
echo "  이미지: $IMAGE_NAME:v$VERSION"
echo "========================================"

# Docker 빌드
echo "🔨 Docker 빌드 중..."
docker build -t $IMAGE_NAME:v$VERSION -t $IMAGE_NAME:latest .

if [ $? -ne 0 ]; then
    echo "❌ Docker 빌드 실패"
    exit 1
fi

echo "✅ Docker 빌드 완료"

# Docker 푸시
echo "📤 Docker 푸시 중..."
docker push $IMAGE_NAME:v$VERSION
docker push $IMAGE_NAME:latest

if [ $? -ne 0 ]; then
    echo "❌ Docker 푸시 실패"
    exit 1
fi

echo "✅ Docker 푸시 완료"
echo "========================================"
echo "  $IMAGE_NAME:v$VERSION 배포 완료!"
echo "========================================"
