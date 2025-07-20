# FAQ_ChatBot

전체적인 구조

```
faq_chatbot/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 앱
│   ├── api/
│   │   ├── __init__.py
│   │   └── chat.py            # 채팅 엔드포인트
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py          # 설정
│   │   ├── embeddings.py      # 임베딩 모델
│   │   ├── llm.py             # LLM 래퍼
│   │   └── memory.py          # 대화 기억
│   ├── services/
│   │   ├── __init__.py
│   │   ├── vector_store.py    # Chroma 인터페이스
│   │   ├── retriever.py       # 검색 로직
│   │   ├── ranker.py          # 문맥 순위화
│   │   └── chat_service.py    # 메인 서비스
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py         # Pydantic 모델
│   └── utils/
│       ├── __init__.py
│       ├── text_processing.py # 텍스트 전처리
│       └── cache.py           # 캐싱 유틸
├── data/
│   └── faqs.json             # FAQ 데이터
├── scripts/
│   └── setup_vector_db.py    # 벡터DB 초기화
├── tests/
├── requirements.txt
└── README.md
```