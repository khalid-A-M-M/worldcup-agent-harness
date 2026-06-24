# SDD Operating System

هذا المجلد هو ذاكرة المشروع الهندسية. هدفه منع التحول إلى vibecoding عشوائي، وتحويل المشروع إلى دورة **Agentic Software Engineering** مبنية على المواصفات.

## المسار المعتمد

```text
Idea
-> Requirements
-> Specification
-> Architecture
-> Agent Contracts
-> Tasks
-> Implementation
-> Testing
-> Review
-> Deployment/Monitoring
-> Evolution Log
```

## القاعدة

لا يتم تعديل جوهر النظام بدون تحديث واحد على الأقل من هذه الملفات:

- `requirements.md`
- `specs/*.md`
- `architecture.md`
- `agents/*.md`
- `decisions/ADR-*.md`
- `tasks/roadmap.md`

## تعريف النجاح

المشروع لا ينجح فقط عندما يعطي توقعاً. ينجح عندما:

- يشرح لماذا توقع.
- يقيس هل كان صحيحاً.
- يحفظ نسخة ما قبل التطور.
- يطور نفسه بعد النتيجة.
- يوضح ما الذي تغير بين نسخة وأخرى.
- يحافظ على traceability من القرار إلى الكود إلى النتيجة.
