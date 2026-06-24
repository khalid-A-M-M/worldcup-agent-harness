# Agent Contracts

## Orchestrator / AgentHarness

المسؤولية:

- تشغيل الوكلاء بترتيب ثابت.
- تمرير `PipelineState`.
- منع الخلط بين الوكلاء.

المدخل:

- `MatchContext`

المخرج:

- `PipelineState`

## DataCollectionAgent

المسؤولية:

- تحميل نتائج البطولة.
- تحميل أحداث أثر الفراشة.
- تحميل priors.
- تحميل الإحصاءات المتقدمة.
- تحميل calibration.

لا يقرر التوقع.

## SpecialistAnalysisAgent

المسؤولية:

- توليد baseline احتمالي عبر Dixon-Coles Lite / Poisson.

المخرج:

- `home_win`
- `draw`
- `away_win`
- expected goals
- top scorelines

## TeamIntelligenceAgent

المسؤولية:

- قراءة أداء البطولة.
- قراءة seed priors.
- قراءة إحصاءات المباراة المتقدمة.
- تحويلها إلى عوامل قابلة للشرح.

## ButterflyFactorsAgent

المسؤولية:

- رصد الأحداث الصغيرة عالية الأثر.
- تطبيق وزن زمني.
- لا يصدر التوقع النهائي.

## CriticAuditorAgent

المسؤولية:

- Devil's Advocate.
- كشف التوقعات الضيقة.
- كشف تعارض baseline مع form/advanced stats.
- توسيع الثقة عند نقص البيانات.

## SynthesizerAgent

المسؤولية:

- دمج كل الإشارات.
- إصدار التوقع النهائي.
- إرفاق العوامل والتحذيرات.

## SelfCorrectionAgent

المسؤولية:

- مقارنة التوقع بالنتيجة الفعلية.
- حساب Brier وLog Loss.
- تسجيل نتيجة التقييم.

## MatchMonitorAgent

الملف:

- `match_monitor.py`

المسؤولية:

- مراقبة وقت نهاية المباراة.
- تشغيل تحديث النتيجة والإحصاءات.
- إطلاق دورة التطور.
