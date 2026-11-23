# North Quay dispatch handover v0.2.0

This native Calc task keeps the original desktop-only task ID and boot path. The separate `0.1.1` version remains the engineering control. The workbook starts on Shift and already contains the stock log, clinic order queue, staging records, adjustment controls and three operation areas. The amber cells identify the calculations that need completion.

The dock result counts released lots by SKU and depot at or before the current cutoff and protects the safety reserve. Clinic dispatch combines eligible confirmed orders across priority tiers, caps shipping at free stock and reports the shortfall. Transfer control reconciles the selected wave, destination and clearance, then applies whole-carton and reserve limits. The Shift panel combines completed decisions for the supervisor.

## Acceptance

The three calculation areas each carry 27 points. A working handover carries 16 and preserving the starting data during processing carries 3. The packaged verifier reads the formulas, computes their results in the starting situation and three changed situations, and compares those results with a separate direct implementation of the business rules. The three probes vary the cutoff, clinic threshold and stock, lane wave, carton size, demand and source rows. SUMIFS and ordinary arithmetic are supported, including common equivalent comparisons, IF and rounding formulas. Scoring checks the referenced values and formulas and accepts equivalent formulas within this set.

The declared simple allowance is `0.03`. One complete transfer block with a prematurely entered handover gets `0.30`. Summarizing blank results or entering the initial correct numbers as values or constant formulas gets `0`. Counterexamples isolate cutoff, matching, carton arithmetic, handover completeness, and preservation of a non-target source item.

The Oracle uses native Calc through computer MCP and the preopened editable file. Its workbook navigation and input syntax are based on published Calc controls. Calibrate it on the actual task desktop and repeat platform validation before release. [LibreOffice SUMIFS help](https://help.libreoffice.org/latest/en-US/text/scalc/01/func_sumifs.html) · [LibreOffice Calc keyboard shortcuts](https://help.libreoffice.org/latest/en-US/text/scalc/04/01020000.html)
