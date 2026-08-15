def suite_data(repeats=2):
    def series(output, latency=10):
        return [
            {"output": output, "latency_ms": latency + index, "input_tokens": 10, "output_tokens": 2}
            for index in range(repeats)
        ]

    return {
        "schema_version": "1.0",
        "suite_id": "test-suite",
        "version": "1.2.3",
        "limits": {"repeats": repeats, "max_output_chars": 1_000},
        "scenarios": [
            {
                "id": "exact",
                "difficulty": "easy",
                "input": "Say Paris",
                "expected": "Paris",
                "judge": {"type": "exact", "case_sensitive": False},
            },
            {
                "id": "json",
                "difficulty": "medium",
                "input": "Return JSON",
                "expected": {"ok": True},
                "judge": {"type": "json_equal"},
            },
        ],
        "candidates": [
            {
                "id": "good",
                "model": "replay-good",
                "prompt_template": "Answer: {input}",
                "input_price_microunits_per_1k": 100,
                "output_price_microunits_per_1k": 200,
            },
            {
                "id": "bad",
                "model": "replay-bad",
                "prompt_template": "Respond: {input}",
                "input_price_microunits_per_1k": 50,
                "output_price_microunits_per_1k": 100,
            },
        ],
        "replay": {
            "good": {"exact": series("Paris", 10), "json": series('{"ok": true}', 12)},
            "bad": {"exact": series("Lyon", 8), "json": series('{"ok": false}', 9)},
        },
    }
