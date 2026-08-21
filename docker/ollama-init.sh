#!/bin/sh
set -eu

generator_name="${GENERATOR_MODEL_NAME:-acne-generator}"
intake_name="${INTAKE_MODEL_NAME:-acne-intaker}"

create_model() {
  name="$1"
  model_dir="$2"
  gguf="$3"
  modelfile="$4"

  if ollama show "$name" >/dev/null 2>&1; then
    echo "[ollama-init] $name already exists; skipping."
    return
  fi

  if [ ! -f "$model_dir/$modelfile" ] || [ ! -s "$model_dir/$gguf" ]; then
    echo "[ollama-init] Missing $model_dir/$modelfile or $model_dir/$gguf" >&2
    echo "[ollama-init] Copy the runtime model assets before starting Compose." >&2
    exit 1
  fi

  echo "[ollama-init] Creating $name from $model_dir/$modelfile..."
  (cd "$model_dir" && ollama create "$name" -f "$modelfile")
}

create_model \
  "$generator_name" \
  /models/generator \
  Qwen2.5-7B-Instruct.Q4_K_M.gguf \
  Modelfile.full

create_model \
  "$intake_name" \
  /models/intaker \
  Qwen2.5-3B-Instruct.Q4_K_M.gguf \
  Modelfile

echo "[ollama-init] Required models are ready:"
ollama list
