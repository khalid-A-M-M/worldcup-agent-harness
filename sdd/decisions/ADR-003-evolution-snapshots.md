# ADR-003: Preserve Every Model Evolution Snapshot

## Status

Accepted

## Context

المشروع ليس فقط توقعات، بل قصة تطور نموذج خلال البطولة. يجب أن نعرف ماذا كان يعتقد النموذج قبل كل تحديث وكيف تغير.

## Decision

كل دورة `evolve_after_results.py` تحفظ نسخة كاملة داخل:

```text
outputs/model_versions/
```

## Snapshot Contents

- calibration file.
- forecasts.
- tournament projection.
- accuracy report.

## Consequences

- يمكن كتابة تقرير نهائي يحكي تطور النموذج.
- يمكن مقارنة النسخ.
- يمكن معرفة هل التحسينات حسنت الدقة أم أفسدتها.
