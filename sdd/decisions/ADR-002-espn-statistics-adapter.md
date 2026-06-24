# ADR-002: Use ESPN As Current Open Statistics Adapter

## Status

Accepted, replaceable

## Context

المطلوب سحب إحصاءات المباراة تلقائياً بعد نهايتها. FIFA/beIN لا يوفران حالياً endpoint عاماً مثبتاً داخل المشروع. ESPN يوفر scoreboard وsummary يحتويان على إحصاءات مفيدة.

## Decision

نستخدم ESPN كمصدر مفتوح عملي للإحصاءات المتاحة:

- shots
- shots on target
- possession
- corners
- cards
- passes
- tackles
- interceptions
- clearances

## Consequences

- xG غير متوفر حالياً.
- إذا وجد مصدر أفضل، نضيف adapter جديد دون تغيير agents.
- فشل ESPN لا يكسر النظام، بل يسجل تحذيراً.
