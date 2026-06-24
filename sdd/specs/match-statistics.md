# Specification: Match Statistics

## الهدف

إدخال أكبر قدر متاح من إحصاءات المباراة في النموذج ولوحة التفاصيل.

## المصدر الحالي

ESPN summary endpoint:

```text
https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event=<event_id>
```

## الحقول المدعومة

- `shots`
- `shots_on_target`
- `possession`
- `corners`
- `yellow_cards`
- `red_cards`
- `fouls`
- `offsides`
- `saves`
- `accurate_passes`
- `total_passes`
- `pass_pct`
- `accurate_crosses`
- `total_crosses`
- `blocked_shots`
- `total_tackles`
- `interceptions`
- `clearances`
- `dominance_index`، مؤشر بديل محسوب من الاستحواذ والتمريرات والتسديدات.
- `attacking_pressure_index`، مؤشر بديل محسوب من التسديدات على المرمى والتسديدات والركنيات والاستحواذ.

## حقول جاهزة لمصدر آخر

- `xg`
- `big_chances`
- `passes_into_final_third`
- `match_momentum`
- `momentum_last_15`

إذا وجدنا مصدراً مفتوحاً يعطي هذه الحقول، يضاف adapter جديد بدون تغيير بنية النموذج.

## Match Momentum

Match Momentum الحقيقي هو منحنى زمني وليس رقماً واحداً. ESPN لا يوفره في endpoint الحالي. لذلك لدينا مستويان:

1. `dominance_index` و`attacking_pressure_index`: بدائل post-match تحسب من إحصاءات ESPN.
2. `match_momentum` و`momentum_last_15`: حقول جاهزة لمصدر يمنح منحنى زمني مثل SofaScore أو مصدر مشابه إذا أصبح الوصول إليه مستقراً.

لا يجوز تسمية `dominance_index` بأنه Match Momentum حقيقي. هو proxy فقط.

## التخزين

كل الإحصاءات تخزن في:

```text
data/match_advanced_stats.csv
```

## الاستخدام في النموذج

`TeamIntelligenceAgent` يقرأ الإحصاءات ويحوّلها إلى factor score.

## الاستخدام في الداشبورد

عند الضغط على بطاقة المباراة، تعرض نافذة التفاصيل:

- مقارنة الاستحواذ.
- التسديدات.
- التسديدات على المرمى.
- xG إن وجد.
- الركنيات.
- العوامل.
- دقة التوقع بعد ظهور النتيجة.
