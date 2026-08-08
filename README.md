# Codex Orchestra

Reusable settings-only control plane for Codex multi-agent projects.

`main` is the generic template. Project branches are examples/snapshots, not sources to merge wholesale:

- `orchestra/us-stock`
- `orchestra/idx-trade`
- `orchestra/biohub`

No project source code, market/competition data, model artifacts, credentials, or runtime caches belong in this repository.

## How it works

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#ffffff","primaryTextColor":"#0f172a","lineColor":"#334155","fontFamily":"Inter, ui-sans-serif, system-ui, sans-serif","fontSize":"16px","clusterBkg":"#ffffff","clusterBorder":"#cbd5e1"},"flowchart":{"curve":"basis","nodeSpacing":34,"rankSpacing":46,"padding":14}}}%%
flowchart TB
    U([User / research lead]) --> M[MAIN orchestrator]
    M --> D{Task complexity}

    subgraph SD[DIRECT · one bounded task]
        direction TB
        DIRECT[DIRECT]
        I[Implement + verify]
        DIRECT --> I
    end

    subgraph SL[LIGHT · 2–3 independent paths]
        direction TB
        LIGHT[LIGHT]
        W1[Worker A]
        W2[Worker B]
        INT[MAIN integrates]
        LIGHT --> W1
        LIGHT --> W2
        W1 --> INT
        W2 --> INT
    end

    subgraph SH[HEAVY · parallel / high-risk]
        direction TB
        HEAVY[HEAVY]
        H1[Worker A]
        H2[Worker B]
        H3[Worker C]
        H4[Independent review]
        HINT[MAIN integrates]
        HEAVY --> H1
        HEAVY --> H2
        HEAVY --> H3
        HEAVY --> H4
        H1 --> HINT
        H2 --> HINT
        H3 --> HINT
        H4 --> HINT
    end

    D -->|small + bounded| DIRECT
    D -->|2–3 paths| LIGHT
    D -->|large / high-risk| HEAVY

    I --> G[Validation / gate]
    INT --> G
    HINT --> G
    G -->|PASS| DONE([Done / next task])
    G -.->|FAIL · revise| M

    classDef user fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#0c4a6e,font-weight:700;
    classDef main fill:#ede9fe,stroke:#7c3aed,stroke-width:2.5px,color:#4c1d95,font-weight:800;
    classDef decision fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f,font-weight:700;
    classDef direct fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d,font-weight:700;
    classDef light fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a8a,font-weight:700;
    classDef heavy fill:#fee2e2,stroke:#dc2626,stroke-width:2px,color:#7f1d1d,font-weight:700;
    classDef gate fill:#fef3c7,stroke:#ca8a04,stroke-width:2.5px,color:#713f12,font-weight:800;
    classDef done fill:#dcfce7,stroke:#16a34a,stroke-width:2.5px,color:#14532d,font-weight:800;

    class U user;
    class M main;
    class D decision;
    class DIRECT,I direct;
    class LIGHT,W1,W2,INT light;
    class HEAVY,H1,H2,H3,H4,HINT heavy;
    class G gate;
    class DONE done;

    style SD fill:#f0fdf4,stroke:#86efac,stroke-width:1.5px
    style SL fill:#eff6ff,stroke:#93c5fd,stroke-width:1.5px
    style SH fill:#fef2f2,stroke:#fca5a5,stroke-width:1.5px
```

### Orchestration levels

| Level | Use when | Shape |
|---|---|---|
| **DIRECT** | One bounded task, little coordination value | MAIN works directly |
| **LIGHT** | A few independent workstreams can run in parallel | MAIN + 2–3 workers |
| **HEAVY** | Large/high-risk work with real parallelism or independent review | MAIN + multiple workers/reviewer |

The rule is simple: **do not spawn workers just because slots exist.** Start DIRECT and promote only when parallelism helps the critical path.

## Model routing

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#ffffff","primaryTextColor":"#0f172a","lineColor":"#475569","fontFamily":"Inter, ui-sans-serif, system-ui, sans-serif","fontSize":"16px"},"flowchart":{"curve":"basis","nodeSpacing":38,"rankSpacing":42,"padding":12}}}%%
flowchart LR
    A([Normal task]) --> L[Luna xhigh · root]
    L --> W[Luna xhigh · workers]
    W --> R{Result clean?}
    R -->|yes| C([Integrate])
    R -->|ambiguous / high-risk| S[Escalation checkpoint]
    S --> SOL[Sol High]
    SOL --> C

    classDef normal fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a8a,font-weight:700;
    classDef decision fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f,font-weight:700;
    classDef escalation fill:#fee2e2,stroke:#dc2626,stroke-width:2px,color:#7f1d1d,font-weight:700;
    classDef done fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d,font-weight:700;

    class A,L,W normal;
    class R decision;
    class S,SOL escalation;
    class C done;
```

Default philosophy:

- persistent root: cost-efficient strong reasoning model;
- normal workers: same cost-efficient strong model;
- expensive model: **bounded escalation**, not persistent orchestration overhead;
- user-selected model policy always overrides the default.

For the current IDX workflow, the intended mapping is **Luna xhigh** for root/workers, with **Sol High** reserved for difficult architecture conflicts, repeated failures, suspicious research results, or final high-risk gates.

## Control plane

```mermaid
%%{init: {"theme":"base","themeVariables":{"background":"#ffffff","primaryTextColor":"#0f172a","lineColor":"#475569","fontFamily":"Inter, ui-sans-serif, system-ui, sans-serif","fontSize":"16px"},"flowchart":{"curve":"basis","nodeSpacing":34,"rankSpacing":42,"padding":12}}}%%
flowchart LR
    subgraph CONFIG[Project control files]
        direction TB
        P[PROJECT_PROFILE.md]
        S[TEAM_STATUS.md]
        T[TASK_REGISTRY.md]
        D[DECISIONS.md]
    end

    M[MAIN integrator]
    W[Workers]
    H[handoffs/]

    P --> M
    S --> M
    T --> M
    D --> M
    M --> W
    W --> H
    H --> M
    M --> S
    M --> T
    M --> D

    classDef config fill:#f8fafc,stroke:#64748b,stroke-width:1.8px,color:#0f172a;
    classDef main fill:#ede9fe,stroke:#7c3aed,stroke-width:2.5px,color:#4c1d95,font-weight:800;
    classDef worker fill:#dbeafe,stroke:#2563eb,stroke-width:2px,color:#1e3a8a,font-weight:700;
    classDef handoff fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d,font-weight:700;

    class P,S,T,D config;
    class M main;
    class W worker;
    class H handoff;
    style CONFIG fill:#ffffff,stroke:#cbd5e1,stroke-width:1.5px
```

`MAIN` is the single integrator. Workers execute bounded assignments and return evidence through handoffs; they do not independently redefine project scope or orchestration policy.

## Recommended use

1. Copy `AGENTS.md`, `coordination/`, and optionally `docs/ORCHESTRATION.md` into the target project.
2. Fill `coordination/PROJECT_PROFILE.md` with project identity, repositories, operating mode, roles, gates, and model policy.
3. Initialize `TEAM_STATUS.md`, `TASK_REGISTRY.md`, and `DECISIONS.md`.
4. Keep generic orchestration rules stable; project-specific constraints belong in the project profile or target repository contracts.
5. Start with `DIRECT`, promote to `LIGHT` when independent work helps, and use `HEAVY` only for genuinely parallel/high-risk work.

## Files

- `AGENTS.md` — generic orchestration contract.
- `coordination/PROJECT_PROFILE.md` — per-project configuration.
- `coordination/TEAM_STATUS.md` — current phase/status, MAIN-owned.
- `coordination/TASK_REGISTRY.md` — task ownership/dependencies/status.
- `coordination/DECISIONS.md` — append-only material decisions.
- `coordination/handoffs/` — worker evidence and handoffs.
- `docs/ORCHESTRATION.md` — detailed operating loop and level-selection guide.
