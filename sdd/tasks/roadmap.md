# Roadmap

## Done

- Agent Harness core.
- World Cup data import.
- Remaining group forecasts.
- FIFA-style Round of 32 bracket slots.
- ESPN stats adapter.
- Match monitor agent.
- Evolution snapshots.
- Accuracy report.
- Arabic dashboard.
- Match detail modal.

## In Progress

- Fully autonomous monitoring reliability.
- More robust network retry/cache behavior.
- Better advanced-stat visualizations.

## Next

1. Add official third-place allocation table from FIFA Annex C.
2. Add second statistics adapter if an open xG source is found.
3. Add model evolution story report.
4. Add confidence calibration chart over time.
5. Add per-agent contribution chart.
6. Add source health dashboard.
7. Add automated smoke test for dashboard JSON integrity.

## Acceptance Gates

قبل اعتبار النسخة قوية:

- يجب أن تعمل المراقبة الخلفية.
- يجب أن تُحدّث نتيجة مباراة مكتملة دون تدخل يدوي.
- يجب أن تحفظ snapshot.
- يجب أن تظهر إحصاءات المباراة في نافذة التفاصيل إن توفرت.
- يجب ألا يختفي سجل النسخ السابقة.
