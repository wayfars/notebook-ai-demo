# Learning tutor live smoke check

One bounded request to an already-running local OpenAI-compatible endpoint used only this fictional lesson: an equation stays balanced when the same operation is applied to each side, illustrated with `x + 2 = 5`.

The question asked why the same amount must be subtracted from both sides. The learning AI client completed in approximately 4.09 seconds, explained preserving balance, and showed subtracting two to obtain `x = 3`. It named the supplied `[L1]` source, which passed marker membership checking. No warning was returned. The request used the fixed output cap, 30-second client timeout, and no retries.

The initially configured endpoint was unreachable; this successful request used a different endpoint that was already running. No model service was started or switched. Endpoint addresses, credentials, personal records, and host configuration are omitted from this public note.

This is a client integration smoke check for one authored question. It does not establish citation entailment, tutoring quality, learning outcomes, concurrent performance, reproducible latency, or production readiness. The browser workflow tests use deterministic mocked AI responses.
