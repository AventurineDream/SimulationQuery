# Hardware-bounded context deployment — September 7

Live hardware verification: the Ollama VM has 31 GiB RAM, 16 virtual Xeon E5-2699 v3 CPU cores, and only a virtual display adapter. Ollama is configured for one loaded model and one parallel request. The 64 GB figure in older notes describes the physical host, not the VM available to SQ.

Chosen policy: keep the explicit 32K model context allocation and 4,096-token actor output allowance; bound only daily director inputs with deterministic excerpts. No summarizer model is added. Complete original sections and retained excerpts are recorded per direction call. This changes director conditioning and must be identified when analyzing this attempt. It is not equivalent to retaining all prior text.

The previously rejected request had a conservative input estimate of 32,891 UTF-8 bytes, not 32,891 measured tokens. A no-generation replay of its context construction under the new excerpt policy gives 22,302 plus a 768-token output reservation, below the 32,768 admission ceiling. This verifies that specific blocker; it does not certify every future request or a completed seven-day season.

Scheduled scenes now use their four-round/12-actor-turn bounds without the inherited 30-minute wall-clock cutoff. Individual request timeouts remain. A delayed-scene regression test crosses 30 minutes while preserving all four rounds. Ordinary simulator time limits are unchanged.

Local verification: 293 tests passed. Installed-model identity and advertised-context preflight passed on the server. Server pytest was not run. Previous failed data roots remain unchanged.

New deployment: `/home/aven/sq-pilot2-context-20260907/checkout`; private data `/home/aven/sq-pilot2-context-20260907/data`; season `SQ-PILOT2-CONTEXT-20260907`. Frozen specification records excerpt policy and disabled scene wall limit. The exact failed-input verification is in `context-verification.json` beside the checkout. Host cron dispatches each minute under a process lock, replacing the old stopped retry's no-op entry; crontab before/after records are retained there. Initial dispatcher PID: 1676288.

Seven-day calendar starts September 7: runs 1 and 2 immediately and sequentially, run 3 at 18:00 Pacific, then 06:00/12:00/18:00 through September 13. The scheduler preserves failed attempts and stops on a fault; it does not repeatedly resample a failed response. Probe branches remain after parent completion. Existing scientific limitations and exploratory one-world scope remain.
