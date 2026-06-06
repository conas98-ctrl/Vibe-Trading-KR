export const DOCS_DEFAULT_VERSION = "0.1.9";
export const DOCS_LATEST_ALIAS = "latest";
export const DOCS_DEFAULT_PAGE = "getting-started/vibe-trading-overview";

export const DOCS_VERSIONS = [
  { name: "0.1.9", label: "0.1.9 (latest)" },
  { name: "0.1.8", label: "0.1.8" },
  { name: "0.1.7", label: "0.1.7" }
];

export const DOCS_STRUCTURE = [
  {
    id: "getting-started",
    label: "Getting started",
    pages: [
      {
        id: "getting-started/vibe-trading-overview",
        title: "Vibe-Trading overview",
        description: "What Vibe-Trading is, where it fits, and what boundary it keeps.",
        lead: "Vibe-Trading is an open-source finance research workspace that turns natural-language prompts into market-data pulls, backtests, reports, and reusable research context.",
        sections: [
          {
            id: "what-it-is",
            title: "What it is",
            body: `
              <p>Vibe-Trading connects an agent loop to finance tools: data loaders, strategy generation, backtest engines, document readers, trade-journal analysis, persistent memory, and multi-agent research teams.</p>
              <p>The goal is not to replace judgment. The goal is to make every research step runnable, inspectable, and easy to repeat.</p>
            `
          },
          {
            id: "research-only",
            title: "Research only",
            body: `
              <p>Vibe-Trading does not execute live trades. It is designed for simulation, backtesting, audit trails, and research workflows. Outputs are not investment advice.</p>
            `
          },
          {
            id: "capabilities",
            title: "Core capabilities",
            body: `
              <ul>
                <li>Natural-language CLI and web workflows.</li>
                <li>Seven backtest engines across equities, crypto, futures, forex, composites, and options portfolios.</li>
                <li>Market data routing across Tushare, OKX, yfinance, AKShare, CCXT, and Futu.</li>
                <li>Trade Journal and Shadow Account workflows for behavior diagnostics.</li>
                <li>Swarm presets for committee-style research reviews.</li>
                <li>MCP tools for Claude Desktop, OpenClaw, Cursor, and other MCP clients.</li>
              </ul>
            `
          }
        ]
      },
      {
        id: "getting-started/quick-start",
        title: "Quick start",
        description: "Install Vibe-Trading, initialize configuration, and run the first research task.",
        lead: "The fastest path is PyPI install, interactive setup, then either CLI research or the local web UI.",
        sections: [
          {
            id: "install",
            title: "Install",
            body: `
              <pre><code>pip install vibe-trading-ai
vibe-trading init
vibe-trading</code></pre>
            `
          },
          {
            id: "first-run",
            title: "First run",
            body: `
              <pre><code>vibe-trading run -p "Backtest a BTC-USDT 20/50 moving-average strategy for 2024, summarize return and drawdown, then export the report"</code></pre>
            `
          },
          {
            id: "web-ui",
            title: "Open the web UI",
            body: `
              <pre><code>vibe-trading serve --port 8899</code></pre>
              <p>The local web UI is useful when you want uploaded files, streaming swarm progress, Settings, and generated artifacts in one place.</p>
            `
          }
        ]
      },
      {
        id: "getting-started/configuration",
        title: "Configuration",
        description: "Provider, model, market-data, and deployment settings.",
        lead: "Vibe-Trading keeps secrets and deployment-specific choices in environment variables or local Settings, not in source files.",
        sections: [
          {
            id: "env",
            title: "Environment file",
            body: `
              <pre><code>LANGCHAIN_PROVIDER=deepseek
LANGCHAIN_MODEL_NAME=deepseek-v4-pro
TUSHARE_TOKEN=your-token
TIMEOUT_SECONDS=2400</code></pre>
              <p>Run <code>vibe-trading init</code> to bootstrap the local configuration interactively.</p>
            `
          },
          {
            id: "keys",
            title: "Keys and data sources",
            body: `
              <p>Many HK, US, crypto, document, journal, and static analysis workflows work without paid market-data keys. A-share fundamental enrichment and some provider-specific workflows need their matching credentials.</p>
              <p>For non-local API or web deployments, configure <code>API_AUTH_KEY</code> and send requests with <code>Authorization: Bearer &lt;key&gt;</code>.</p>
            `
          },
          {
            id: "models",
            title: "Model choice",
            body: `
              <p>Agent quality depends on tool use. Prefer strong tool-calling models for long research runs, swarms, and multi-step backtests. Avoid small distilled models for workflows where fabricated answers are costly.</p>
            `
          }
        ]
      }
    ]
  },
  {
    id: "core-concepts",
    label: "Core concepts",
    pages: [
      {
        id: "core-concepts/research-workflow",
        title: "Research workflow",
        description: "How a Vibe-Trading run moves from prompt to evidence.",
        lead: "A good run routes the request, grounds it in data, executes tools, validates outputs, and leaves artifacts behind.",
        sections: [
          {
            id: "pipeline",
            title: "Pipeline",
            body: `
              <ol>
                <li><strong>Plan:</strong> choose relevant skills, tools, data sources, and swarm presets.</li>
                <li><strong>Ground:</strong> fetch market bars, documents, URLs, broker journals, or local files at runtime.</li>
                <li><strong>Execute:</strong> run backtests, factor analysis, options checks, exports, or report generation.</li>
                <li><strong>Validate:</strong> attach metrics, benchmark comparison, Monte Carlo, Bootstrap, Walk-Forward, warnings, and run cards when applicable.</li>
                <li><strong>Deliver:</strong> return the answer plus inspectable artifacts.</li>
              </ol>
            `
          },
          {
            id: "artifacts",
            title: "Artifacts",
            body: `
              <p>Backtests and research runs can produce reports, charts, generated strategy files, run metadata, and reusable context. The artifact trail matters because finance research often needs later inspection.</p>
            `
          }
        ]
      },
      {
        id: "core-concepts/backtesting",
        title: "Backtesting",
        description: "Market coverage, engines, metrics, and validation tools.",
        lead: "Vibe-Trading backtests daily and minute strategies across multiple asset classes, then keeps outputs auditable with metrics and run cards.",
        sections: [
          {
            id: "engines",
            title: "Engines",
            body: `
              <ul>
                <li>China A-share, global equity, crypto, China futures, global futures, forex, and composite engines.</li>
                <li>Options portfolio engine for option strategy research.</li>
                <li>Minute intervals including 1m, 5m, 15m, 30m, 1H, 4H, and 1D where supported by the data source.</li>
              </ul>
            `
          },
          {
            id: "validation",
            title: "Validation",
            body: `
              <p>Research runs can include benchmark comparison, Monte Carlo, Bootstrap confidence intervals, Walk-Forward validation, and run cards. Treat these as evidence helpers, not guarantees.</p>
            `
          },
          {
            id: "example",
            title: "Example",
            body: `
              <pre><code>vibe-trading run -p "Backtest an equal-weight SPY and BTC-USDT momentum rotation strategy for 2024 with benchmark comparison"</code></pre>
            `
          }
        ]
      },
      {
        id: "core-concepts/swarm-teams",
        title: "Swarm teams",
        description: "Preset research teams for committee-style analysis.",
        lead: "Swarm presets turn a research question into a small DAG of specialist workers, then stream progress and persist the final report.",
        sections: [
          {
            id: "presets",
            title: "Presets",
            body: `
              <p>Vibe-Trading includes 29 presets such as investment committee, quant strategy desk, crypto trading desk, macro rates and FX desk, and risk committee.</p>
              <pre><code>vibe-trading --swarm-presets
vibe-trading --swarm-run investment_committee '{"topic":"BTC outlook"}'</code></pre>
            `
          },
          {
            id: "keys",
            title: "Model requirements",
            body: `
              <p>Most MCP tools work without an LLM key after install. <code>run_swarm</code> needs an LLM provider because it spawns internal worker agents.</p>
            `
          }
        ]
      }
    ]
  },
  {
    id: "tools",
    label: "Tools",
    pages: [
      {
        id: "tools/data-sources",
        title: "Data sources",
        description: "How Vibe-Trading routes symbols and market data providers.",
        lead: "Data routing is provider-aware: mixed symbols can use <code>source=\"auto\"</code> while each market keeps its own data rules.",
        sections: [
          {
            id: "providers",
            title: "Providers",
            body: `
              <ul>
                <li>Tushare for China market and fundamental workflows when configured.</li>
                <li>OKX and CCXT for crypto symbols such as <code>BTC-USDT</code>.</li>
                <li>yfinance for global equities and common benchmarks.</li>
                <li>AKShare and Futu for additional China, Hong Kong, and market-specific coverage.</li>
              </ul>
            `
          },
          {
            id: "symbols",
            title: "Symbol conventions",
            body: `
              <p>Crypto pairs use uppercase hyphen format, for example <code>BTC-USDT</code>. Mixed-market research should prefer automatic source routing where possible.</p>
            `
          }
        ]
      },
      {
        id: "tools/kiwoom-websocket-smoke-runbook",
        title: "Kiwoom WebSocket Smoke Runbook",
        description: "키움증권 REST OpenAPI 국내주식 WebSocket smoke를 안전하게 실행하고 evidence를 남기는 절차.",
        lead: "Kiwoom WebSocket smoke는 기본적으로 broker call을 하지 않으며, 실제 Kiwoom REST OpenAPI 네트워크 호출은 operator가 명시적으로 opt-in 했을 때만 실행됩니다.",
        sections: [
          {
            id: "official-surfaces",
            title: "공식 확인 표면",
            body: `
              <p>이 runbook은 키움증권 REST OpenAPI의 국내주식 WebSocket smoke 흐름을 Vibe-Trading에서 확인하기 위한 한국어 절차입니다. 대상 profile은 <code>kiwoom-paper-sdk</code>, <code>kiwoom-live-sdk-readonly</code>, <code>kiwoom-paper-trade</code>, <code>kiwoom-live-trade</code>입니다.</p>
              <ul>
                <li><a href="https://openapi.kiwoom.com/" target="_blank" rel="noreferrer">Kiwoom REST API 포털</a></li>
                <li><a href="https://openapi.kiwoom.com/guide/apiguide" target="_blank" rel="noreferrer">Kiwoom REST API 가이드</a></li>
                <li><a href="https://www.kiwoom.com/h/customer/download/VOpenApiInfoView?dummyVal=0" target="_blank" rel="noreferrer">Kiwoom Open API+ Windows COM 안내</a></li>
              </ul>
              <p>Kiwoom REST API 포털은 OAuth 접근토큰, 국내주식 계좌/시세/실시간시세/조건검색/주문 API, 운영 도메인 <code>https://api.kiwoom.com</code>, 모의투자 REST 도메인 <code>https://mockapi.kiwoom.com</code>을 안내합니다. Vibe-Trading의 Kiwoom WebSocket smoke는 공식 REST WebSocket endpoint <code>wss://api.kiwoom.com:10000/api/dostk/websocket</code>와 <code>LOGIN</code>, <code>REG</code>, <code>PING</code> frame 계약을 작게 감싼 credential-gated 확인 흐름입니다.</p>
              <p>Windows 전용 Kiwoom Open API+ OCX bridge는 별도 connector family입니다. 이 runbook은 REST OpenAPI WebSocket smoke만 다루며, Open API+ 설치, OCX 등록, KOA Studio, Windows bridge smoke는 완료로 claim하지 않습니다.</p>
            `
          },
          {
            id: "prerequisites",
            title: "준비물",
            body: `
              <ol>
                <li>Kiwoom REST API 사용신청이 완료된 계정.</li>
                <li>REST OpenAPI용 app key와 secret key.</li>
                <li><code>~/.vibe-trading/kiwoom.json</code> 로컬 설정 파일. 이 파일은 저장소에 커밋하지 않습니다.</li>
                <li>Credentialed smoke를 수행할 시장 시간과 Kiwoom API 이용 조건 확인.</li>
              </ol>
              <pre><code>{
  "profile": "paper",
  "app_key": "YOUR_KIWOOM_APP_KEY",
  "app_secret": "YOUR_KIWOOM_SECRET_KEY",
  "access_token": "OPTIONAL_PREISSUED_ACCESS_TOKEN"
}</code></pre>
              <p><code>profile</code>은 <code>paper</code>, <code>live-readonly</code>, <code>live</code> 중 하나입니다. Kiwoom REST guide는 모의투자 REST 도메인을 안내하지만, 이 WebSocket smoke의 실계정 수신 proof는 실제 credential, endpoint, 계정 권한, 장중 수신 가능 상태를 별도로 확인하기 전까지 claim하지 않습니다.</p>
            `
          },
          {
            id: "dry-run",
            title: "Dry-run 확인",
            body: `
              <p>기본 명령은 broker call을 하지 않습니다. credential이나 network가 준비되지 않은 CI, 리뷰 환경, 문서 검증에서는 이 명령을 먼저 사용합니다.</p>
              <pre><code>vibe-trading connector kiwoom-websocket-smoke \\
  --profile kiwoom-paper-sdk \\
  --channel domestic_stock_realtime \\
  --symbol 005930 \\
  --evidence-path ~/.vibe-trading/evidence/kiwoom-websocket-smoke-domestic-stock.json</code></pre>
              <p>예상 결과는 <code>status=not_run</code>, <code>network=not_attempted</code>, <code>evidence_path=null</code>입니다. 이 상태는 실패가 아니라 안전 기본값입니다. 실제 token 사용, WebSocket 연결, evidence 파일 생성은 <code>--allow-broker-calls</code>가 있어야 진행됩니다.</p>
            `
          },
          {
            id: "credentialed-smoke",
            title: "Credentialed smoke",
            body: `
              <p>credential과 이용 조건이 준비된 뒤에만 broker call을 켭니다. smoke는 주문을 넣지 않고 WebSocket login, subscription, ping/real frame 수신, redacted evidence 작성만 확인합니다.</p>
              <pre><code>vibe-trading connector kiwoom-websocket-smoke \\
  --profile kiwoom-paper-sdk \\
  --channel domestic_stock_realtime \\
  --symbol 005930 \\
  --evidence-path ~/.vibe-trading/evidence/kiwoom-websocket-smoke-domestic-stock.json \\
  --max-messages 3 \\
  --message-timeout 10 \\
  --allow-broker-calls</code></pre>
              <p>실전 읽기 전용 profile에서는 추가로 <code>--allow-live</code>가 필요합니다.</p>
              <pre><code>vibe-trading connector kiwoom-websocket-smoke \\
  --profile kiwoom-live-sdk-readonly \\
  --channel domestic_stock_realtime \\
  --symbol 005930 \\
  --evidence-path ~/.vibe-trading/evidence/kiwoom-websocket-smoke-live-readonly.json \\
  --max-messages 3 \\
  --message-timeout 10 \\
  --allow-broker-calls \\
  --allow-live</code></pre>
              <p>실전 주문 profile인 <code>kiwoom-live-trade</code>는 live order mandate, kill switch, pre-trade gate, audit ledger의 적용 대상입니다. WebSocket smoke 자체는 읽기/수신 확인용이지만, 실전 profile 접근은 별도 live opt-in 없이는 차단합니다.</p>
            `
          },
          {
            id: "channels",
            title: "채널 선택",
            body: `
              <ul>
                <li><code>domestic_stock_realtime</code>: 공식 REST WebSocket sample의 국내주식 실시간 channel. Vibe-Trading은 <code>LOGIN</code> frame 뒤 <code>REG</code> subscription을 보내며 기본 type code는 <code>0B</code>입니다.</li>
              </ul>
              <p><code>--symbol</code>은 국내주식 종목코드입니다. 예: <code>005930</code>. <code>KRX:039490</code>, <code>005930.KS</code>처럼 prefix/suffix가 붙은 값은 내부에서 숫자 종목코드로 정규화됩니다.</p>
              <p>전체 지원 채널은 CLI의 <code>--channel</code> choices와 MCP tool schema enum으로 노출됩니다. 잘못된 채널 이름이나 빈 symbol은 token 사용 또는 WebSocket 연결 전에 거부됩니다.</p>
            `
          },
          {
            id: "evidence",
            title: "Evidence 보관",
            body: `
              <p><code>--evidence-path</code>에는 로컬 전용 경로를 지정합니다. 권장 위치는 <code>~/.vibe-trading/evidence/</code>처럼 저장소 밖에 있는 디렉터리입니다.</p>
              <ul>
                <li>app key, secret key, access token은 기록하지 않습니다.</li>
                <li>subscription에는 symbol 원문 대신 <code>item_count</code>와 channel summary 중심으로 남깁니다.</li>
                <li>sample payload는 이벤트 종류와 field count 중심으로 축약하고 redaction을 한 번 더 적용합니다.</li>
                <li>계좌번호, token 원문, 주문 원문 frame, 민감한 체결 정보는 public PR이나 공개 문서에 붙이지 않습니다.</li>
              </ul>
              <p>Credentialed evidence에는 profile, endpoint, 수신 상태, channel summary가 포함될 수 있으므로 원본 JSON은 로컬에 보관합니다. 공개 PR에는 어떤 profile/channel을 어떤 opt-in으로 확인했는지와 redaction 방침만 요약합니다.</p>
            `
          },
          {
            id: "cli-mcp-tool",
            title: "CLI / MCP 경로",
            body: `
              <p>CLI에서는 <code>vibe-trading connector kiwoom-websocket-smoke</code>를 사용합니다. MCP client에서는 <code>trading_kiwoom_websocket_smoke</code> tool을 사용합니다. 필수 인자는 <code>symbol</code> 또는 <code>symbols</code>, <code>evidence_path</code>입니다. <code>allow_broker_calls</code> 기본값은 <code>false</code>이며, 실전 profile은 <code>allow_live=true</code>도 요구합니다.</p>
              <pre><code>{
  "connection": "kiwoom-paper-sdk",
  "channel": "domestic_stock_realtime",
  "symbols": ["005930"],
  "evidence_path": "~/.vibe-trading/evidence/kiwoom-websocket-smoke-domestic-stock.json",
  "max_messages": 3,
  "message_timeout": 10,
  "allow_broker_calls": true
}</code></pre>
            `
          },
          {
            id: "non-claims",
            title: "아직 claim하지 않는 것",
            body: `
              <p>이 runbook은 절차와 safety gate를 고정합니다. 다음 항목은 실제 계정 credential, Kiwoom REST API 신청 상태, 시장 시간, 이용 조건 확인 전까지 완료로 claim하지 않습니다.</p>
              <ul>
                <li>실제 Kiwoom WebSocket에서 frame을 수신했다는 credentialed proof.</li>
                <li>실전 주문 가능성 또는 실전 주문 권한.</li>
                <li>Kiwoom market data의 재배포, 저장, 공개 공유 허용 여부.</li>
                <li>REST WebSocket channel별 운영 한도와 rate-limit의 포괄 검증.</li>
                <li>Windows Open API+ OCX bridge 설치, 로그인, KOA Studio, COM event smoke.</li>
                <li>장중/장후/휴장일별 수신 품질 보장.</li>
              </ul>
              <p>Credentialed smoke를 수행한 뒤에는 로컬 evidence JSON을 검토하고, public PR에는 원본 credential/evidence를 공개하지 않았다는 요약만 남깁니다.</p>
            `
          }
        ]
      },
      {
        id: "tools/shadow-account",
        title: "Shadow Account",
        description: "Turn a broker journal into behavior diagnostics and a counterfactual strategy path.",
        lead: "Shadow Account starts with your real trading records, extracts recurring rules, and compares actual trades with a rule-based shadow strategy.",
        sections: [
          {
            id: "flow",
            title: "Workflow",
            body: `
              <ol>
                <li>Read a broker export from supported formats or a generic CSV.</li>
                <li>Profile holding time, win rate, drawdown, PnL ratio, and behavior signals.</li>
                <li>Extract recurring if-then strategy rules.</li>
                <li>Run a shadow backtest and attribute delta-PnL.</li>
                <li>Render an HTML/PDF audit report.</li>
              </ol>
            `
          },
          {
            id: "example",
            title: "Example",
            body: `
              <pre><code>vibe-trading --upload trades_export.csv
vibe-trading run -p "Analyze my trading behavior, extract my shadow strategy, and compare it with my actual trades"</code></pre>
            `
          }
        ]
      },
      {
        id: "tools/finance-skills",
        title: "Finance skills",
        description: "Reusable finance knowledge modules loaded into research runs.",
        lead: "Skills keep domain knowledge close to the agent without hardcoding every behavior into the core loop.",
        sections: [
          {
            id: "library",
            title: "Library",
            body: `
              <p>Vibe-Trading bundles specialized skills across data sources, strategy generation, analysis, options, reporting, tools, and risk workflows.</p>
              <p>Good prompts can ask the agent to load or create skills for repeated research patterns.</p>
            `
          },
          {
            id: "examples",
            title: "Examples",
            body: `
              <ul>
                <li>Dividend analysis and yield-trap checks.</li>
                <li>A-share pre-ST risk screening.</li>
                <li>vn.py export and Pine Script export workflows.</li>
                <li>Factor research, macro analysis, and technical patterns.</li>
              </ul>
            `
          }
        ]
      }
    ]
  },
  {
    id: "reference",
    label: "Reference",
    pages: [
      {
        id: "reference/cli",
        title: "CLI reference",
        description: "Common commands for local research, web UI, memory, swarms, and files.",
        lead: "The CLI is the fastest operator surface for repeatable research tasks.",
        sections: [
          {
            id: "commands",
            title: "Common commands",
            body: `
              <pre><code>vibe-trading
vibe-trading init
vibe-trading run -p "your research prompt"
vibe-trading --upload report.pdf
vibe-trading memory list
vibe-trading serve --port 8899
vibe-trading-mcp</code></pre>
            `
          },
          {
            id: "interactive",
            title: "Interactive mode",
            body: `
              <p>Interactive mode supports slash commands for recent runs, swarm presets, memory, and research navigation.</p>
            `
          }
        ]
      },
      {
        id: "reference/mcp-server",
        title: "MCP server",
        description: "Expose Vibe-Trading tools to MCP-compatible clients.",
        lead: "The MCP server runs as a stdio subprocess and exposes Vibe-Trading tools to agent clients.",
        sections: [
          {
            id: "start",
            title: "Start",
            body: `
              <pre><code>vibe-trading-mcp</code></pre>
            `
          },
          {
            id: "config",
            title: "Client config",
            body: `
              <pre><code>{
  "mcpServers": {
    "vibe-trading": {
      "command": "vibe-trading-mcp"
    }
  }
}</code></pre>
            `
          },
          {
            id: "tools",
            title: "Tool surface",
            body: `
              <p>The server exposes tools for skills, market data, backtesting, factor analysis, options, web/document reading, trade journals, Shadow Account, and swarm runs.</p>
            `
          }
        ]
      },
      {
        id: "reference/cloudflare-pages",
        title: "Cloudflare Pages",
        description: "Deploy this wiki without running a server.",
        lead: "The wiki is static. Cloudflare Pages can serve it directly from the repository.",
        sections: [
          {
            id: "settings",
            title: "Pages settings",
            body: `
              <ul>
                <li>Project root: <code>wiki</code></li>
                <li>Build command: leave empty</li>
                <li>Output directory: <code>.</code></li>
                <li>Custom domain: <code>vibetrading.wiki</code></li>
              </ul>
            `
          },
          {
            id: "why-static",
            title: "Why static",
            body: `
              <p>Docs, landing copy, redirects, theme state, and client-side search all work as static files. No VPS, database, or server process is required.</p>
            `
          }
        ]
      }
    ]
  }
];
