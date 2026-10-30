# Workboard

## Roles

The brief (§04) names Hemu as team lead and reviewer. Operationally this project is run by one person: **Dolender** does all engineering (YT-02..YT-10), reviews and merges every PR, and is the reviewer at all three pipeline gates (research_review, script_review, qa_review). The approvals table records Dolender as approver, and the final sign-off (`reports/sign-off.md`) is Dolender's.

## Known gaps

- Prototype mode has fixtures only for the Short preset; `make demo-long` and `make second-topic` fail with "no fixture for this topic" until long/second-topic fixtures or production mode exist (D-21). Gate B's two script packages are pending that decision.
- Phase 4P TTS engine (Piper vs Kokoro) not chosen yet (D-21).
