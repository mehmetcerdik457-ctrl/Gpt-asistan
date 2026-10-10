# Local models (not integrated)

Local language-model inference is **NOT DONE**. `LocalModel` is an explicit
placeholder and does not load or run a model. No model runtime or weights are
installed by this project.

For a Galaxy S26 Ultra-class phone, a realistic experiment would be
`llama.cpp` with a small GGUF model quantized to 4-bit. A 1–3 billion parameter
model often needs roughly 1–2 GB for quantized weights; a 7–8 billion model
can use roughly 4–6 GB for weights, plus additional RAM for the runtime and
context. Storage requirements are similar to the model-file size, with extra
space needed for downloads and temporary files. Actual memory use and
performance depend on the model, quantization, context length, and phone
runtime; mobile thermal limits also matter.

Before downloading or distributing any model, check its specific license and
terms for commercial use, redistribution, and derivative works. These are
evaluation notes only, not a claim that a model or runtime is available in the
repository or installed on a device.
