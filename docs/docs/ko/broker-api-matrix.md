# 한국 브로커 API 매트릭스

이 문서는 한국시장 포크가 지원할 공식 브로커 API 표면을 고정하기 위한 감사표다. 구현 상태는 보수적으로 적는다. 자격증명, 모의투자 계정, Windows 브리지 실행면이 없는 항목은 "실연동 완료"로 표시하지 않는다.

자격증명 기반 실연동 검증은 [한국시장 자격증명 smoke 검증 Runbook](credential-smoke-runbook.md)에 따라 raw evidence와 audit report를 함께 남긴다.

## 상태 기준

- `registry`: Vibe-Trading connector profile, transport, mandate 분류, fail-closed config가 등록됨.
- `contract`: 공식 샘플/문서 응답을 기준으로 요청/응답 매핑 테스트가 있음.
- `paper-smoke`: 모의투자 또는 테스트 계정으로 account, positions, orders, quote, history, paper order/cancel을 실행함.
- `live-gated`: 실계좌 주문 경로가 mandate, kill switch, pre-trade check, audit ledger 뒤에서만 열림.
- `blocked`: 공식 API, 자격증명, OS 실행면, 라이선스, 또는 문서 접근 때문에 검증이 닫히지 않음.

## 1차 구현 대상

| 브로커 | 공식 표면 | Vibe connector | Transport | 현재 상태 | 실연동 게이트 |
|---|---|---:|---|---|---|
| 한국투자증권 KIS | [KIS Developers](https://apiportal.koreainvestment.com/apiservice-category), [open-trading-api](https://github.com/koreainvestment/open-trading-api), [kis-ai-extensions](https://github.com/koreainvestment/kis-ai-extensions) | `kis-*` | `broker_sdk` | `registry`, `contract` for domestic stock REST and WebSocket | KIS app key/secret, account/product code, mock/live approval, actual WebSocket smoke |
| LS증권 | [LS OpenAPI](https://openapi.ls-sec.co.kr/apiservice), [사용 방법](https://openapi.ls-sec.co.kr/howto-use), [샘플](https://openapi.ls-sec.co.kr/howto-sample) | `ls-*` | `broker_sdk` | `registry`, `contract` for token/t1101/t0424/CSPAT00601/CSPAT00701/CSPAT00801 REST | LS app key/secret, mock/live approval |
| DB증권 | [DB증권 OPEN API](https://openapi.dbsec.co.kr/), [API 가이드](https://openapi.dbsec.co.kr/apiservice) | `db-*` | `broker_sdk` | `registry`, `contract` for token/PRICE/CSPAQ03420/CSPAQ04800/CSPAT00600/CSPAT00700/CSPAT00800/CSPAT00610/CSPAT00710/CSPAT00810 REST and S00/S01/IS0/IS1 WebSocket | DB app key/secret, mock/live approval, actual WebSocket smoke |
| 키움증권 REST | [Kiwoom REST OpenAPI](https://openapi.kiwoom.com/guide/apiguide), [주문 가이드](https://openapi.kiwoom.com/m/guide/apiguide?jobTpCode=13) | `kiwoom-*` | `broker_sdk` | `registry`, `contract` for ka10001/ka10081/kt00018/ka10075/kt10000/kt10001/kt10002/kt10003 | Kiwoom REST app credentials, mock/live approval |
| 키움증권 OpenAPI+ | [Kiwoom OpenAPI portal](https://openapi.kiwoom.com/guide/apiguide) | `kiwoom-openapi-*` | `local_bridge` | `registry`, `contract`, `blocked` for Windows smoke | Windows PC/VM, OpenAPI+ login, localhost bridge token |
| 대신증권 CYBOS/CREON Plus | [Daishin CYBOS Plus](https://money2.daishin.com/E5/WTS/Customer/GuideTrading/DW_CybosPlus.aspx?m=1098&p=4553&v=3387) | `daishin-cybos-*` | `local_bridge` | `registry`, `contract`, `blocked` for Windows smoke | Windows PC/VM, CYBOS/CREON login, localhost bridge token |

## 공식 API 전수 조사 로그

2026-06-04 기준으로 공개 웹에서 확인한 한국 브로커/시장 API 표면과 확인 실패 항목을 함께 적는다. 이 표는 구현 완료 목록이 아니라 다음 구현 queue와 차단 사유를 고정하는 감사 로그다. 공식 페이지, 브로커 포털, 또는 브로커가 관리하는 공개 GitHub/문서에서 확인된 표면만 구현 근거로 삼는다. 블로그, 커뮤니티, 패키지 README만으로 확인된 표면은 구현 근거로 쓰지 않는다.

| 브로커/기관 | 확인된 공식 표면 | 표면 성격 | 포팅 판정 | 닫아야 할 게이트 |
|---|---|---|---|---|
| DB증권 | [DB증권 OPEN API](https://openapi.dbsec.co.kr/), [API 가이드](https://openapi.dbsec.co.kr/apiservice) | REST/WebSocket. 국내주식 주문/정정/취소, NXT 주문, 국내주식 시세/실시간, 국내선물옵션, 해외주식, 해외선물옵션, 장내채권, 웹소켓 공통 카테고리가 공개됨. | 국내주식 REST, NXT 주문/정정/취소, 국내주식 실시간 WebSocket `S00/S01/IS0/IS1`, WebSocket session reset은 구현됨. 파생/해외/채권은 차기 구현 후보. | app key/secret, 모의투자 계정 smoke, 실제 WebSocket 연결 smoke, 파생/해외/채권 contract 확장. |
| 토스증권 | [토스증권 Open API](https://home.tossinvest.com/en/open-api) | 국내/해외 통합 REST/WebSocket 사전신청 표면. 공개 페이지에 `POST /api/v1/orders`와 `openapi.tossinvest.com/v1` base host/path 샘플이 있음. | `broker_sdk` 후보지만 사전신청/문서 공개 단계로 `blocked`. | GA 문서, API key 발급, 계좌 header, 시세/잔고/주문/cancel 상세 계약. |
| 유진투자증권 | [챔피언 Open API](https://www.eugenefn.com/opapi/opapi100.do) | Windows OCX/DLL. 국내주식, 해외주식, 선물옵션의 시세조회/잔고조회/주문 표면. | `local_bridge` 후보. | Windows 모듈 설치, 개발설명서, read-only bridge contract, 주문 path는 별도 safety gate. |
| 유안타증권 | [티레이더 Open API 서비스 소개](https://www.myasset.com/myasset/trading/apiSvc/TR_1604001_P1.cmd), [API 다운로드](https://www.myasset.com/myasset/trading/apiSvc/TR_1604003_P1.cmd) | Windows DLL/COM. TR InBlock/비동기 수신, Deview 도구, key-value/Struct 통신, 모의투자 테스트 안내가 공개됨. | `local_bridge` 후보. | Windows DLL/COM 모듈, TR 목록/샘플, read-only bridge contract, 모의투자 smoke. |
| KB증권 | [핀테크스토어](https://store.kbsec.com/intro) | 제휴/BaaS/Open API 마켓. 계좌개설부터 주식거래까지 연결한 제휴 사례가 공개됨. | 일반 개인용 자동매매 API가 아니라 제휴 API 표면으로 분류. | 제휴 문서 접근, API 마켓 상세 스펙, retail 주문 API 공개 여부 확인. |
| 미래에셋증권 | [로보링크 수수료 안내](https://trading.securities.miraeasset.com/imf/200/imf604.do) | 로보링크가 Open API 방식의 Server-to-Server 주문매체로 안내됨. 시세/주문화면은 제공하지 않는 주문매체 성격. | 기관/일임/자문 성격 후보. 공개 retail connector로는 `blocked`. | 로보링크 신청 자격, API 개발문서, 시세 별도 계약, 주문 책임/승인 경계. |
| 하나금융그룹/하나증권 | [하나금융그룹 Open API 플랫폼](https://www.hanafnapimarket.com/) | 은행, 카드, 증권, 캐피탈, 생명, 저축은행 API 마켓 표면. | 금융그룹 제휴 API 후보. 일반 트레이딩 connector는 미확인. | 하나증권 주문/잔고 API 상세 문서 접근 또는 제휴 승인. |
| 신한투자증권 | DMA 서비스 공식 URL은 확인됐으나 현재 fetch 가능한 본문에서 API 상세를 안정적으로 추출하지 못함. | 기관 DMA/FIX/API 후보. | `blocked`로 유지. | 공식 DMA 페이지 본문 재확인, DMA팀 제휴/계약, FIX/API 개발문서. |
| NH투자증권/NAMUH/QV | 공개 검색에서 QV/NAMUH OpenAPI 후보는 있으나 이번 pass에서 현재 공식 페이지를 확정하지 못함. | Windows DLL/HTS API 후보. | `blocked`; 블로그/비공식 패키지만으로 구현하지 않음. | NH 공식 다운로드/신청 페이지, DLL 명세, 모의투자 smoke. |
| 삼성증권/SK증권 등 | 이번 pass에서 개인/일반 공개 트레이딩 Open API 공식 표면을 확인하지 못함. | 미확인. | 구현 보류. | 공식 개발자 포털 또는 제휴 문서 확인. |

비브로커 시장 데이터 표면도 별도 후보로 둔다. [KRX Data Marketplace OPEN API](https://openapi.krx.co.kr/contents/OPP/MAIN/main/index.cmd)는 주식, 증권상품, 채권, 파생상품 통계 데이터와 인증키 신청 표면을 제공한다. [코스콤 오픈API플랫폼](https://koscom.gitbook.io/open-api/api)는 KRX 기반 주식/파생/업종 시세 API와 정보시세 라이선스 계약 필요성을 명시한다. 이 둘은 broker connector가 아니라 한국시장 backtest/data loader 후보로 분류한다.

## 한국시장 백테스트/데이터 라우팅 계약

이 섹션은 브로커 주문 API가 아니라 backtest/data loader 표면을 다룬다. 현재 구현은 인증 없는 공개 yfinance 호환 경로와 KRX 기본 시장 규칙 모델이며, KRX/코스콤 공식 데이터 API loader는 별도 라이선스/인증키 게이트가 닫힌 뒤 추가한다.

| 표면 | 현재 계약 | 검증/게이트 |
|---|---|---|
| 시장 감지 | `005930.KS`, `035720.KQ`, `KRX:005930`, `KR.005930`는 `kr_equity`로 분류된다. 접미사가 없는 6자리 코드는 중국 A주와 충돌하므로 backtest auto-routing에서는 명시적 한국 태그를 권장한다. | `agent/tests/test_market_detection.py` |
| Loader fallback | `kr_equity` fallback chain은 `yfinance` → `akshare`다. yfinance loader는 `.KS`/`.KQ`, `KRX:`, `KR.`, `KOSPI:`, `KOSDAQ:` 표기를 Yahoo 호환 심볼로 변환한다. `KRX:`와 `KR.`는 시장부 구분 정보가 없으므로 KOSPI `.KS`로 기본 변환하고, KOSDAQ은 `.KQ` 또는 `KOSDAQ:`을 사용한다. | `agent/tests/test_registry.py`, `agent/tests/test_kr_backtest_data_routing.py` |
| Engine rules | `GlobalEquityEngine(market="kr")`는 [KRX guide](https://global.krx.co.kr/contents/GLB/01/0109/0109000000/guide_to_trading_in_the_korean_stock_market.pdf)의 1주 거래단위와 ±30% 일일 가격제한을 모델링한다. 기본값은 long-only이며, covered short/대차 등 예외는 `kr_allow_short`를 명시해야 열린다. | `agent/tests/test_kr_backtest_data_routing.py` |
| 비용 설정 | 계좌·상품·시점에 따라 달라지는 수수료/거래세는 기본값으로 단정하지 않고 `kr_commission`, `kr_transaction_tax`, `slippage_kr`에 명시 입력한다. | 계좌별 smoke/evidence 필요 |
| Benchmark | 한국 주식 benchmark ticker는 yfinance용 KOSPI composite `^KS11`로 해석한다. | `agent/tests/test_kr_backtest_data_routing.py` |
| 남은 공식 데이터 게이트 | KRX Data Marketplace와 코스콤 오픈API플랫폼은 공식 한국시장 data/backtest loader 후보로 남아 있다. 인증키, 정보시세 라이선스, 재배포 가능 범위, quote/bar endpoint 계약을 확인해야 구현을 닫을 수 있다. | `blocked` |
| 남은 settlement 게이트 | KRX guide는 결제를 T+2로 명시하지만 현재 engine은 현금 결제 잠금까지 모델링하지 않는다. backtest cash-lock/settlement ledger는 차기 구현 항목이다. | `blocked` |

## 재사용/라이선스 원칙

- KIS `open-trading-api`와 `kis-ai-extensions`는 공식 동작·TR명·MCP 구조 참고 자료로 사용한다.
- 두 KIS GitHub 저장소는 2026-06-04 현재 GitHub API에서 라이선스가 명시되지 않았으므로, 코드를 vendoring하거나 복사하지 않는다.
- 브로커별 endpoint 구현은 Vibe-Trading 자체 코드로 재작성하고, 공식 문서는 링크와 테스트 근거로만 둔다.
- DB증권 포털은 `openapi.db-fi.com` 검색 결과도 존재하지만 로컬 TLS 검증에서 hostname mismatch가 나므로, 문서 링크는 동일 포털의 정상 인증서 도메인인 `openapi.dbsec.co.kr`를 사용한다.

## KIS 국내주식 REST 계약

| 기능 | Path | TR ID |
|---|---|---|
| OAuth token | `/oauth2/tokenP` | - |
| Hash key | `/uapi/hashkey` | - |
| 주식현재가 시세 | `/uapi/domestic-stock/v1/quotations/inquire-price` | `FHKST01010100` |
| 국내주식기간별시세 | `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice` | `FHKST03010100` |
| 주식잔고조회 | `/uapi/domestic-stock/v1/trading/inquire-balance` | live `TTTC8434R`, mock `VTTC8434R` |
| 주식정정취소가능주문조회 | `/uapi/domestic-stock/v1/trading/inquire-psbl-rvsecncl` | `TTTC0084R` |
| 주식주문(현금) | `/uapi/domestic-stock/v1/trading/order-cash` | live sell/buy `TTTC0011U`/`TTTC0012U`, mock sell/buy `VTTC0011U`/`VTTC0012U` |
| 주식주문(정정취소) | `/uapi/domestic-stock/v1/trading/order-rvsecncl` | live `TTTC0013U`, mock `VTTC0013U` |

위 계약은 `agent/tests/test_kis_rest_contract.py`에서 token, quote, history, balance, open-order/cancelable-order, hashkey, order request shape로 고정한다. `get_open_orders`는 공식 샘플이 정정/취소 전 확인하도록 요구하는 `inquire-psbl-rvsecncl`을 호출하며, 주문번호, 종목, 매수/매도, 주문수량, 체결수량, 잔량, 정정취소 가능수량, 주문가를 정규화한다. 실제 브로커 계정으로 호출한 smoke test와 연속조회 pagination evidence는 아직 닫히지 않았다.

## KIS 국내주식 WebSocket 계약

| 기능 | Endpoint / TR | Message |
|---|---|---|
| WebSocket approval key | `/oauth2/Approval` | body `grant_type=client_credentials`, `appkey`, `secretkey`; response `approval_key` |
| 운영 WebSocket | `ws://ops.koreainvestment.com:21000` | official `ops` endpoint |
| 모의 WebSocket | `ws://ops.koreainvestment.com:31000` | official `vops` endpoint |
| 실시간호가 KRX/NXT/통합 | `H0STASP0` / `H0NXASP0` / `H0UNASP0` | `tr_key`는 종목코드 |
| 실시간체결가 KRX/NXT/통합 | `H0STCNT0` / `H0NXCNT0` / `H0UNCNT0` | `tr_key`는 종목코드 |
| 주식체결통보 | live `H0STCNI0`, mock `H0STCNI9` | `tr_key`는 HTS ID, 체결통보 stream은 AES key/IV 기반 복호화가 필요함 |
| 실시간예상체결 KRX/NXT/통합 | `H0STANC0` / `H0NXANC0` / `H0UNANC0` | `tr_key`는 종목코드 |
| 국내지수 실시간체결/예상체결/프로그램매매 | `H0UPCNT0` / `H0UPANC0` / `H0UPPGM0` | `tr_key`는 지수코드 |
| 장운영정보 KRX/NXT/통합 | `H0STMKO0` / `H0NXMKO0` / `H0UNMKO0` | `tr_key`는 종목코드 |
| 회원사 KRX/NXT/통합 | `H0STMBC0` / `H0NXMBC0` / `H0UNMBC0` | `tr_key`는 종목코드 |
| 시간외 호가/체결/예상체결 KRX | `H0STOAA0` / `H0STOUP0` / `H0STOAC0` | `tr_key`는 종목코드 |
| 프로그램매매 KRX/NXT/통합 | `H0STPGM0` / `H0NXPGM0` / `H0UNPGM0` | `tr_key`는 종목코드 |

구독 메시지는 공식 `open-trading-api`의 `data_fetch` 형태를 따른다. Header는 `content-type: utf-8`, `approval_key`, `tr_type`, `custtype: P`를 포함하고, body는 `{"input": {"tr_id": "...", "tr_key": "..."}}` 형태다. `agent/tests/test_kis_rest_contract.py`가 endpoint catalog, `/oauth2/Approval` 요청 shape, 구독 메시지 shape, 체결가 data frame 파서, system frame 파서를 고정한다. 실제 WebSocket handshake, 구독 성공, `H0STCNI0/H0STCNI9` 체결통보 복호화 smoke는 KIS 계정과 approval key가 준비된 뒤 별도 evidence로 닫는다.

## LS OpenAPI REST 계약

| 기능 | Path | TR / Header |
|---|---|---|
| OAuth token | `/oauth2/token` | `grant_type=client_credentials`, `appkey`, `appsecretkey`, `scope=oob`, `content-type: application/x-www-form-urlencoded` |
| 주식현재가호가 | `/stock/market-data` | `tr_cd: t1101`, body `t1101InBlock.shcode` |
| 주식 잔고조회2 | `/stock/accno` | `tr_cd: t0424`, body `t0424InBlock` |
| 현물주문 | `/stock/order` | `tr_cd: CSPAT00601`, body `CSPAT00601InBlock1` |
| 현물정정주문 | `/stock/order` | `tr_cd: CSPAT00701`, body `CSPAT00701InBlock1` |
| 현물취소주문 | `/stock/order` | `tr_cd: CSPAT00801`, body `CSPAT00801InBlock1` |

위 계약은 `agent/tests/test_ls_kiwoom_rest_contract.py`에서 token, quote, balance, order, modify, cancel request shape와 응답 파싱으로 고정한다. `CSPAT00801`은 공식 body에 `OrdQty`가 필수이므로 수량 없는 취소 요청은 adapter가 fail-closed한다.

## DB증권 Open API REST 계약

| 기능 | Path | TR / Header |
|---|---|---|
| OAuth token | `/oauth2/token` | form `appkey`, `appsecretkey`, `grant_type=client_credentials`, `scope=oob`, `content-type: application/x-www-form-urlencoded` |
| 현재가조회 | `/api/v1/quote/kr-stock/inquiry/price` | `PRICE`, body `In.InputIscd1`, `In.InputCondMrktDivCode` |
| 주식잔고조회 | `/api/v1/trading/kr-stock/inquiry/balance` | `CSPAQ03420`, body `In.QryTpCode0` |
| 체결/미체결조회 | `/api/v1/trading/kr-stock/inquiry/transaction-history` | `CSPAQ04800`, body `In.ExecYn`, `BnsTpCode`, `IsuTpCode`, `QryTp`, `TrdMktCode`, `SorTpYn` |
| 주식종합주문 | `/api/v1/trading/kr-stock/order` | `CSPAT00600`, body `In` |
| 주식정정주문 | `/api/v1/trading/kr-stock/order-revision` | `CSPAT00700`, body `In` |
| 주식취소주문 | `/api/v1/trading/kr-stock/order-cancel` | `CSPAT00800`, body `In` |
| 주식종합주문-NXT | `/api/v1/trading/kr-stock/order-nxt` | `CSPAT00610`, body `In` |
| 주식정정주문-NXT | `/api/v1/trading/kr-stock/order-revision-nxt` | `CSPAT00710`, body `In` |
| 주식취소주문-NXT | `/api/v1/trading/kr-stock/order-cancel-nxt` | `CSPAT00810`, body `In` |

모든 DB증권 REST 업무 호출은 `authorization: Bearer <token>`, `cont_yn: N`, `cont_key: ""`, `content-type: application/json; charset=utf-8` 헤더를 사용한다. `agent/tests/test_db_rest_contract.py`가 token, quote, balance, transaction-history, KRX/NXT order, modify, cancel request shape와 응답 파싱으로 고정한다. `CSPAT00800`과 `CSPAT00810`은 공식 body에 `OrdQty`가 필수이므로 수량 없는 취소 요청은 adapter가 fail-closed한다.

## DB증권 Open API WebSocket 계약

| 기능 | Endpoint / Path | TR / Message |
|---|---|---|
| 운영 WebSocket | `wss://openapi.dbsec.co.kr:7070` | 공식 API list의 국내주식 실시간 domain |
| 모의 WebSocket | `wss://openapi.dbsec.co.kr:17070` | 공식 API list의 국내주식 실시간 simulatedDomain |
| 실시간 주식체결가 | `/pub/S00` | subscribe body `{"tr_cd": "S00", "tr_key": "J 005930"}` |
| 실시간 주식호가 | `/pub/S01` | subscribe body `{"tr_cd": "S01", "tr_key": "J 005930"}` |
| 실시간 주식주문접수 | `/pub/IS0` | account event body `{"tr_cd": "IS0"}`, header `tr_type: "3"` |
| 실시간 주식주문체결 | `/pub/IS1` | account event body `{"tr_cd": "IS1"}`, header `tr_type: "3"` |
| WebSocket session reset | `/api/v1/websocket/disconnectSession` | `DisconnectSession`, TPS 1 |

`S00`/`S01` quote stream은 header `token`, `tr_type: "1"`과 `tr_key` 형식 `J <종목코드>`를 사용한다. `IS0`/`IS1` 주문 event stream은 공식 예제처럼 `tr_type: "3"`을 사용하고 symbol key를 붙이지 않는다. `agent/tests/test_db_rest_contract.py`가 WebSocket endpoint catalog, subscribe message shape, S00/S01 event parser, `DisconnectSession` REST request shape를 고정한다. 실제 WebSocket handshake, subscription, event 수신 smoke는 DB access token과 계정이 준비된 뒤 별도 evidence로 닫는다.

## 키움 REST OpenAPI 계약

| 기능 | Path | API ID |
|---|---|---|
| OAuth token | `/oauth2/token` | body `grant_type`, `appkey`, `secretkey`; response `token` |
| 주식기본정보요청 | `/api/dostk/stkinfo` | `ka10001` |
| 주식일봉차트조회요청 | `/api/dostk/chart` | `ka10081` |
| 계좌평가잔고내역요청 | `/api/dostk/acnt` | `kt00018` |
| 미체결요청 | `/api/dostk/acnt` | `ka10075` |
| 주식 매수주문 | `/api/dostk/ordr` | `kt10000` |
| 주식 매도주문 | `/api/dostk/ordr` | `kt10001` |
| 주식 정정주문 | `/api/dostk/ordr` | `kt10002` |
| 주식 취소주문 | `/api/dostk/ordr` | `kt10003` |

모든 키움 REST 업무 호출은 `authorization: Bearer <token>`, `cont-yn`, `next-key`, `api-id` 헤더를 사용한다. `agent/tests/test_ls_kiwoom_rest_contract.py`가 quote, daily bars, balance, open orders, buy/sell order, modify order, cancel request shape를 고정한다.

## Windows local_bridge 계약

키움 OpenAPI+와 대신 CYBOS/CREON Plus는 Windows COM/OCX API라서 macOS/Linux 프로세스에서 직접 호출하지 않는다. Vibe-Trading은 read-only localhost bridge만 호출한다.

| 기능 | Method/Path | 비고 |
|---|---|---|
| Health | `GET /health` | bridge version, connector, login/readiness 상태 |
| Account | `GET /account` | 계좌 요약 |
| Positions | `GET /positions` | 보유잔고 |
| Open orders | `GET /orders?include_executions=true|false` | 미체결/선택적 체결 내역 |
| Quote | `GET /quote/{symbol}` | 한국 종목코드는 `005930`, `005930.KS`, `KRX:005930`를 `005930`으로 정규화 |
| History | `GET /history/{symbol}?period=1d&limit=90` | 기간봉/일봉 bridge 응답 |

모든 bridge 호출은 `Authorization: Bearer <bridge_token>`, `X-Vibe-Connector`, `X-Vibe-Transport: local_bridge` 헤더를 사용한다. `agent/tests/test_kr_local_bridge_contract.py`가 이 계약을 고정한다. 주문 path는 아직 노출하지 않으며, bridge profile은 read-only다.

## 현재 구현 범위

- `kr_equity`, `kr_etf`, `kr_derivative`, `kr_bond`, `kr_elw` asset class가 mandate universe에 추가됨.
- `local_bridge` transport가 추가되어 macOS/Linux 본체가 Windows COM/OCX API를 직접 호출하지 않음.
- KIS는 국내주식 현재가, 기간별시세, 잔고조회, 정정취소 가능 주문조회, 현금주문, 정정취소 REST contract와 국내주식 실시간 WebSocket endpoint/channel/message/parser contract를 mockable adapter로 구현함.
- LS는 token, `t1101` 현재가, `t0424` 잔고조회, `CSPAT00601` 현물주문, `CSPAT00701` 정정주문, `CSPAT00801` 취소주문 REST contract와 mockable adapter를 구현함.
- DB증권은 token, `PRICE` 현재가, `CSPAQ03420` 잔고조회, `CSPAQ04800` 체결/미체결조회, `CSPAT00600` 주문, `CSPAT00700` 정정주문, `CSPAT00800` 취소주문, NXT `CSPAT00610` 주문, `CSPAT00710` 정정주문, `CSPAT00810` 취소주문 REST contract와 `S00/S01/IS0/IS1` WebSocket contract, `DisconnectSession` contract를 구현함.
- 키움 REST는 token, `ka10001`, `ka10081`, `kt00018`, `ka10075`, `kt10000`, `kt10001`, `kt10002`, `kt10003` REST contract와 mockable adapter를 구현함.
- 키움 OpenAPI+와 대신 CYBOS/CREON Plus는 read-only Windows bridge profile과 local bridge HTTP contract를 구현함.
- Backtest는 `kr_equity` 시장 감지, `source="auto"` yfinance/akshare fallback, `.KS`/`.KQ` Yahoo 호환 심볼 변환, KOSPI `^KS11` benchmark, `GlobalEquityEngine(market="kr")`의 1주 단위/long-only 기본값/±30% 가격제한 차단 계약을 구현함.
- 모든 신규 connector는 설정이 없을 때 `not configured`로 fail-closed 하며, 주문형 profile은 live에서 `orders.place.requires_mandate` capability를 표시함.
- KIS `check_status`는 token 발급이 알림톡 등 브로커 알림을 유발할 수 있으므로 자동 token probe를 실행하지 않는다. 실제 read/order 호출 시 명시적으로 인증한다.

## 다음 닫아야 할 검증

- 공통: [한국시장 자격증명 smoke 검증 Runbook](credential-smoke-runbook.md)에 따라 no-call baseline과 credentialed smoke를 분리하고, `broker_calls_proven` 또는 `data_calls_proven`이 `true`인 audit report가 있을 때만 실연동 완료로 표시한다.
- KIS: app key/secret, 계좌번호/상품코드가 준비되면 quote/history/account/open-orders/order mock 계정 smoke, `inquire-psbl-rvsecncl` 연속조회 evidence, WebSocket approval key 발급/handshake/구독/수신 smoke, 체결통보 복호화 smoke, 최소 주문/취소 evidence.
- LS: mock 계정 read/order/modify/cancel smoke.
- DB증권: mock 계정 read/order/modify/cancel/NXT smoke, 실제 WebSocket 연결/구독/수신 smoke, 파생/해외/채권 contract 확장.
- 키움 REST: 모의 계정 read/order/modify/cancel smoke.
- Windows bridge: Kiwoom OpenAPI+와 Daishin CYBOS/CREON Plus를 실제 Windows PC/VM에서 실행해 `/health`, quote/account/positions/history smoke와 bridge server allowlist를 검증.
- 토스증권: 사전신청 이후 공개 API 문서와 credential surface가 열리면 REST/WebSocket contract를 추가.
- 유진/유안타/NH: 공식 Windows 모듈과 TR 명세가 확보되면 read-only `local_bridge` profile부터 추가.
- KRX/코스콤: 브로커가 아닌 한국시장 data/backtest loader 후보로 분리하고 인증키, 라이선스/재배포 조건, quote/bar endpoint contract를 확인.
- Backtest settlement: KRX T+2 결제에 맞춘 현금 잠금/settlement ledger 모델을 추가하고 KRX 휴장일 calendar와 NXT/정규장 시간 분리를 검증.
- 실계좌: 브로커별 explicit user approval, mandate snapshot, kill switch clear 상태, 최소 주문/즉시 취소 audit evidence.
