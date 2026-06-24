# Architecture

## النمط

النظام يعتمد على **Agent Harness** مركزي، لا على وكلاء منفلتين.

```text
Data Sources
  -> Data Collection Agent
  -> Statistical Agent
  -> Team Intelligence Agent
  -> Butterfly Factors Agent
  -> Critic/Auditor Agent
  -> Synthesizer Agent
  -> Self-Correction Agent
  -> Evolution Snapshot
  -> Dashboard
```

## طبقات النظام

### 1. Data Layer

ملفات أساسية:

- `data/worldcup_2026_openfootball.json`
- `data/all_group_fixtures.csv`
- `data/fixtures.csv`
- `data/actual_results.csv`
- `data/match_advanced_stats.csv`
- `data/model_calibration.json`

مصادر حالية:

- openfootball لجدول ونتائج كأس العالم.
- ESPN API لإحصاءات المباراة التفصيلية المتاحة.

### 2. Agent Layer

موجودة في:

- `football_harness/agents.py`
- `football_harness/core.py`
- `football_harness/model.py`

### 3. Evolution Layer

ملفات:

- `match_monitor.py`
- `fetch_espn_match_stats.py`
- `update_worldcup_results.py`
- `evolve_after_results.py`

المخرجات:

- `outputs/accuracy_report.json`
- `outputs/model_versions/`

### 4. Projection Layer

ملف:

- `project_tournament_paths.py`

وظيفته:

- ترتيب المجموعات المتوقع.
- المسارات.
- مواجهات دور الـ32 حسب خانات FIFA الرسمية.

### 5. Dashboard Layer

ملف:

- `index.html`

الصفحة static وتقرأ JSON. لا تشغل Python بنفسها. التشغيل الآلي مسؤولية `match_monitor.py`.

## مبدأ العزل

كل مصدر بيانات يجب أن يدخل عبر adapter مستقل:

- ESPN adapter: `fetch_espn_match_stats.py`
- openfootball adapter: `import_worldcup_data.py`

لا يتم وضع منطق المصدر داخل وكيل التوقع نفسه.
