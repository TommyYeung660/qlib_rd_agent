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
#    - Docker Engine + NVIDIA Container Toolkit (for RD-Agent code sandboxing)
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
echo "=== [1/8] Updating system packages ==="
# ---------------------------------------------------------------------------
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y build-essential git curl wget unzip software-properties-common

# ---------------------------------------------------------------------------
echo "=== [2/8] Installing Miniforge ==="
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
echo "=== [3/8] Installing CUDA Toolkit ==="
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
echo "=== [4/8] Installing Docker Engine ==="
# ---------------------------------------------------------------------------
# RD-Agent uses Docker to sandbox AI-generated code execution.
# This installs Docker CE (not Docker Desktop) inside WSL2.
if ! command -v docker &> /dev/null; then
    # Remove any conflicting packages
    for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do
        sudo apt-get remove -y "$pkg" 2>/dev/null || true
    done

    # Add Docker's official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    # Set up the repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Allow current user to use Docker without sudo
    sudo usermod -aG docker "$USER"
    echo "Added $USER to docker group. You may need to restart WSL for group change to take effect."
else
    echo "Docker already installed: $(docker --version)"
fi

# Start Docker daemon if not running (WSL2 may not have systemd)
if ! pgrep -x dockerd > /dev/null; then
    echo "Starting Docker daemon..."
    sudo dockerd &>/dev/null &
    sleep 3
fi

echo "Verification: docker version"
docker version 2>/dev/null || echo "WARNING: Docker daemon not responding. Try: sudo service docker start"

# Install NVIDIA Container Toolkit (for GPU pass-through to Docker)
if ! dpkg -l nvidia-container-toolkit &> /dev/null 2>&1; then
    echo "Installing NVIDIA Container Toolkit..."
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L "https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list" | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    # Restart Docker to pick up nvidia runtime
    sudo pkill dockerd 2>/dev/null || true
    sleep 2
    sudo dockerd &>/dev/null &
    sleep 3
else
    echo "NVIDIA Container Toolkit already installed"
fi

# ---------------------------------------------------------------------------
echo "=== [5/8] Installing uv ==="
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
echo "=== [6/8] Creating rdagent4qlib conda environment ==="
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
echo "=== [7/8] Setting up qlib_rd_agent project ==="
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
echo "=== [8/8] Environment configuration ==="
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
echo "       LITELLM_PROXY_API_KEY=<your-aihubmix-key>"
echo "       OPENAI_API_KEY=<same-as-volcengine-key>"
echo "  3. Ensure Windows NVIDIA driver is installed (not inside WSL)"
echo "  4. Verify GPU:  nvidia-smi"
echo "  5. Verify Docker:  docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi"
echo "  6. Health check:  conda run -n rdagent4qlib rdagent health_check"
echo "  7. Run:"
echo "       cd $PROJECT_DIR && source .venv/bin/activate && python -m src.main full"
echo ""
