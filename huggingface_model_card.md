---
license: llama3.1
base_model: meta-llama/Llama-3.1-8B-Instruct
language:
  - es
  - en
pipeline_tag: text-generation
tags:
  - llama
  - llama-3.1
  - gguf
  - unreal-engine
  - q4_k_m
  - lora
library_name: llama.cpp
---

# Model Card for SuNavar/Pygenesis-Unreal

Local Unreal Engine 5 assistant. Llama 3.1 8B Instruct, QLoRA-tuned, published as a Q4_K_M GGUF (`pygenesis-unreal-q4km.gguf`). It answers with one BP-Lite JSON graph, one Lighting-Spec JSON, or a short UE5 explanation in Spanish.

The Unreal Editor does not load this file. A local FastAPI bridge and an editor plugin turn that JSON into Blueprint nodes or level lighting.

## Model Details

### Model Description

Pygenesis Unreal is a domain model for Unreal Engine 5. It was adapted from Llama 3.1 8B Instruct with 4-bit QLoRA on ShareGPT conversations about Blueprints, lighting, and UE5 troubleshooting, then merged and quantized to GGUF Q4_K_M for llama.cpp.

Blueprint requests are expected to come back as a single BP-Lite object (`graph_name`, `nodes`, exec wires). Lighting requests come back as a Lighting-Spec (`environment_type`, directional light, fog, post-process). Other UE5 questions come back as a short explanation. Graph JSON uses Unreal node names in English. Prose is in Spanish.

- **Developed by:** SuNavar
- **Funded by:** Independent project. No external funder.
- **Shared by:** [SuNavar](https://huggingface.co/SuNavar)
- **Model type:** Causal language model, Llama 3.1 8B Instruct, QLoRA, GGUF Q4_K_M
- **Language(s):** Spanish for replies. English for Unreal Engine node and pin names. Prompts are written in Spanish.
- **License:** [Llama 3.1 Community License](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE). Accept the license on `meta-llama/Llama-3.1-8B-Instruct` before use. The bridge and plugin source are Apache-2.0.
- **Finetuned from model:** [meta-llama/Llama-3.1-8B-Instruct](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct)

### Model Sources

- **Repository:** [gitlab.com/SunoNavarro/pygen_unreal](https://gitlab.com/SunoNavarro/pygen_unreal)
- **Model weights:** [SuNavar/Pygenesis-Unreal](https://huggingface.co/SuNavar/Pygenesis-Unreal)
- **Paper:** None
- **Demo:** Local only. Window → Pygenesis Unreal inside the Unreal Editor, after the FastAPI bridge is running.

## Uses

Foreseeable users are Unreal Engine developers who want a first draft of a Blueprint graph or a lighting setup on their own machine. People affected are the same users: a wrong graph can be applied in the Editor if they accept it. The model does not connect to Epic services and does not send the prompt off the machine once the GGUF is local.

### Direct Use

Load `pygenesis-unreal-q4km.gguf` in llama.cpp or `llama-cpp-python` with the Llama 3.1 Instruct chat template. Ask, in Spanish, for a Blueprint, a lighting preset, or a short UE5 explanation. Read the JSON before using it. The file by itself does not create assets.

### Downstream Use

The Pygenesis Unreal plugin is the intended downstream app. The bridge calls this GGUF locally, keeps one JSON object, and the plugin builds the Blueprint or applies the lighting in the Editor. That app can drop an unresolved function and can ask the model to continue a graph that closed too early. It does not invent nodes the model never wrote.

### Out-of-Scope Use

- A general-purpose chatbot, a coding agent, or a replacement for Epic's documentation.
- Compiling a project, writing production C++, or shipping a game from the raw JSON.
- Treating every node name as a real Unreal function. Unknown functions must be checked.
- Any use that the Llama 3.1 Community License does not allow.

## Bias, Risks, and Limitations

The model inherits Llama 3.1's training biases and adds a narrow Unreal corpus. It can close a graph before the request is covered, repeat JSON keys, or keep writing after the object. It can name a pin or a function that does not exist in UE5. Q4_K_M is lossy relative to the merged 16-bit weights. The documented training set is small (about 1,309 train conversations and 231 eval conversations) and mixes synthetic ShareGPT turns with excerpts from Epic manuals, so answers can sound official while still being wrong.

Applying a bad graph in the Editor changes the open project. Review the JSON, then apply it.

### Recommendations

Users should keep the GGUF local, read the JSON, and apply it only through a tool that rejects unresolved functions. Do not treat a closed JSON object as proof that every requested node is present. Do not use the model as the only source for Unreal API facts.

## How to Get Started with the Model

The Llama 3.1 Instruct chat template is required.

```bash
llama-cli -m pygenesis-unreal-q4km.gguf -c 4096 --jinja -p "Crea un Blueprint: al pulsar F imprime \"Interactuando\" con PrintString."
```

```python
from llama_cpp import Llama

llm = Llama(model_path="pygenesis-unreal-q4km.gguf", n_ctx=4096, verbose=False)
out = llm.create_chat_completion(
    messages=[
        {"role": "system", "content": "Responde en español. Pedido de Blueprint: un solo JSON BP-Lite y luego para."},
        {"role": "user", "content": "Crea un Blueprint: al pulsar F imprime \"Interactuando\" con PrintString."},
    ]
)
print(out["choices"][0]["message"]["content"])
```

In the Pygenesis project the same file is loaded by the FastAPI bridge. The plugin then builds the graph from the JSON.

## Training Details

### Training Data

ShareGPT conversations for this project. The set documented with the training scripts is about 1,309 training examples and 231 evaluation examples. It covers BP-Lite graphs, Lighting-Spec presets, UE5 troubleshooting, and chunks taken from official Epic manuals. The system prompt used in training is `UNREAL_SYSTEM`. There is no public dataset card for this mix. The GGUF in this repo does not include the dataset.

### Training Procedure

QLoRA, 4-bit, on `meta-llama/Llama-3.1-8B-Instruct`, with the Llama 3.1 Instruct chat template. The target context in the project plan is 4,096 tokens. The adapter was merged into a full Hugging Face model, exported to f16 GGUF, and quantized with `llama-quantize` to Q4_K_M. The published file is that Q4_K_M GGUF, `pygenesis-unreal-q4km.gguf`.

#### Training hyperparameters

Exact step counts, learning rate, epoch count, and batch size for the uploaded weights were not stored next to this GGUF. The procedure above is the one in the project training notes. Do not assume a specific learning rate or number of epochs.

#### Speeds, sizes, times

Not recorded on the model card. Training was set up for a Colab GPU (A100 as the preferred runtime, T4 as a fallback with a shorter context).

## Evaluation

No formal benchmark score is published with this GGUF. Checks used during development are hand-written Unreal prompts: a key that prints a string, movement input, launch character, overlap, a two-point patrol, lighting presets, and short conceptual questions. A usable answer is one JSON object the plugin can apply, or a short explanation when the user did not ask for a graph. Those checks are not a leaderboard result.

## Environmental Impact

Training ran on a rented Colab GPU. Energy use, hours, and emissions were not measured for this release.

## Technical Specifications

### Model Architecture and Objective

Llama 3.1 decoder-only transformer, 8B parameters, instruction-tuned by Meta, then QLoRA-adapted for Unreal Engine 5 text. Objective: next-token prediction on ShareGPT conversations. Inference artifact: GGUF, quantization Q4_K_M.

### Compute Infrastructure

Fine-tuning was documented for Google Colab. Conversion to GGUF used llama.cpp (`convert_hf_to_gguf.py` and `llama-quantize`). Inference is local, through llama.cpp or `llama-cpp-python`.

#### Hardware

Training notes name an A100 as the preferred Colab GPU and a T4 as a fallback. The quantization machine is not specified beyond a Windows host with llama.cpp binaries.

#### Software

Transformers, PEFT, TRL, bitsandbytes, and llama.cpp. The chat template is Llama 3.1 Instruct.

## Citation

No paper. Cite the model repo and the project repo:

```bibtex
@misc{pygenesis_unreal_2026,
  title  = {Pygenesis Unreal},
  author = {SuNavar},
  year   = {2026},
  url    = {https://huggingface.co/SuNavar/Pygenesis-Unreal}
}
```

## Glossary

- **BP-Lite:** Compact JSON for a Blueprint graph. Nodes have an id, a type (`Event`, `InputKey`, `Branch`, `FunctionCall`), a UE5 name, and exec wires. It is not Unreal's native asset format.
- **Lighting-Spec:** Compact JSON for directional light, exponential fog, and post-process.
- **Q4_K_M:** A llama.cpp quantization. Smaller and faster than f16, with some quality loss.

## More Information

Project source, plugin, and bridge: [gitlab.com/SunoNavarro/pygen_unreal](https://gitlab.com/SunoNavarro/pygen_unreal).

## Model Card Contact

[SuNavar on Hugging Face](https://huggingface.co/SuNavar).
