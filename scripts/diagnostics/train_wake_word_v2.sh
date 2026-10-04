#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
host_work_root="${repo_root}/.local/wake-training"
work_root="${AIDEN_WAKE_TRAINING_ROOT:-${host_work_root}}"
oww_root="${work_root}/openWakeWord"
venv_root="${work_root}/venv"
python_bin="${PYTHON_BIN:-python3.10}"
pytorch_version="${PYTORCH_VERSION:-2.7.1}"
training_config_path="${AIDEN_WAKE_TRAINING_CONFIG:-${repo_root}/scripts/diagnostics/wake_word_v2.yml}"
model_name="${AIDEN_WAKE_MODEL_NAME:-aiden_v2}"
training_config_name="$(basename "${training_config_path}")"

export PIP_CACHE_DIR="${AIDEN_WAKE_PIP_CACHE_DIR:-${host_work_root}/pip-cache}"
export HF_HOME="${work_root}/huggingface-cache"
export XDG_CACHE_HOME="${work_root}/cache"
export TMPDIR="${work_root}/tmp"
export UV_CACHE_DIR="${work_root}/uv-cache"
export UV_PYTHON_INSTALL_DIR="${work_root}/uv-python"
export UV_PYTHON_BIN_DIR="${work_root}/bin"
export PIP_PROGRESS_BAR=off
# The official Piper and DeepPhonemizer checkpoints are trusted full-model
# artifacts created before PyTorch 2.6 changed torch.load() to weights-only by
# default. Keep this compatibility override confined to the training process.
export TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1

if ! ldconfig -p 2>/dev/null | grep -q 'libespeak-ng\.so'; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends libespeak-ng1
fi

mkdir -p \
  "${PIP_CACHE_DIR}" \
  "${HF_HOME}" \
  "${XDG_CACHE_HOME}" \
  "${TMPDIR}" \
  "${UV_CACHE_DIR}" \
  "${UV_PYTHON_INSTALL_DIR}" \
  "${UV_PYTHON_BIN_DIR}"

if ! command -v "${python_bin}" >/dev/null 2>&1; then
  uv_bin="${work_root}/bin/uv"
  if [[ ! -x "${uv_bin}" ]]; then
    uv_installer="${TMPDIR}/uv-install.sh"
    curl -LsSf https://astral.sh/uv/install.sh -o "${uv_installer}"
    env UV_INSTALL_DIR="${work_root}/bin" UV_NO_MODIFY_PATH=1 sh "${uv_installer}"
  fi
  "${uv_bin}" python install 3.10
  python_bin="$("${uv_bin}" python find 3.10)"
fi

if [[ "$("${python_bin}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != "3.10" ]]; then
  echo "The isolated training interpreter must be Python 3.10: ${python_bin}" >&2
  exit 1
fi

if [[ ! -d "${oww_root}/.git" ]]; then
  git clone --depth 1 https://github.com/dscripka/openWakeWord.git "${oww_root}"
fi
if [[ ! -d "${work_root}/piper-sample-generator/.git" ]]; then
  git clone --depth 1 https://github.com/dscripka/piper-sample-generator "${work_root}/piper-sample-generator"
fi

"${python_bin}" -m venv "${venv_root}"
source "${venv_root}/bin/activate"
# torchmetrics 0.11 (required by openWakeWord 0.6) still imports
# pkg_resources, which setuptools 81 removed.
python -m pip install --upgrade pip wheel "setuptools<81"

# openWakeWord's training extra still declares torchaudio<1 even though its
# training code works with the current 2.x API. Install a matched CUDA 12.8
# pair first, then relax only that stale constraint in the ignored local clone.
python -m pip install \
  "torch==${pytorch_version}" \
  "torchaudio==${pytorch_version}" \
  --index-url https://download.pytorch.org/whl/cu128
python - "${oww_root}/setup.py" <<'PY'
from pathlib import Path
import sys

setup_path = Path(sys.argv[1])
contents = setup_path.read_text(encoding="utf-8")
old = "'torchaudio>=0.13.1,<1'"
new = "'torchaudio>=2.7,<3'"
if old in contents:
    setup_path.write_text(contents.replace(old, new), encoding="utf-8")
elif new not in contents:
    raise SystemExit(f"Unexpected torchaudio constraint in {setup_path}")
PY

# TensorFlow 2.8, required by the official training pipeline, predates NumPy 2.
python -m pip install "numpy==1.23.5" -e "${oww_root}[full]"
# The training extra installs CPU-only ONNX Runtime, which makes feature
# extraction take well over an hour. Replace it with the matching CUDA build
# when needed so the RTX GPU is used for openWakeWord embeddings as well.
if ! python - <<'PY'
import onnxruntime as ort
raise SystemExit(0 if "CUDAExecutionProvider" in ort.get_available_providers() else 1)
PY
then
  python -m pip uninstall -y onnxruntime onnxruntime-gpu
  python -m pip install --no-deps "onnxruntime-gpu==1.23.2"
fi
python - <<'PY'
import onnxruntime as ort

providers = ort.get_available_providers()
if "CUDAExecutionProvider" not in providers:
    raise SystemExit(f"CUDA ONNX Runtime provider unavailable: {providers}")
print(f"ONNX Runtime providers: {providers}")
PY
# Piper's generator is a source-only helper and its requirements are not
# installed by openWakeWord's training extra.
python -m pip install espeak-phonemizer webrtcvad
# PyTorch 2.6+ defaults to weights-only checkpoints. This official Piper
# checkpoint is a trusted full-model artifact and needs the legacy load mode.
python - "${work_root}/piper-sample-generator/generate_samples.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "model = torch.load(model_path)"
new = "model = torch.load(model_path, weights_only=False)"
if old in text:
    path.write_text(text.replace(old, new), encoding="utf-8")
elif new not in text:
    raise SystemExit(f"Unexpected checkpoint load in {path}")
PY
# The upstream trainer sends the entire 11.3-hour false-positive validation
# set to the GPU in one batch at the first validation checkpoint (75% of the
# first sequence).  That peaks beyond the available RTX 5070/WSL memory and
# terminates the distro.  Chunking preserves every validation example and the
# resulting false-positive-rate calculation while keeping GPU memory bounded.
python - "${oww_root}/openwakeword/train.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "batch_size=len(X_val_fp_labels)"
new = "batch_size=min(2048, len(X_val_fp_labels))"
if old in text:
    path.write_text(text.replace(old, new), encoding="utf-8")
elif new not in text:
    raise SystemExit(f"Unexpected false-positive validation batching in {path}")
PY
python -c "import pkg_resources" 2>/dev/null
python -m pip cache purge
python - <<'PY'
import torch

if not torch.cuda.is_available():
    raise SystemExit("CUDA is unavailable in the isolated training environment")
print(f"Training GPU: {torch.cuda.get_device_name(0)}")
PY

# Feature extraction needs the package's official mel-spectrogram and VAD
# resources; editable installs do not include these binary assets.
python -c "import openwakeword; openwakeword.utils.download_models(['hey_aiden'])"

if [[ ! -f "${training_config_path}" ]]; then
  echo "Missing training configuration: ${training_config_path}" >&2
  exit 2
fi
cp "${training_config_path}" "${work_root}/${training_config_name}"
cd "${work_root}"

if [[ ! -f piper-sample-generator/models/en-us-libritts-high.pt ]]; then
  mkdir -p piper-sample-generator/models
  curl -fL -C - --retry 5 --retry-all-errors \
    -o piper-sample-generator/models/en-us-libritts-high.pt \
    https://github.com/rhasspy/piper-sample-generator/releases/download/v1.0.0/en-us-libritts-high.pt
fi

for asset in openwakeword_features_ACAV100M_2000_hrs_16bit.npy validation_set_features.npy; do
  if [[ ! -f "${asset}" ]]; then
    curl -fL -C - --retry 5 --retry-all-errors -o "${asset}" \
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

feature_root="${model_name}_output/${model_name}"
if [[ -f "${feature_root}/positive_features_train.npy" && \
      -f "${feature_root}/negative_features_train.npy" && \
      -f "${feature_root}/positive_features_test.npy" && \
      -f "${feature_root}/negative_features_test.npy" ]]; then
  echo "Reusing completed feature arrays in ${feature_root}; skipping clip generation and augmentation."
else
  # Upstream skips the entire augmentation phase when only the first feature
  # array exists. Remove incomplete arrays from an interrupted run so all four
  # are rebuilt together instead of failing later with missing files.
  rm -f \
    "${feature_root}/positive_features_train.npy" \
    "${feature_root}/negative_features_train.npy" \
    "${feature_root}/positive_features_test.npy" \
    "${feature_root}/negative_features_test.npy"
  python "${oww_root}/openwakeword/train.py" --training_config "${training_config_name}" --generate_clips
  python "${oww_root}/openwakeword/train.py" --training_config "${training_config_name}" --augment_clips
fi
python "${oww_root}/openwakeword/train.py" --training_config "${training_config_name}" --train_model

model_path="$(find "${model_name}_output" -name "${model_name}.onnx" -print -quit)"
if [[ -z "${model_path}" ]]; then
  echo "Training completed without producing ${model_name}.onnx" >&2
  exit 3
fi
cp "${model_path}" "${repo_root}/vosk_models/${model_name}.onnx"
echo "Created ${repo_root}/vosk_models/${model_name}.onnx"
