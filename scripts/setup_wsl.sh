#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
#  WSL2 Setup Script for qlib_rd_agent
#  Target: Windows PC with NVIDIA GTX 3060, running WSL2 (Ubuntu)
#
#  This script installs all prerequisites:
#    - System packages
#    - Miniforge (conda-forge)
#    - CUDA Toolkit 12.1 (toolkit only; WSL2 uses Windows GPU driver)
#    - uv (Python package manager)
#    - rdagent4qlib conda environment (Python 3.10, RD-Agent, Qlib, PyTorch)
#    - qlib_rd_agent project setup
#
#  LLM providers (Volcengine + AIHUBMIX) are cloud-based APIs — no local
#  model server needed.  Just configure API keys in .env.
#
#  Usage:
#    chmod +x setup_wsl.sh
#    ./setup_wsl.sh
#
#  IMPORTANT:
#    - Run this INSIDE WSL2 Ubuntu, not in Windows
#    - Ensure Windows NVIDIA driver is already installed on the host
#    - Do NOT install NVIDIA driver inside WSL2
# =============================================================================

PROJECT_DIR="$HOME/qlib_rd_agent"

# ---------------------------------------------------------------------------
echo "=== [1/7] Updating system packages ==="
# ---------------------------------------------------------------------------
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y build-essential git curl wget unzip software-properties-common

# ---------------------------------------------------------------------------
echo "=== [2/7] Installing Miniforge ==="
# ---------------------------------------------------------------------------
# Using Miniforge (conda-forge default channel), NOT Anaconda or Miniconda.
if ! command -v conda &> /dev/null; then
    wget -q "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh" -O /tmp/miniforge.sh
    bash /tmp/miniforge.sh -b -p "$HOME/miniforge3"
    rm /tmp/miniforge.sh

    # Initialize conda for bash but DON'T auto-activate base
    "$HOME/miniforge3/bin/conda" init bash
    "$HOME/miniforge3/bin/conda" config --set auto_activate_base false

    echo "Miniforge installed. Please restart shell or run: source ~/.bashrc"
else
    echo "conda already installed at: $(which conda)"
fi

# Ensure conda is available in this session
if [ -f "$HOME/miniforge3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniforge3/etc/profile.d/conda.sh"
fi

echo "Verification: conda $(conda --version 2>&1 || echo 'not yet on PATH — restart shell')"

# ---------------------------------------------------------------------------
echo "=== [3/7] Installing CUDA Toolkit ==="
# ---------------------------------------------------------------------------
# WSL2 uses the Windows GPU driver — only the CUDA toolkit is needed inside WSL.
# Installing CUDA 12.1, compatible with PyTorch 2.x.
if ! command -v nvcc &> /dev/null; then
    wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-wsl-ubuntu.pin
    sudo mv cuda-wsl-ubuntu.pin /etc/apt/preferences.d/cuda-repository-pin-600

    wget https://developer.download.nvidia.com/compute/cuda/12.1.1/local_installers/cuda-repo-wsl-ubuntu-12-1-local_12.1.1-1_amd64.deb
    sudo dpkg -i cuda-repo-wsl-ubuntu-12-1-local_12.1.1-1_amd64.deb
    sudo cp /var/cuda-repo-wsl-ubuntu-12-1-local/cuda-*-keyring.gpg /usr/share/keyrings/
    sudo apt-get update
    sudo apt-get -y install cuda-toolkit-12-1

    rm -f cuda-repo-wsl-ubuntu-12-1-local_12.1.1-1_amd64.deb

    # Add CUDA to PATH (persisted in .bashrc)
    if ! grep -q 'cuda-12.1/bin' ~/.bashrc; then
        echo 'export PATH=/usr/local/cuda-12.1/bin:$PATH' >> ~/.bashrc
        echo 'export LD_LIBRARY_PATH=/usr/local/cuda-12.1/lib64:${LD_LIBRARY_PATH:-}' >> ~/.bashrc
    fi
    export PATH=/usr/local/cuda-12.1/bin:$PATH
    export LD_LIBRARY_PATH=/usr/local/cuda-12.1/lib64:${LD_LIBRARY_PATH:-}
else
    echo "CUDA already installed: $(nvcc --version | head -1)"
fi

echo "Verification: nvidia-smi"
nvidia-smi || echo "WARNING: nvidia-smi failed. Ensure Windows NVIDIA driver is installed."

# ---------------------------------------------------------------------------
echo "=== [4/7] Installing uv ==="
# ---------------------------------------------------------------------------
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Ensure uv is on PATH (persisted in .bashrc)
    if ! grep -q '.local/bin' ~/.bashrc; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    fi
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "uv already installed: $(uv --version)"
fi

echo "Verification: uv $(uv --version 2>&1)"

# ---------------------------------------------------------------------------
echo "=== [5/7] Creating rdagent4qlib conda environment ==="
# ---------------------------------------------------------------------------
source "$HOME/miniforge3/etc/profile.d/conda.sh"

if ! conda env list | grep -q "rdagent4qlib"; then
    conda create -n rdagent4qlib python=3.10 -y

    conda activate rdagent4qlib

    # Install RD-Agent
    pip install rdagent

    # Install Qlib from the specific commit pinned by RD-Agent
    pip install "git+https://github.com/microsoft/qlib.git@3e72593b8c985f01979bebcf646658002ac43b00"

    # Install PyTorch with CUDA 12.1 support (GTX 3060 = Ampere, sm_86)
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

    conda deactivate
else
    echo "rdagent4qlib environment already exists"
fi

echo "Verification: conda env list"
conda env list

# ---------------------------------------------------------------------------
# Reload PATH so uv/conda/cuda are available in this session
# ---------------------------------------------------------------------------
source "$HOME/.bashrc" 2>/dev/null || true
export PATH="$HOME/.local/bin:$HOME/miniforge3/bin:/usr/local/cuda-12.1/bin:$PATH"

# ---------------------------------------------------------------------------
echo "=== [6/7] Setting up qlib_rd_agent project ==="
# ---------------------------------------------------------------------------
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Please clone or copy qlib_rd_agent to $PROJECT_DIR first."
    echo "Example: git clone <repo_url> $PROJECT_DIR"
else
    cd "$PROJECT_DIR"

    if [ ! -d ".venv" ]; then
        uv venv --python 3.10
        source .venv/bin/activate
        uv pip install -e ".[dev]"
        deactivate
    else
        echo ".venv already exists in $PROJECT_DIR"
    fi
fi

# ---------------------------------------------------------------------------
echo "=== [7/7] Environment configuration ==="
# ---------------------------------------------------------------------------
if [ -f "$PROJECT_DIR/.env.example" ] && [ ! -f "$PROJECT_DIR/.env" ]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    echo "Created .env from template. Please edit $PROJECT_DIR/.env with your API keys."
elif [ -f "$PROJECT_DIR/.env" ]; then
    echo ".env already exists at $PROJECT_DIR/.env"
else
    echo ".env.example not found — create $PROJECT_DIR/.env manually when ready."
fi

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Restart your shell:  source ~/.bashrc"
echo "  2. Edit $PROJECT_DIR/.env with your API keys:"
echo "       VOLCENGINE_API_KEY=<your-volcengine-key>"
echo "       AIHUBMIX_API_KEY=<your-aihubmix-key>"
echo "  3. Ensure Windows NVIDIA driver is installed (not inside WSL)"
echo "  4. Verify GPU:  nvidia-smi"
echo "  5. Run:"
echo "       cd $PROJECT_DIR && source .venv/bin/activate && python -m src.main full"
echo ""
