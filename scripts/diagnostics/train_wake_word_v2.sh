#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
work_root="${repo_root}/.local/wake-training"
oww_root="${work_root}/openWakeWord"
venv_root="${work_root}/venv"
python_bin="${PYTHON_BIN:-python3.10}"

if ! command -v "${python_bin}" >/dev/null 2>&1; then
  echo "Python 3.10 is required in WSL (set PYTHON_BIN to its executable)." >&2
  exit 1
fi

mkdir -p "${work_root}"
if [[ ! -d "${oww_root}/.git" ]]; then
  git clone --depth 1 https://github.com/dscripka/openWakeWord.git "${oww_root}"
fi
if [[ ! -d "${work_root}/piper-sample-generator/.git" ]]; then
  git clone --depth 1 https://github.com/dscripka/piper-sample-generator "${work_root}/piper-sample-generator"
fi

"${python_bin}" -m venv "${venv_root}"
source "${venv_root}/bin/activate"
python -m pip install --upgrade pip wheel setuptools
python -m pip install -e "${oww_root}[full]"
python -m pip install --upgrade torch torchaudio --index-url https://download.pytorch.org/whl/cu128
python - <<'PY'
import torch

if not torch.cuda.is_available():
    raise SystemExit("CUDA is unavailable in the isolated training environment")
print(f"Training GPU: {torch.cuda.get_device_name(0)}")
PY

cp "${repo_root}/scripts/diagnostics/wake_word_v2.yml" "${work_root}/wake_word_v2.yml"
cd "${work_root}"

if [[ ! -f piper-sample-generator/models/en_US-libritts_r-medium.pt ]]; then
  mkdir -p piper-sample-generator/models
  curl -fL -o piper-sample-generator/models/en_US-libritts_r-medium.pt \
    https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt
fi

for asset in openwakeword_features_ACAV100M_2000_hrs_16bit.npy validation_set_features.npy; do
  if [[ ! -f "${asset}" ]]; then
    curl -fL -o "${asset}" \
      "https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main/${asset}"
  fi
done

python "${repo_root}/scripts/diagnostics/prepare_wake_training_assets.py" --root "${work_root}"

for required_dir in mit_rirs audioset_16k fma; do
  if [[ ! -d "${required_dir}" ]] || [[ -z "$(find "${required_dir}" -type f -print -quit)" ]]; then
    echo "Missing training audio directory: ${work_root}/${required_dir}" >&2
    echo "Populate it with 16 kHz WAV assets before running the training phases." >&2
    exit 2
  fi
done

python "${oww_root}/openwakeword/train.py" --training_config wake_word_v2.yml --generate_clips
python "${oww_root}/openwakeword/train.py" --training_config wake_word_v2.yml --augment_clips
python "${oww_root}/openwakeword/train.py" --training_config wake_word_v2.yml --train_model

model_path="$(find aiden_v2_output -name 'aiden_v2.onnx' -print -quit)"
if [[ -z "${model_path}" ]]; then
  echo "Training completed without producing aiden_v2.onnx" >&2
  exit 3
fi
cp "${model_path}" "${repo_root}/vosk_models/aiden_v2.onnx"
echo "Created ${repo_root}/vosk_models/aiden_v2.onnx"
