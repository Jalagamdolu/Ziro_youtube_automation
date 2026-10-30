# Source snapshots — prototype claim ledger

Raw HTML of every page cited in the prototype fixture
`src/app/adapters/fixtures/what-makes-an-ai-agent-different-from-a-chatbot/claims.json`,
fetched once with `curl -L` (desktop Chrome user agent) on 2026-10-30. They are evidence that each
quote was on the page when it was accessed (brief §07: topical claims keep date + citation).

`tests/unit/test_T03_claim_traceability.py::test_fixture_quotes_appear_in_saved_snapshots`
re-checks this offline on every run: it strips scripts, styles and tags, unescapes entities,
collapses whitespace, and requires each quote verbatim.

| Claim | URL | Snapshot | Fetched (UTC) | SHA-256 |
|---|---|---|---|---|
| C1 | https://www.anthropic.com/engineering/building-effective-agents | `www-anthropic-com-engineering-building-effective-agents.html` | 2026-10-30 06:38:39 | `33d80af9dbb229d61e1f2f6adfd89dff994079fb471fc570cb2ab012e0e19289` |
| C2 | https://www.ibm.com/think/topics/chatbots | `www-ibm-com-think-topics-chatbots.html` | 2026-10-30 06:38:42 | `c594bc71356fe680e7f47e3c95421c12595928f061c16dcf80ad182690c4cf00` |
| C3 | https://www.ibm.com/think/topics/ai-agents | `www-ibm-com-think-topics-ai-agents.html` | 2026-10-30 06:38:41 | `b887ef76aafd2a695881803f482c7a0897232815cea84af072a9a655b7d6f59e` |
| C4 | https://cloud.google.com/discover/what-are-ai-agents | `cloud-google-com-discover-what-are-ai-agents.html` | 2026-10-30 06:38:45 | `3e1b35a5dd14a6736117693d95c67e90c03ec91064092f92590485d1d8cf0cf5` |

Publication dates in the fixture come from the pages themselves: Anthropic `datePublished`
2024-12-19; IBM AI agents `datePublished` 2024-07-03; IBM chatbots shows "Published 15 October
2021" on the page (its metadata says 2024-12-05; the visible date is used); Google Cloud shows none.

The snapshots are third-party pages kept unmodified as citation evidence only; they are not
shipped in any video or output.
