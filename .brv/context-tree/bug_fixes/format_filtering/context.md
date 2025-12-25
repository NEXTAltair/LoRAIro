
Result format filtering now normalizes format keys (strip/lower) and drops rows where selected format status is missing or not a dict, preventing tags without format status from showing when a result format is selected.
