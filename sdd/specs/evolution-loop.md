# Specification: Evolution Loop

## الهدف

بعد كل مباراة، يجب أن يعرف النظام:

- ماذا توقع قبل المباراة؟
- ماذا حدث فعلاً؟
- ما مدى دقة التوقع؟
- هل يجب تعديل أوزان النموذج؟
- كيف أثّر ذلك على بقية البطولة؟

## Trigger

يعمل `match_monitor.py` بشكل مستمر.

الشرط:

```text
now_utc >= kickoff_utc + 110 minutes
```

أي 90 دقيقة لعب + 20 دقيقة انتظار للنتيجة والإحصاءات.

## خطوات التنفيذ

1. تحديد المباريات المستحقة للفحص.
2. تشغيل `fetch_espn_match_stats.py --match-id <id>`.
3. تشغيل `update_worldcup_results.py`.
4. تحديث `actual_results.csv`.
5. تحديث `match_advanced_stats.csv`.
6. تشغيل `evolve_after_results.py`.
7. حفظ snapshot في `outputs/model_versions/`.
8. تحديث `accuracy_report.json`.
9. إعادة توليد توقعات المباريات المتبقية.
10. إعادة توليد `tournament_projection.json`.

## Acceptance Criteria

- إذا انتهت مباراة وظهر مصدر النتيجة، يجب أن تظهر في `actual_results.csv`.
- إذا توفرت إحصاءات ESPN، يجب أن تظهر في `match_advanced_stats.csv`.
- يجب أن يظهر تقييم المباراة في `accuracy_report.json`.
- يجب أن ينقص عدد ملفات التوقع المتبقية في `forecast_manifest.json`.
- يجب إنشاء نسخة جديدة داخل `outputs/model_versions/`.

## Failure Behavior

- إذا فشل ESPN، لا يتوقف النظام.
- إذا فشل openfootball، يستخدم آخر نسخة محلية ناجحة إن وجدت.
- إذا لم تتوفر الإحصاءات، يظهر تحذير في الداشبورد.
