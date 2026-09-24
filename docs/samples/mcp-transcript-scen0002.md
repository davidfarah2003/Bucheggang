# MCP session transcript, SCEN0002

Recorded 2026-09-24 23:44 CEST from one real session. The agent side is the `mcp` 2.2 in-memory client (`mcp.Client(create_server(store))`) calling the policy MCP server. The customer side is the Wallet API (`leash.api.main.create_app`) driven through a FastAPI `TestClient`. Both share one temporary `DraftStore` directory. The confirm route called the live challenge simulator once through `leash.runner.mandates`: `POST /v1/mandates` returned simulator draft `draft_e6f10b94a5428722`, and `POST /v1/mandates/draft_e6f10b94a5428722/confirm` returned the mandate below. The simulator key was read only by `leash.runner.settings` and appears nowhere here.

The proposal is `docs/samples/scen0002_draft.json` as a user-side agent would write it from the authoring guide. The customer answered both open questions on the confirmation screen: "ask" for a missing return period and "yes" for a sporting goods retailer. The confirm route folded those answers into version 2 before creating the mandate.

Draft `c6adb83f-d680-43b2-b3a7-c14a77dfbbd2`, mandate `TM8b150c14b81c91d0`.

### agent: list_tools

```json
[
  "get_policy_authoring_instructions",
  "propose_task_policy",
  "get_policy_status",
  "get_policy_summary",
  "buy",
  "get_purchase_status"
]
```

### agent: get_policy_authoring_instructions (request_instructions only)

```json
"Using the guide, return one JSON proposal with exactly rules, examples, open_questions and uncertainty_policy. Treat only this cardholder instruction as purchase authority: \"Replace my worn road-running shoes in size 43. Buy only from a specialist sports retailer, only if the order can be returned within 14 days or more, and pay no more than CHF 200. Ask me when uncertain.\""
```

### agent: propose_task_policy arguments

```json
{
  "instruction": "Replace my worn road-running shoes in size 43. Buy only from a specialist sports retailer, only if the order can be returned within 14 days or more, and pay no more than CHF 200. Ask me when uncertain.",
  "proposal": {
    "rules": [
      {
        "field": "authorization.billing_amount_chf",
        "operator": "<=",
        "value": 200,
        "currency": "CHF",
        "scope": "purchase",
        "source_text": "pay no more than CHF 200",
        "plain_english": "The total charged amount must be CHF 200 or less."
      },
      {
        "field": "authorization.merchant.merchant_category",
        "operator": "=",
        "value": "sporting_goods",
        "scope": "purchase",
        "source_text": "specialist sports retailer",
        "plain_english": "The seller must be classified as a sporting goods retailer."
      },
      {
        "field": "facts.product_type",
        "operator": "=",
        "value": "road-running shoes",
        "scope": "purchase",
        "source_text": "road-running shoes",
        "plain_english": "The item must be road-running shoes."
      },
      {
        "field": "facts.size",
        "operator": "=",
        "value": "43",
        "scope": "purchase",
        "source_text": "size 43",
        "plain_english": "The shoes must be size 43."
      },
      {
        "field": "facts.return_days",
        "operator": ">=",
        "value": 14,
        "scope": "purchase",
        "source_text": "returned within 14 days or more",
        "plain_english": "The seller must state a return window of at least 14 days."
      },
      {
        "field": "state.approvals_count",
        "operator": "<",
        "value": 1,
        "scope": "purchase",
        "source_text": "Replace my worn road-running shoes",
        "plain_english": "Only one successful purchase can fulfil this request."
      }
    ],
    "examples": [
      {
        "description": "One pair of size 43 road-running shoes, CHF 150, a sporting goods retailer, 30-day returns.",
        "expected": "approve",
        "why": "All stated requirements are met and no pair has been bought yet."
      },
      {
        "description": "The same shoes and seller for CHF 230.",
        "expected": "decline",
        "why": "The total is over the CHF 200 cap."
      },
      {
        "description": "One pair of size 42 road-running shoes for CHF 150.",
        "expected": "decline",
        "why": "The shoe size differs from the request."
      },
      {
        "description": "One matching pair after a previous pair was approved.",
        "expected": "decline",
        "why": "The request has already been fulfilled."
      },
      {
        "description": "One matching pair with no stated return period.",
        "expected": "step_up",
        "why": "The return window cannot be checked from the available facts."
      }
    ],
    "open_questions": [
      {
        "question": "When the seller does not state a return period, should we ask you or decline?",
        "options": [
          "ask",
          "decline"
        ],
        "answer": null,
        "confirming_answers": [
          "ask",
          "decline"
        ]
      },
      {
        "question": "Should a retailer classified as sporting goods count as a specialist sports retailer?",
        "options": [
          "yes",
          "ask me",
          "decline"
        ],
        "answer": null,
        "confirming_answers": [
          "yes"
        ]
      }
    ],
    "uncertainty_policy": "ask"
  }
}
```

### agent: propose_task_policy result (draft_id, version)

```json
{
  "draft_id": "c6adb83f-d680-43b2-b3a7-c14a77dfbbd2",
  "version": 1
}
```

### agent: get_policy_summary

```json
{
  "draft_id": "c6adb83f-d680-43b2-b3a7-c14a77dfbbd2",
  "version": 1,
  "instruction": "Replace my worn road-running shoes in size 43. Buy only from a specialist sports retailer, only if the order can be returned within 14 days or more, and pay no more than CHF 200. Ask me when uncertain.",
  "plain_english": [
    "The total charged amount must be CHF 200 or less.",
    "The seller must be classified as a sporting goods retailer.",
    "The item must be road-running shoes.",
    "The shoes must be size 43.",
    "The seller must state a return window of at least 14 days.",
    "Only one successful purchase can fulfil this request."
  ],
  "examples": [
    {
      "description": "One pair of size 43 road-running shoes, CHF 150, a sporting goods retailer, 30-day returns.",
      "expected": "approve",
      "why": "All stated requirements are met and no pair has been bought yet."
    },
    {
      "description": "The same shoes and seller for CHF 230.",
      "expected": "decline",
      "why": "The total is over the CHF 200 cap."
    },
    {
      "description": "One pair of size 42 road-running shoes for CHF 150.",
      "expected": "decline",
      "why": "The shoe size differs from the request."
    },
    {
      "description": "One matching pair after a previous pair was approved.",
      "expected": "decline",
      "why": "The request has already been fulfilled."
    },
    {
      "description": "One matching pair with no stated return period.",
      "expected": "step_up",
      "why": "The return window cannot be checked from the available facts."
    }
  ],
  "open_questions": [
    {
      "question": "When the seller does not state a return period, should we ask you or decline?",
      "options": [
        "ask",
        "decline"
      ],
      "answer": null
    },
    {
      "question": "Should a retailer classified as sporting goods count as a specialist sports retailer?",
      "options": [
        "yes",
        "ask me",
        "decline"
      ],
      "answer": null
    }
  ],
  "uncertainty_policy": "ask"
}
```

### agent: get_policy_status before the Wallet

```json
{
  "draft_id": "c6adb83f-d680-43b2-b3a7-c14a77dfbbd2",
  "version": 1,
  "status": "pending",
  "mandate_id": null,
  "confirmed_at": null,
  "rejected_reason": null
}
```

The agent hands the customer `/app/?draft=c6adb83f-d680-43b2-b3a7-c14a77dfbbd2`.

### customer: POST /session -> 200

```json
{
  "username": "local-demo"
}
```

### customer: GET /drafts/{id} -> 200 (version, hash)

```json
{
  "version": 1,
  "hash": "54c70cc2061650485bb8833add6e1c73c5f53f13d9ca00ba3c64ee8dc38cde0f"
}
```

### customer: POST /drafts/{id}/confirm body

```json
{
  "version": 1,
  "hash": "54c70cc2061650485bb8833add6e1c73c5f53f13d9ca00ba3c64ee8dc38cde0f",
  "answers": {
    "When the seller does not state a return period, should we ask you or decline?": "ask",
    "Should a retailer classified as sporting goods count as a specialist sports retailer?": "yes"
  }
}
```

### customer: POST /drafts/{id}/confirm -> 200

```json
{
  "mandate_id": "TM8b150c14b81c91d0",
  "draft_id": "c6adb83f-d680-43b2-b3a7-c14a77dfbbd2",
  "version": 2,
  "hash": "54c70cc2061650485bb8833add6e1c73c5f53f13d9ca00ba3c64ee8dc38cde0f",
  "status": "active",
  "confirmed_at": "2026-09-24T21:44:40.514870Z"
}
```

### agent: get_policy_status after the Wallet

```json
{
  "draft_id": "c6adb83f-d680-43b2-b3a7-c14a77dfbbd2",
  "version": 2,
  "status": "confirmed",
  "mandate_id": "TM8b150c14b81c91d0",
  "confirmed_at": "2026-09-24T21:44:40.514870Z",
  "rejected_reason": null
}
```

Mandate for the shopping agent: `TM8b150c14b81c91d0`.

Store directory used: `/tmp/jc-b0fb749932af/home/scratch/leash-policy-zrduapeb`; `c6adb83f-d680-43b2-b3a7-c14a77dfbbd2/confirmation.json` exists: True.
