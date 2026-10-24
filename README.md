# RAZESE Optimizer

**RAZESE Optimizer** is a premium Windows tool designed to maximize system performance, reduce input lag in games, and relieve the operating system from unnecessary background loads[cite: 1].

The application is built on a modern interface using the **CustomTkinter** library[cite: 1, 4] and offers an elegant dark-mode design with a detailed overview of your PC's status.

---

## 🚀 Key Features

* **Performance Optimization (MAX FPS):** Unlocks the hidden *Ultimate Performance* power plan[cite: 1], maximizes CPU boost, enables Hardware-Accelerated GPU Scheduling (HAGS), game mode, and disables unnecessary window animations for instant response[cite: 4].
* **Game Management & Optimization:** Automatically detects installed games (Steam, Epic Games, GOG) or allows you to add custom `.exe` files. For each game, it can enforce maximum GPU performance and CPU priority[cite: 4].
* **Live System Monitor:** Tracks the usage of the CPU (including individual cores), RAM, disks, and graphics card in real-time, along with an overview of top memory consumers and a process manager[cite: 4].
* **Pro Tools:** Includes utilities for quickly freeing up RAM, ping and Wi-Fi testing, finding the fastest DNS (Cloudflare, Google, Quad9), SSD TRIM, clearing shader cache, and repairing system files (SFC + DISM)[cite: 4].
* **System Bloatware Removal:** Disables unnecessary Windows services, background telemetry tasks, background apps (OneDrive, Teams, Widgets, etc.), and manages startup applications[cite: 4].
* **Custom Tweaks:** The ability to add and run custom scripts (PowerShell, CMD) or clean folders directly through the application interface[cite: 4].

---

## 🛠️ Installation & Building

If you want to build the executable `.exe` file yourself from the source code, use the included `build.bat` script[cite: 2], which automatically installs required dependencies (Python packages like `customtkinter`, `psutil`, `pillow`, `pyinstaller`)[cite: 1, 2], creates the icon[cite: 2, 3], and packages the app into a single executable file using PyInstaller[cite: 1, 2].

1. Make sure you have **Python** installed (with the *"Add python.exe to PATH"* option checked)[cite: 2].
2. Run the **`build.bat`** file[cite: 2].
3. Done! You will find the resulting executable in the `bcg/RAZESE Optimizer.exe` folder[cite: 2].

---

## ⚠️ Disclaimer
The application requires **Administrator privileges** because it modifies system registry keys, power settings, and Windows services[cite: 1, 4]. Before making mass adjustments, the application automatically creates a system restore point[cite: 4].
