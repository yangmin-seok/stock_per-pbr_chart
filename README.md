# 한국 주식 데이터 시각화 플랫폼

`pykrx` 라이브러리의 세션 패칭 기술을 이용하여, 한국거래소(KRX)의 고정밀 재무/주가 데이터를 수집 및 분석하는 시각화 대시보드 애플리케이션입니다.

## 주요 기능 스펙
- **데이터 확보 엔진**: KRX 세션 로그인 기반의 한국 주식 데이터 및 `yfinance`를 활용한 글로벌 매크로 지표 (환율, 유가, 금, 은, S&P 500, 나스닥 등) 동시 수집.
- **백그라운드 수집 에이전트(Data Agent)**: Streamlit 구동과 동시에 스레드로 동작하여 매일 장 종료 후 전 종목 데이터를 백그라운드에서 SQLite 캐시(DB)로 업데이트 함으로써 앱 렌더링 딜레이를 99% 이상 단축.
- **분석 대시보드 (Streamlit)**: 10년 치 주가 및 재무 데이터를 바탕으로 한 PER/PBR 밴드 통계 분석 및 시각화, 섹터 파이 차트/트리맵 그리고 주요 매크로 지표의 현황을 네이버 금융 스타일의 스파크라인 카드로 제공.

## 설치 방법 및 실행
1. 가상환경 생성 및 활성화 (Conda 권장)
```bash
# conda 가상환경 생성 (파이썬 3.10 버전 예시)
conda create -n stock_env python=3.10 -y

# 가상환경 활성화
conda activate stock_env
```

2. 필요한 패키지 설치
```bash
pip install -r requirements.txt
```

2. 루트 디렉토리에 `.env` 환경 변수 설정
```env
KRX_ENABLE_LOGIN=true
KRX_LOGIN_ID=your_id
KRX_LOGIN_PW=your_password
KRX_LOGIN_FAIL_POLICY=continue
```

3. 대시보드 구동
```bash
streamlit run app.py
```
