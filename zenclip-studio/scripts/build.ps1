# ZenClip - Build Scripts

## Windows Build Script (PowerShell)

```powershell
# build.ps1 - Build script for ZenClip

param(
    [string]$Target = "all",
    [string]$Platform = "win32"
)

$ErrorActionPreference = "Stop"

Write-Host "=== ZenClip Build Script ===" -ForegroundColor Cyan
Write-Host "Target: $Target"
Write-Host "Platform: $Platform"

function Build-Backend {
    Write-Host "`n[1/3] Building Backend..." -ForegroundColor Yellow

    Push-Location backend

    # Install dependencies
    Write-Host "Installing Python dependencies..."
    pip install -r requirements.txt
    pip install pyinstaller

    # Build with PyInstaller
    Write-Host "Building backend executable..."
    pyinstaller zenclip-backend.spec --clean

    Pop-Location
    Write-Host "[1/3] Backend build complete!" -ForegroundColor Green
}

function Build-Frontend {
    Write-Host "`n[2/3] Building Frontend..." -ForegroundColor Yellow

    Push-Location frontend

    # Install dependencies
    Write-Host "Installing Node dependencies..."
    npm install

    # Build
    Write-Host "Building frontend..."
    npm run build

    Pop-Location
    Write-Host "[2/3] Frontend build complete!" -ForegroundColor Green
}

function Build-Electron {
    Write-Host "`n[3/3] Building Electron App..." -ForegroundColor Yellow

    Push-Location electron

    # Install dependencies
    Write-Host "Installing Node dependencies..."
    npm install

    # Compile TypeScript
    Write-Host "Compiling TypeScript..."
    npx tsc

    # Build electron app
    Write-Host "Building Electron app..."
    if ($Platform -eq "win32") {
        npm run build:win
    } elseif ($Platform -eq "darwin") {
        npm run build:mac
    } else {
        npm run build:linux
    }

    Pop-Location
    Write-Host "[3/3] Electron build complete!" -ForegroundColor Green
}

# Main
switch ($Target) {
    "backend" { Build-Backend }
    "frontend" { Build-Frontend }
    "electron" { Build-Electron }
    "all" {
        Build-Backend
        Build-Frontend
        Build-Electron
    }
    default {
        Write-Host "Unknown target: $Target"
        Write-Host "Usage: .\build.ps1 -Target [backend|frontend|electron|all]"
        exit 1
    }
}

Write-Host "`n=== Build Complete! ===" -ForegroundColor Cyan
```

---

## Linux/macOS Build Script (Bash)

```bash
#!/bin/bash
# build.sh - Build script for ZenClip

set -e

TARGET=${1:-all}
PLATFORM=${2:-linux}

echo "=== ZenClip Build Script ==="
echo "Target: $TARGET"
echo "Platform: $PLATFORM"

build_backend() {
    echo -e "\n[1/3] Building Backend..."

    cd backend

    # Install dependencies
    echo "Installing Python dependencies..."
    pip install -r requirements.txt
    pip install pyinstaller

    # Build with PyInstaller
    echo "Building backend executable..."
    pyinstaller zenclip-backend.spec --clean

    cd ..
    echo -e "[1/3] Backend build complete!\n"
}

build_frontend() {
    echo -e "\n[2/3] Building Frontend..."

    cd frontend

    # Install dependencies
    echo "Installing Node dependencies..."
    npm install

    # Build
    echo "Building frontend..."
    npm run build

    cd ..
    echo -e "[2/3] Frontend build complete!\n"
}

build_electron() {
    echo -e "\n[3/3] Building Electron App..."

    cd electron

    # Install dependencies
    echo "Installing Node dependencies..."
    npm install

    # Compile TypeScript
    echo "Compiling TypeScript..."
    npx tsc

    # Build electron app
    echo "Building Electron app..."
    if [ "$PLATFORM" = "darwin" ]; then
        npm run build:mac
    else
        npm run build:linux
    fi

    cd ..
    echo -e "[3/3] Electron build complete!\n"
}

# Main
case $TARGET in
    backend)
        build_backend
        ;;
    frontend)
        build_frontend
        ;;
    electron)
        build_electron
        ;;
    all)
        build_backend
        build_frontend
        build_electron
        ;;
    *)
        echo "Unknown target: $TARGET"
        echo "Usage: ./build.sh [backend|frontend|electron|all] [linux|darwin]"
        exit 1
        ;;
esac

echo -e "\n=== Build Complete! ==="
```

---

## PyInstaller Spec File (backend/zenclip-backend.spec)

```python
# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

# Get backend source directory
backend_dir = Path(SPECPATH)

a = Analysis(
    ['src/app_modular.py'],
    pathex=[str(backend_dir)],
    binaries=[],
    datas=[
        ('static', 'static'),
        ('templates', 'templates'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='zenclip-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

---

## Usage

### Build Everything
```powershell
# Windows
.\scripts\build.ps1 -Target all

# Linux/macOS
./scripts/build.sh all
```

### Build Individual Components
```powershell
# Backend only
.\scripts\build.ps1 -Target backend

# Frontend only
.\scripts\build.ps1 -Target frontend

# Electron only
.\scripts\build.ps1 -Target electron
```

### Cross-Platform Build
```powershell
# Build for macOS
.\scripts\build.ps1 -Target electron -Platform darwin

# Build for Linux
.\scripts\build.ps1 -Target electron -Platform linux
```

---

*Build scripts generated: 2026-04-04*
