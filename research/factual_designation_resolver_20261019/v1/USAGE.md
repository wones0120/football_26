# Saved Monday #1 and #2: fantasy points and usage evidence

Run **2c10b6cc-527d-41f2-af4f-23db94f8446a**; projection **5110cc61-e134-4c88-9cd3-ba97a9688c9d**; frozen cutoff **2026-10-19T15:31:03.970927UTC**. Both saved rosters exclude Jordan Watkins. These are the exact model FP means, not a manual football adjustment.

**No supported forward pass-attempt, rushing-attempt or target forecasts are present for these players.** Their explicit `pregame_expected_targets/carries` are null, and the saved feature rows contain no passing-attempt forecast. Historical observations and allocated proxies below must not be called projections. A Captain multiplier increases FP/salary, not physical attempts/targets.

|Player|Native FLEX / CPT ID|FLEX salary|Base projected FP|FP used at CPT in #1/#2|Original observed targets/game|Original observed carries/game|Observed window|
|---|---|---:|---:|---:|---:|---:|---|
|Jayden Daniels|44533077 / 44533137|$10,000|18.230808|27.346212|0.000|7.000|2026 W1,W2,W5|
|Brock Purdy|44533076 / 44533136|$10,800|19.180749|—|0.000|5.667|2026 W3–5|
|Christian McCaffrey|44533075 / 44533135|$11,800|12.277180|—|4.333|13.667|2026 W3–5|
|Drew Stevens|44533091 / 44533151|$5,000|8.320000|—|N/A|N/A|2026 W3–5 kicker usage|
|Treylon Burks|44533099 / 44533159|$3,200|4.808526|—|3.333|0.000|2026 W3–5|
|Antonio Williams|44533094 / 44533154|$4,200|5.936262|—|5.000|0.000|2026 W3–5|
|Chig Okonkwo|44533092 / 44533152|$4,600|6.630303|—|4.333|0.000|2026 W1,W4,W5|
|Austin Ekeler|44533097 / 44533157|$3,600|5.394214|—|2.333|5.000|2025 W2 + 2026 W4,W5|

The windows are **last three observed records**, not necessarily consecutive games or the current season. Missing rows are not measured zero. Ekeler's cross-season window is a material limitation. The passing-attempt historical means, read from the same canonical windows, are **Daniels25.333 / Purdy28.667**; these are not saved model count forecasts. Other positions' passing attempts are not applicable here, rather than useful zero-volume forecasts.

Drew Stevens's original weekly records show **2.0 FG attempts/game** and **2.333 PAT attempts/game** over W3–5. The role-evidence field named `attempts` contains FG+PAT combined (6,3,4), so its4.333 average must not be represented as field-goal attempts or tonight's forecast.

|Allocated proxy only|Targets|Carries|
|---|---:|---:|
|Christian McCaffrey|2.018895|7.588498|
|Treylon Burks|2.158632|N/A|
|Antonio Williams|2.874147|N/A|
|Chig Okonkwo|2.793960|N/A|
|Austin Ekeler|1.171173|3.774934|

Daniels/Purdy/Stevens have no allocated target/carry proxy in the saved snapshot. N/A preserves missing/not-applicable fields; the measured historical zeros above remain zero. Proxy channels are derived from lagged team volume and allocated shares; they are not independently calibrated future player workload forecasts.

**Saved #1:** Daniels CPT27.346212 + Stevens8.320000 + Purdy19.180749 + McCaffrey12.277180 + Burks4.808526 + Antonio Williams5.936262 = **77.868929FP**, **$50,000**.

**Saved #2:** Daniels CPT27.346212 + Purdy19.180749 + Okonkwo6.630303 + Ekeler5.394214 + McCaffrey12.277180 + Antonio Williams5.936262 = **76.764921FP**, **$50,000**.

Proof: monday_optimizer.json immutable saved roster/input snapshot; saved_usage_features.json exact saved feature-run rows; usage_observed_windows.json canonical source IDs/row IDs/timestamps and original component records. Historical mean verification is descriptive; it does not establish a new calibrated forecast.
