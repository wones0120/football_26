# Showdown Captain Role and Scenario Analysis

- Slates: `41`
- Captain archetypes: `11`
- Scenario cells: `7`

## Captain Role Archetypes

| Archetype | Slates | Share |
|---|---:|---:|
| QB:premium | 9 | 22.0% |
| WR:premium | 8 | 19.5% |
| RB:premium | 6 | 14.6% |
| WR:core | 6 | 14.6% |
| WR:value | 3 | 7.3% |
| RB:value | 3 | 7.3% |
| TE:premium | 2 | 4.9% |
| TE:value | 1 | 2.4% |
| DST:premium | 1 | 2.4% |
| TE:core | 1 | 2.4% |
| QB:core | 1 | 2.4% |

## Scenario Priors

| Scenario | Slates | Prior Source | Leading Archetype | Probability |
|---|---:|---|---|---:|
| high_total__close | 2 | global_fallback | QB:premium | 19.2% |
| high_total__moderate | 8 | scenario | WR:core | 21.1% |
| high_total__wide | 3 | global_fallback | QB:premium | 19.2% |
| low_total__close | 1 | global_fallback | QB:premium | 19.2% |
| mid_total__close | 9 | scenario | QB:premium | 25.0% |
| mid_total__moderate | 14 | scenario | QB:premium | 20.0% |
| mid_total__wide | 4 | global_fallback | QB:premium | 19.2% |

Role is based on captain salary relative to the highest flex salary at that position: premium >=90%, core 70-90%, and value <70%. Scenario priors use Laplace smoothing and pregame total/spread context, so they can be applied to future slates.
