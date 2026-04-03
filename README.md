# 한국 주식 데이터 시각화 플랫폼

`pykrx` 라이브러리의 세션 패칭 기술을 이용하여, 한국거래소(KRX)의 고정밀 재무/주가 데이터를 수집 및 분석하는 시각화 대시보드 애플리케이션입니다.

## 기능 스펙
- **데이터 확보 엔진**: KRX 로그인 세션 연동으로 PER/PBR, EPS, BPS 등 핵심 재무 데이터 접근.
- **분석/캐싱 기능 (10년치 기준)**: 과거 10년의 통계 분석 모델을 통해 종목별 PER/PBR 밴드 차트의 통계적 구간(최저, 평균, 최고점) 제시. 매일 장 마감 후 자동 갱신 및 SQLite 로컬 캐싱 최적화.
- **인터랙티브 대시보드 (Streamlit)**: Streamlit과 Plotly를 사용한 KOSPI / KOSDAQ 밴드 시각화 및 종목 스크리닝 용 산점도 제공.

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
