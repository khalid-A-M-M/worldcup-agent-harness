# ADR-004: Match Momentum Is Required But Not Fully Sourced Yet

## Status

Accepted gap

## Context

Match Momentum مهم لأنه يصف ضغط المباراة عبر الزمن، وليس فقط مجموع التسديدات والاستحواذ. المستخدم أشار إلى أنه عامل أساسي يجب ألا ينسى.

## Decision

نضيف حقول Match Momentum إلى schema ونضيف proxy مؤقت:

- `dominance_index`
- `attacking_pressure_index`

ونترك الحقول الحقيقية جاهزة:

- `match_momentum`
- `momentum_last_15`

## Consequences

- النموذج أصبح يستفيد من ضغط المباراة بعد نهايتها.
- لا يزال ينقصه منحنى momentum حقيقي.
- يجب البحث أو بناء adapter لمصدر يوفر time-series momentum.
