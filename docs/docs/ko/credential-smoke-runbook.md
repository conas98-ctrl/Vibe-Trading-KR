# 한국시장 자격증명 smoke 검증 Runbook

이 문서는 한국시장 포크의 contract-only 구현을 실제 브로커/데이터 자격증명으로 닫을 때 사용하는 절차다. 명령이 성공하더라도 raw evidence와 audit report가 함께 남지 않으면 실연동 완료로 표시하지 않는다.

## 목적

- 브로커 connector smoke와 audit 결과를 같은 실행 묶음으로 남긴다.
- KRX/코스콤 같은 한국시장 데이터 소스 smoke와 audit 결과를 별도로 남긴다.
- 자격증명 없는 baseline과 자격증명 있는 실행을 구분해, 계획 파일만으로 실호출을 증명하지 않도록 한다.
- secret, account token, app secret, bridge token, live order payload가 저장소에 들어가지 않게 한다.

## 사전 조건

- 이 Runbook의 명령은 브로커/data-source smoke CLI와 audit CLI가 포함된 브랜치 또는 병합 후 트리에서 실행한다.
- 브로커별 모의투자 또는 실계좌 API 사용 승인이 끝나 있어야 한다.
- 실계좌 주문 smoke는 사용자의 명시 승인, mandate snapshot, kill switch 해제 확인, 최소 주문/즉시 취소 계획이 별도로 있어야 한다.
- KIS, LS, DB, 키움 REST는 브로커 포털의 app key/secret과 계좌번호/상품코드가 필요하다.
- 키움 OpenAPI+와 대신 CYBOS/CREON Plus는 Windows PC/VM에서 로그인된 read-only bridge가 필요하다.
- KRX/코스콤 데이터 smoke는 인증키, 정보시세 라이선스, 재배포 가능 범위 확인이 필요하다.

로컬 evidence는 저장소 밖이나 ignore되는 경로에 둔다.

```bash
export KR_SMOKE_DIR="outputs/kr-smoke/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$KR_SMOKE_DIR"
chmod 700 "$KR_SMOKE_DIR"
```

## 0. 자격증명 설정

브로커별 app secret, access token, bridge token은 명령 출력에 표시하지 않는다. Shell history에 secret 값이 남지 않도록 가능하면 환경변수 이름을 넘긴다. 설정 파일은 `~/.vibe-trading` 아래 connector별 JSON으로 저장되며 `0600` 권한을 사용한다.

KIS/LS/DB/키움 REST SDK profile은 app key와 app secret이 필요하다. 계좌 조회, 잔고, 미체결, 주문 smoke를 실행하려면 계좌번호와 상품코드도 함께 설정한다.

```bash
export KIS_APP_KEY="..."
export KIS_APP_SECRET="..."

vibe-trading connector configure kis-paper-sdk \
  --app-key-env KIS_APP_KEY \
  --app-secret-env KIS_APP_SECRET \
  --account "12345678" \
  --account-product-code "01" \
  --yes
```

같은 형식으로 `ls-paper-sdk`, `db-paper-sdk`, `kiwoom-paper-sdk`를 설정한다. live read-only 또는 live trading profile을 설정할 때는 profile id를 `kis-live-sdk-readonly`, `kis-live-trade`처럼 바꾼다. 실계좌 주문 profile은 이 설정만으로 실행되지 않으며, 별도 mandate, kill switch, pre-trade gate가 통과해야 한다.

Windows COM/OCX bridge profile은 bridge URL과 bridge token이 필요하다. bridge process는 Windows PC/VM에서 사용자가 직접 실행하고 로그인한 상태여야 한다.

```bash
export KIWOOM_BRIDGE_TOKEN="..."

vibe-trading connector configure kiwoom-openapi-live-bridge-readonly \
  --bridge-url "http://127.0.0.1:8765" \
  --bridge-token-env KIWOOM_BRIDGE_TOKEN \
  --yes
```

대신 CYBOS/CREON Plus는 `daishin-cybos-live-bridge-readonly` profile을 같은 방식으로 설정한다. 설정 뒤에는 broker call을 허용하기 전에 먼저 readiness만 확인한다.

```bash
vibe-trading connector check kis-paper-sdk
vibe-trading connector check kiwoom-openapi-live-bridge-readonly
```

## 1. 브로커 no-call baseline

먼저 자격증명 없이 plan-only evidence를 만든다. 이 단계의 목적은 명령 wiring과 redaction을 확인하는 것이며, 실호출 증거가 아니다.

```bash
vibe-trading connector smoke \
  --profile kis-paper-sdk \
  --output "$KR_SMOKE_DIR/broker-plan.json"

vibe-trading connector smoke-audit \
  --evidence "$KR_SMOKE_DIR/broker-plan.json" \
  --output "$KR_SMOKE_DIR/broker-plan.audit.json" \
  --json
```

기대값:

- audit `status`는 `ok`.
- `broker_calls_proven`은 `false`.
- 결과 파일 권한은 민감 출력 기준으로 제한되어야 한다.
- 이 결과만으로 `paper-smoke`나 `live-gated` 완료를 주장하지 않는다.

## 2. 브로커 credentialed smoke

자격증명이 준비되면 read-only 작업부터 실행한다. 주문 smoke는 별도 승인 전에는 포함하지 않는다.

```bash
vibe-trading connector smoke \
  --profile kis-paper-sdk \
  --operation check \
  --operation quote \
  --operation account \
  --operation positions \
  --operation orders \
  --allow-broker-calls \
  --output "$KR_SMOKE_DIR/kis-paper-read.json"

vibe-trading connector smoke-audit \
  --evidence "$KR_SMOKE_DIR/kis-paper-read.json" \
  --require-broker-calls \
  --output "$KR_SMOKE_DIR/kis-paper-read.audit.json" \
  --json
```

브로커별 profile 예시는 다음과 같다. 실제 이름은 `vibe-trading connector list`로 확인한다.

| 브로커 | 우선 smoke profile | 기본 범위 |
|---|---|---|
| KIS | `kis-paper-sdk` | check, quote, account, positions, open orders, history |
| LS증권 | `ls-paper-sdk` | token, quote, balance, open orders, order/modify/cancel paper gate |
| DB증권 | `db-paper-sdk` | token, quote, balance, transaction history, KRX/NXT paper gate |
| 키움 REST | `kiwoom-paper-sdk` | token, quote, daily bars, account, open orders |
| 키움 OpenAPI+ bridge | `kiwoom-openapi-bridge` | health, account, positions, orders, quote, history |
| 대신 CYBOS bridge | `daishin-cybos-bridge` | health, account, positions, orders, quote, history |

실계좌 주문 smoke를 실행할 때만 `--allow-live`를 추가한다. 이 경우 evidence에는 explicit approval, mandate snapshot, kill switch 상태, 주문 수량/가격 제한, 즉시 취소 결과가 모두 있어야 한다.

## 3. 한국시장 데이터 no-call baseline

KRX/코스콤 같은 데이터 소스도 브로커 smoke와 별도로 baseline을 남긴다.

```bash
vibe-trading data-source smoke \
  --json \
  --output "$KR_SMOKE_DIR/data-plan.json"

vibe-trading data-source smoke-audit \
  --evidence "$KR_SMOKE_DIR/data-plan.json" \
  --output "$KR_SMOKE_DIR/data-plan.audit.json" \
  --json
```

기대값:

- audit `status`는 `ok`.
- `data_calls_proven`은 `false`.
- KRX/코스콤 loader가 아직 자격증명 없이 닫혔다고 표시하지 않는다.

## 4. 한국시장 데이터 credentialed smoke

인증키와 라이선스 범위가 확인된 뒤에만 실제 데이터 호출을 허용한다.

```bash
vibe-trading data-source smoke \
  --source krx \
  --symbol 005930.KS \
  --allow-data-calls \
  --json \
  --output "$KR_SMOKE_DIR/krx-005930.json"

vibe-trading data-source smoke-audit \
  --evidence "$KR_SMOKE_DIR/krx-005930.json" \
  --require-data-calls \
  --output "$KR_SMOKE_DIR/krx-005930.audit.json" \
  --json
```

코스콤을 사용할 때도 같은 기준을 적용한다. 라이선스가 quote 조회만 허용하고 재배포를 금지한다면, raw response를 공개 PR에 첨부하지 않는다.

## 5. 완료 기준

브로커 smoke 완료는 아래 항목이 모두 충족될 때만 인정한다.

- raw evidence와 audit report가 모두 존재한다.
- audit report `status`가 `ok`다.
- credentialed run에서 `broker_calls_proven`이 `true`다.
- 주문 smoke를 포함했다면 주문 제출, 체결 여부, 취소 또는 정리 결과, audit ledger가 모두 남아 있다.
- secret, token, 계좌 비밀번호, app secret이 파일에 남아 있지 않다.

데이터 smoke 완료는 아래 항목이 모두 충족될 때만 인정한다.

- raw evidence와 audit report가 모두 존재한다.
- audit report `status`가 `ok`다.
- credentialed run에서 `data_calls_proven`이 `true`다.
- 라이선스/재배포 제한 때문에 공개할 수 없는 raw response는 redacted evidence로 대체하고, 로컬 보관 경로와 검증자만 기록한다.

## 6. 실패 처리

- `broker_calls_proven: false` 또는 `data_calls_proven: false`가 나오면 실연동 완료가 아니라 blocked/manual gate로 남긴다.
- `not_run`, `missing_operations`, `secret_detected`, `audit_error`가 있으면 해당 브로커나 데이터 소스는 완료로 표시하지 않는다.
- 자격증명 부족, 포털 승인 지연, Windows bridge 미기동, 라이선스 불명확성은 실패가 아니라 닫히지 않은 검증 게이트로 기록한다.
- 실패한 evidence도 원인 분석에는 보존하되, 공개 PR에는 secret이 제거된 요약만 올린다.

## 7. 하지 말 것

- app secret, access token, bridge token, 계좌 비밀번호를 README, PR body, issue comment에 붙이지 않는다.
- no-call baseline evidence를 실호출 증거처럼 쓰지 않는다.
- 실계좌 주문을 사용자 승인 없이 실행하지 않는다.
- KIS `check_status`처럼 token 발급이 브로커 알림을 유발할 수 있는 작업을 자동 probe로 돌리지 않는다.
- 문서 PR에 새로운 브로커 기능 구현, backtest routing, live safety 변경을 섞지 않는다.
