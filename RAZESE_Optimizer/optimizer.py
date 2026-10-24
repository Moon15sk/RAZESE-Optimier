import customtkinter as ctk
from tkinter import filedialog, messagebox
import subprocess, threading, json, os, sys, ctypes, re, shutil, winreg, uuid, time, hashlib
try:
    import psutil
except Exception:
    psutil = None
try:
    from PIL import Image, ImageDraw
    PIL_OK = True
except Exception:
    PIL_OK = False
from ui_extras import Splash, Gauge, CoreBars

APP = "RAZESE Optimizer"
GOLD, GOLD2 = "#D4AF37", "#F3D77A"
BG, CARD, CARD2 = "#0A0A0E", "#13131A", "#1B1B25"
TXT, MUTED, LINE = "#EDEDED", "#8A8A98", "#262633"
NO_WIN = 0x08000000
W64 = winreg.KEY_WOW64_64KEY
HIVES = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}

_APPDATA = os.environ.get("APPDATA", ".")
DATA = os.path.join(_APPDATA, "RAZESE Optimizer")
_OLD = os.path.join(_APPDATA, "BCG Optimizer")
if os.path.isdir(_OLD) and not os.path.isdir(DATA):
    try:
        os.rename(_OLD, DATA)
    except OSError:
        pass
os.makedirs(DATA, exist_ok=True)
BK = os.path.join(DATA, "backup.json")
CFG = os.path.join(DATA, "config.json")
CUS = os.path.join(DATA, "custom.json")
GAMES = os.path.join(DATA, "games.json")        # manually added games
GOPT = os.path.join(DATA, "games_opt.json")     # optimized games
LOCK = threading.RLock()
ICONS = os.path.join(DATA, "icons")
os.makedirs(ICONS, exist_ok=True)


def res(p):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, p)


def jload(p, default):
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def jsave(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def sh(cmd, ps=False):
    if ps:
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
               "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;" + cmd]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=NO_WIN)
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def run(cmd, ps=False):
    return sh(cmd, ps)[1]


def lerp(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


# ---------- registry with backup ----------
def reg_get(hive, path, name):
    try:
        with winreg.OpenKey(HIVES[hive], path, 0, winreg.KEY_READ | W64) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def reg(hive, path, name, value, typ=winreg.REG_DWORD):
    key = f"{hive}|{path}|{name}"
    with LOCK:
        bk = jload(BK, {})
        if key not in bk:
            try:
                with winreg.OpenKey(HIVES[hive], path, 0, winreg.KEY_READ | W64) as k:
                    v, t = winreg.QueryValueEx(k, name)
                    isb = isinstance(v, bytes)
                    bk[key] = {"v": list(v) if isb else v, "t": t, "b": isb}
            except OSError:
                bk[key] = None
            jsave(BK, bk)
        with winreg.CreateKeyEx(HIVES[hive], path, 0, winreg.KEY_SET_VALUE | W64) as k:
            winreg.SetValueEx(k, name, 0, typ, value)


def revert_regs():
    with LOCK:
        bk = jload(BK, {})
        extra = {}
        for key, old in bk.items():
            if key.startswith("_"):
                extra[key] = old
                continue
            try:
                if "|" in key:
                    hive, path, name = key.split("|", 2)
                else:  # legacy format
                    hive, rest = key.split("\\", 1)
                    path, name = rest.rsplit("\\", 1)
                if old is None:
                    with winreg.OpenKey(HIVES[hive], path, 0, winreg.KEY_SET_VALUE | W64) as k:
                        winreg.DeleteValue(k, name)
                else:
                    v = bytes(old["v"]) if old["b"] else old["v"]
                    with winreg.CreateKeyEx(HIVES[hive], path, 0, winreg.KEY_SET_VALUE | W64) as k:
                        winreg.SetValueEx(k, name, 0, old["t"], v)
            except Exception:
                pass
        jsave(BK, {})
        return extra


def flag(name, value=True):
    with LOCK:
        bk = jload(BK, {})
        bk.setdefault(name, value)
        jsave(BK, bk)


# ---------- file helpers ----------
def protected_paths():
    e = os.environ.get
    drive = e("SystemDrive", "C:")
    items = [drive + "\\", drive + "\\Users", e("WINDIR", r"C:\Windows"),
             os.path.join(e("WINDIR", r"C:\Windows"), "System32"), e("ProgramFiles", ""),
             e("ProgramFiles(x86)", ""), e("USERPROFILE", ""), e("ProgramData", "")]
    return {os.path.normpath(i).lower() for i in items if i}


def wipe(raw, strict=True):
    """Delete everything inside a folder (not the folder itself)."""
    p = os.path.normpath(os.path.expandvars(str(raw).strip().strip('"')))
    if not os.path.isdir(p):
        if strict:
            raise Exception(f"Priečinok neexistuje: {p}")
        return 0
    if os.path.dirname(p) == p or p.lower() in protected_paths():
        raise Exception(f"Chránený systémový priečinok: {p}")
    n = 0
    for name in os.listdir(p):
        fp = os.path.join(p, name)
        try:
            if os.path.isdir(fp) and not os.path.islink(fp):
                shutil.rmtree(fp, ignore_errors=True)
            else:
                os.remove(fp)
            n += 1
        except Exception:
            pass
    return n


def svc_off(name):
    if reg_get("HKLM", rf"SYSTEM\CurrentControlSet\Services\{name}", "Start") is None:
        return False
    try:
        reg("HKLM", rf"SYSTEM\CurrentControlSet\Services\{name}", "Start", 4)
    except OSError:
        pass
    run(["sc", "stop", name])
    return True


# ---------- built-in tweaks ----------
def t_anim():
    sz = winreg.REG_SZ
    reg("HKCU", r"Control Panel\Desktop\WindowMetrics", "MinAnimate", "0", sz)
    reg("HKCU", r"Control Panel\Desktop", "MenuShowDelay", "0", sz)
    reg("HKCU", r"Control Panel\Desktop", "UserPreferencesMask",
        bytes([0x90, 0x12, 0x03, 0x80, 0x10, 0x00, 0x00, 0x00]), winreg.REG_BINARY)
    adv = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
    reg("HKCU", adv, "TaskbarAnimations", 0)
    reg("HKCU", adv, "ListviewAlphaSelect", 0)
    reg("HKCU", adv, "ListviewShadow", 0)
    reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects", "VisualFXSetting", 2)
    reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency", 0)


def t_bg():
    reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "GlobalUserDisabled", 1)
    reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Search", "BackgroundAppGlobalToggle", 0)
    reg("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\AppPrivacy", "LetAppsRunInBackground", 2)
    cdm = r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
    for n in ("SilentInstalledAppsEnabled", "SystemPaneSuggestionsEnabled",
              "SubscribedContent-338388Enabled", "SubscribedContent-338389Enabled", "PreInstalledAppsEnabled"):
        reg("HKCU", cdm, n, 0)
    edge = r"SOFTWARE\Policies\Microsoft\Edge"
    reg("HKLM", edge, "StartupBoostEnabled", 0)
    reg("HKLM", edge, "BackgroundModeEnabled", 0)


def t_telemetry():
    reg("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\DataCollection", "AllowTelemetry", 0)
    reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\AdvertisingInfo", "Enabled", 0)
    svc_off("DiagTrack")
    svc_off("dmwappushservice")


def t_ui():
    adv = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
    reg("HKCU", adv, "TaskbarDa", 0)
    reg("HKCU", adv, "TaskbarMn", 0)
    reg("HKCU", adv, "ShowTaskViewButton", 0)
    reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Search", "BingSearchEnabled", 0)
    reg("HKCU", r"Software\Policies\Microsoft\Windows\WindowsCopilot", "TurnOffWindowsCopilot", 1)


def t_net():
    prof = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
    reg("HKLM", prof, "NetworkThrottlingIndex", 0xFFFFFFFF)
    base = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
    with winreg.OpenKey(HIVES["HKLM"], base, 0, winreg.KEY_READ | W64) as k:
        i, subs = 0, []
        while True:
            try:
                subs.append(winreg.EnumKey(k, i)); i += 1
            except OSError:
                break
    for s in subs:
        reg("HKLM", base + "\\" + s, "TcpAckFrequency", 1)
        reg("HKLM", base + "\\" + s, "TCPNoDelay", 1)
    run(["netsh", "int", "tcp", "set", "global", "autotuninglevel=normal"])
    run(["netsh", "int", "tcp", "set", "global", "rss=enabled"])
    run(["ipconfig", "/flushdns"])


def t_delivery():
    reg("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\DeliveryOptimization", "DODownloadMode", 0)


def t_power():
    out = run(["powercfg", "-duplicatescheme", "e9a42b02-d5df-448d-aa00-03f14749eb61"])
    m = re.search(r"([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})", out)
    guid = m.group(1) if m else "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"  # fallback: High performance
    if m:
        run(["powercfg", "-changename", guid, "Ultimate Performance"])
    run(["powercfg", "-setactive", guid])


def t_cpu():
    for alias, val in (("PROCTHROTTLEMIN", "100"), ("PROCTHROTTLEMAX", "100"),
                       ("CPMINCORES", "100"), ("PERFBOOSTMODE", "2"), ("SYSCOOLPOL", "1")):
        run(["powercfg", "-setacvalueindex", "SCHEME_CURRENT", "SUB_PROCESSOR", alias, val])
    run(["powercfg", "-setactive", "SCHEME_CURRENT"])
    reg("HKLM", r"SYSTEM\CurrentControlSet\Control\PriorityControl", "Win32PrioritySeparation", 38)
    reg("HKLM", r"SYSTEM\CurrentControlSet\Control\Power\PowerThrottling", "PowerThrottlingOff", 1)


def t_gpu():
    reg("HKLM", r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", 2)
    reg("HKCU", r"System\GameConfigStore", "GameDVR_Enabled", 0)
    reg("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled", 1)
    reg("HKCU", r"Software\Microsoft\GameBar", "AllowAutoGameMode", 1)
    reg("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\GameDVR", "AllowGameDVR", 0)
    prof = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
    reg("HKLM", prof, "SystemResponsiveness", 0)
    g = prof + r"\Tasks\Games"
    reg("HKLM", g, "GPU Priority", 8)
    reg("HKLM", g, "Priority", 6)
    reg("HKLM", g, "Scheduling Category", "High", winreg.REG_SZ)
    reg("HKLM", g, "SFIO Priority", "High", winreg.REG_SZ)


def t_core():
    reg("HKLM", r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity", "Enabled", 0)


def t_usb():
    run(["powercfg", "-setacvalueindex", "SCHEME_CURRENT", "2a737441-1930-4402-8d77-b2bebba308a3",
         "48e6b7a6-50f5-4782-a5d4-53bb8f07e226", "0"])
    run(["powercfg", "-setacvalueindex", "SCHEME_CURRENT", "SUB_PCIE", "ASPM", "0"])
    run(["powercfg", "-setacvalueindex", "SCHEME_CURRENT", "SUB_DISK", "DISKIDLE", "0"])
    run(["powercfg", "-setactive", "SCHEME_CURRENT"])


def t_fast():
    reg("HKCU", r"Control Panel\Desktop", "WaitToKillAppTimeout", "2000", winreg.REG_SZ)
    reg("HKCU", r"Control Panel\Desktop", "HungAppTimeout", "2000", winreg.REG_SZ)
    reg("HKCU", r"Control Panel\Desktop", "AutoEndTasks", "1", winreg.REG_SZ)
    reg("HKLM", r"SYSTEM\CurrentControlSet\Control", "WaitToKillServiceTimeout", "2000", winreg.REG_SZ)
    reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Serialize", "StartupDelayInMSec", 0)


def t_ntfs():
    run(["fsutil", "behavior", "set", "disablelastaccess", "1"])
    flag("_lastaccess")


def t_sysmain():
    svc_off("SysMain")


def t_hib():
    with LOCK:
        bk = jload(BK, {})
        if "_hib" not in bk:
            v = reg_get("HKLM", r"SYSTEM\CurrentControlSet\Control\Power", "HibernateEnabled")
            bk["_hib"] = int(v) if v is not None else 1
            jsave(BK, bk)
    run(["powercfg", "-h", "off"])


def t_mouse():
    sz = winreg.REG_SZ
    reg("HKCU", r"Control Panel\Mouse", "MouseSpeed", "0", sz)
    reg("HKCU", r"Control Panel\Mouse", "MouseThreshold1", "0", sz)
    reg("HKCU", r"Control Panel\Mouse", "MouseThreshold2", "0", sz)


def t_clean():
    n = 0
    for d in {os.environ.get("TEMP"), os.environ.get("TMP"), r"C:\Windows\Temp"}:
        if d:
            n += wipe(d, False)
    run("Clear-RecycleBin -Force -ErrorAction SilentlyContinue", ps=True)
    return f"{n} položiek"


def t_deep():
    n = 0
    la = os.environ.get("LOCALAPPDATA", "")
    for d in (la + r"\CrashDumps", r"C:\Windows\Minidump",
              r"C:\ProgramData\Microsoft\Windows\WER\ReportArchive",
              r"C:\ProgramData\Microsoft\Windows\WER\ReportQueue"):
        n += wipe(d, False)
    run(["net", "stop", "wuauserv"])
    n += wipe(r"C:\Windows\SoftwareDistribution\Download", False)
    run(["net", "start", "wuauserv"])
    return f"{n} položiek"


def t_fso():
    gc = r"System\GameConfigStore"
    reg("HKCU", gc, "GameDVR_FSEBehaviorMode", 2)
    reg("HKCU", gc, "GameDVR_HonorUserFSEBehaviorMode", 1)
    reg("HKCU", gc, "GameDVR_FSEBehavior", 2)
    reg("HKCU", gc, "GameDVR_DXGIHonorFSEWindowsCompatible", 1)


def t_quiet():
    reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\PushNotifications", "ToastEnabled", 0)
    reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "ShowSyncProviderNotifications", 0)
    reg("HKCU", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SoftLandingEnabled", 0)


def t_wsearch():
    svc_off("WSearch")


def t_xbox():
    for sname in ("XblAuthManager", "XblGameSave", "XboxNetApiSvc", "XboxGipSvc"):
        svc_off(sname)


NIC_PROPS = [("Interrupt Moderation", "Disabled"), ("Roaming Sensitivity Level", "Lowest"),
             ("Transmit Power", "Highest"), ("MIMO Power Save Mode", "No SMPS"), ("U-APSD support", "Disabled"),
             ("Throughput Booster", "Enabled"), ("Energy-Efficient Ethernet", "Disabled"),
             ("Green Ethernet", "Disabled"), ("Flow Control", "Disabled"), ("Power Saving Mode", "Disabled")]


def nic_adv_reset():
    names = ",".join(f"'{n}'" for n, _ in NIC_PROPS)
    run("foreach($a in (Get-NetAdapter -Physical)){foreach($n in @(" + names + ")){"
        "try{Reset-NetAdapterAdvancedProperty -Name $a.Name -DisplayName $n -ErrorAction Stop}catch{}}}", ps=True)


def t_vbs():
    reg("HKLM", r"SYSTEM\CurrentControlSet\Control\DeviceGuard", "EnableVirtualizationBasedSecurity", 0)


def t_timer():
    reg("HKLM", r"SYSTEM\CurrentControlSet\Control\Session Manager\kernel", "GlobalTimerResolutionRequests", 1)
    rc, _, _ = sh(["bcdedit", "/set", "disabledynamictick", "yes"])
    if rc == 0:
        flag("_bcd")


def t_mpo():
    reg("HKLM", r"SOFTWARE\Microsoft\Windows\Dwm", "OverlayTestMode", 5)


def t_cstate():
    run(["powercfg", "-setacvalueindex", "SCHEME_CURRENT", "54533251-82be-4824-96c1-47b60b740d00",
         "5d76a2ca-e8c0-402f-a133-2158492d58ad", "1"])
    run(["powercfg", "-setactive", "SCHEME_CURRENT"])
    flag("_idle")


def t_nic_pm():
    sh("Get-NetAdapter -Physical | ForEach-Object { Disable-NetAdapterPowerManagement -Name $_.Name "
       "-ErrorAction SilentlyContinue }", ps=True)
    flag("_nicpm")


def t_nic_adv():
    props = ",".join(f"@('{n}','{v}')" for n, v in NIC_PROPS)
    script = (f"$props=@({props});$c=0;"
              "foreach($a in (Get-NetAdapter -Physical | Where-Object Status -eq 'Up')){foreach($p in $props){"
              "try{Set-NetAdapterAdvancedProperty -Name $a.Name -DisplayName $p[0] -DisplayValue $p[1] "
              "-ErrorAction Stop;$c++}catch{}}};$c")
    rc, out, err = sh(script, ps=True)
    flag("_nicadv")
    return f"{out.strip() or 0} nastavení ovládača karty"


def t_tcp_lat():
    for a in ("rsc=disabled", "nonsackrttresiliency=disabled", "maxsynretransmissions=2", "ecncapability=disabled"):
        run(["netsh", "int", "tcp", "set", "global", a])
    run(["netsh", "int", "tcp", "set", "heuristics", "disabled"])
    reg("HKLM", r"SOFTWARE\Policies\Microsoft\Windows\Psched", "NonBestEffortLimit", 0)
    flag("_tcp")


BLOAT_SERVICES = ("Fax", "MapsBroker", "RetailDemo", "WMPNetworkSvc", "RemoteRegistry", "WerSvc", "lfsvc",
                  "WpcMonSvc", "SEMgrSvc", "PhoneSvc", "icssvc", "WalletService", "TrkWks", "SCardSvr",
                  "ScDeviceEnum", "wisvc", "AJRouter", "lltdsvc", "WFDSConMgrSvc", "SmsRouter", "PcaSvc",
                  "diagnosticshub.standardcollector.service", "CscService", "SharedRealitySvc", "spectrum")
BLOAT_TASKS = (r"\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser",
               r"\Microsoft\Windows\Application Experience\ProgramDataUpdater",
               r"\Microsoft\Windows\Application Experience\StartupAppTask",
               r"\Microsoft\Windows\Customer Experience Improvement Program\Consolidator",
               r"\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip",
               r"\Microsoft\Windows\Customer Experience Improvement Program\KernelCeipTask",
               r"\Microsoft\Windows\DiskDiagnostic\Microsoft-Windows-DiskDiagnosticDataCollector",
               r"\Microsoft\Windows\Windows Error Reporting\QueueReporting",
               r"\Microsoft\Windows\Feedback\Siuf\DmClient",
               r"\Microsoft\Windows\Feedback\Siuf\DmClientOnScenarioDownload",
               r"\Microsoft\Windows\Autochk\Proxy")
KILL_PROCS = ("OneDrive.exe", "Teams.exe", "ms-teams.exe", "Widgets.exe", "WidgetService.exe",
              "PhoneExperienceHost.exe", "YourPhone.exe", "GameBarPresenceWriter.exe", "GameBar.exe",
              "GameBarFTServer.exe", "MicrosoftEdgeUpdate.exe", "Cortana.exe", "SkypeApp.exe",
              "SkypeBackgroundHost.exe", "HxTsr.exe", "HxOutlook.exe", "CompatTelRunner.exe", "GoogleUpdate.exe",
              "jusched.exe", "AdobeARM.exe", "AdobeIPCBroker.exe", "AdobeUpdateService.exe")
STARTUP_JUNK = ("onedrive", "teams", "spotify", "discord", "steam", "epicgames", "skype", "adobe", "googleupdate",
                "cortana", "yourphone", "phone link", "opera", "utorrent", "bittorrent", "zoom", "slack", "dropbox",
                "ccleaner", "jusched", "itunes", "ipodservice", "msedge", "microsoftedge")


def t_svc_bloat():
    n = sum(1 for sname in BLOAT_SERVICES if svc_off(sname))
    return f"{n} služieb vypnutých"


def t_tasks_bloat():
    n = 0
    for tn in BLOAT_TASKS:
        rc, _, _ = sh(["schtasks", "/Change", "/TN", tn, "/Disable"])
        n += rc == 0
    if n:
        flag("_tasks")
    return f"{n} úloh vypnutých"


def t_kill_bg():
    n = 0
    for p in KILL_PROCS:
        rc, _, _ = sh(["taskkill", "/f", "/im", p])
        n += rc == 0
    return f"ukončených {n} procesov"


def t_startup_trim():
    n = 0
    for it in list_startup():
        if it["enabled"] and any(k in (it["name"] + " " + it["cmd"]).lower() for k in STARTUP_JUNK):
            reg(it["hive"], STARTUP_APPROVED % it["sub"], it["name"], bytes([3] + [0] * 11), winreg.REG_BINARY)
            n += 1
    return f"{n} aplikácií vypnutých pri štarte"


# (id, category, title, description, function, default ON)
TWEAKS = [
    ("power", "VÝKON", "Ultimate Performance", "Skrytý plán napájania s maximálnym výkonom", t_power, True),
    ("cpu", "VÝKON", "CPU Max Boost", "Bez parkovania jadier, 100 % takt, agresívny boost", t_cpu, True),
    ("gpu", "VÝKON", "GPU & Ultra Low Latency", "HW plánovanie GPU, Game Mode, herná priorita", t_gpu, True),
    ("anim", "VÝKON", "Vypnúť animácie a priehľadnosť", "Okná, panel úloh, menu – okamžitá odozva", t_anim, True),
    ("usb", "VÝKON", "Vypnúť šetrenie energie USB / PCIe / disk", "Bez uspávania USB, PCIe linky a disku", t_usb, True),
    ("fast", "VÝKON", "Rýchlejší štart a vypínanie", "Kratšie čakanie na ukončenie apiek a služieb", t_fast, True),
    ("ntfs", "VÝKON", "NTFS bez zápisu posledného prístupu", "Menej zbytočných zápisov na disk", t_ntfs, True),
    ("core", "VÝKON", "Vypnúť Core Isolation", "Memory Integrity OFF (vyžaduje reštart)", t_core, True),
    ("sysmain", "VÝKON", "Vypnúť SysMain (Superfetch)", "Len pre SSD disky – na HDD to nechaj vypnuté", t_sysmain, False),
    ("hib", "VÝKON", "Vypnúť hibernáciu", "Uvoľní niekoľko GB na disku", t_hib, False),
    ("mouse", "VÝKON", "Vypnúť zrýchlenie myši", "Presnejšie mierenie (zmení pocit z myši)", t_mouse, False),
    ("fso", "VÝKON", "Vypnúť Fullscreen Optimizations (globálne)", "Menší input lag v hrách na celú obrazovku", t_fso, False),
    ("wsearch", "VÝKON", "Vypnúť indexovanie (Windows Search)", "Menej zaťaženia disku, hľadanie bude pomalšie", t_wsearch, False),
    ("xbox", "VÝKON", "Vypnúť Xbox služby", "Nechaj zapnuté, ak používaš Xbox appku alebo Game Pass", t_xbox, False),
    ("svc_bloat", "ODĽAHČENIE CPU", "Vypnúť nepotrebné služby Windowsu", "Fax, mapy, vzdialený register, hlásenie chýb, poloha a ďalšie (~25 služieb)", t_svc_bloat, True),
    ("tasks_bloat", "ODĽAHČENIE CPU", "Vypnúť telemetrické úlohy na pozadí", "Compatibility Appraiser, CEIP, diagnostika a podobne", t_tasks_bloat, True),
    ("kill_bg", "ODĽAHČENIE CPU", "Ukončiť nepotrebné procesy na pozadí", "OneDrive, Teams, Widgets, Phone Link, Game Bar, updatery…", t_kill_bg, True),
    ("startup_trim", "ODĽAHČENIE CPU", "Vypnúť zbytočné spúšťanie so systémom", "OneDrive, Teams, Spotify, Discord, Steam, Adobe… (späť zapneš v Nástrojoch)", t_startup_trim, True),
    ("vbs", "FPS BOOST", "Vypnúť VBS (virtualizácia zabezpečenia)", "Pár % FPS navyše, nižšia ochrana pred malvérom", t_vbs, True),
    ("timer", "FPS BOOST", "Presný časovač (nižší input lag)", "Vypne dynamický tick, plynulejšie snímky (vyžaduje reštart)", t_timer, True),
    ("mpo", "FPS BOOST", "Vypnúť Multiplane Overlay (MPO)", "Rieši seknutie a blikanie pri hrách", t_mpo, False),
    ("cstate", "FPS BOOST", "CPU bez uspávania jadier", "Najnižšia latencia CPU – viac tepla a spotreby, len desktop", t_cstate, False),
    ("net", "SIEŤ", "Turbo internet", "Nižší ping, vypnutý Nagle, bez sieťového throttlingu", t_net, True),
    ("delivery", "SIEŤ", "Vypnúť zdieľanie aktualizácií (P2P)", "Windows nebude posielať updaty cez tvoj internet", t_delivery, True),
    ("nic_pm", "SIEŤ", "Sieťová karta bez šetrenia energie", "Wi-Fi / LAN sa nikdy neuspí – stabilnejší ping", t_nic_pm, True),
    ("nic_adv", "SIEŤ", "Wi-Fi / LAN Turbo (ovládač karty)", "Bez moderácie prerušení, max. výkon vysielania a nízka latencia", t_nic_adv, True),
    ("tcp_lat", "SIEŤ", "TCP bez zbytočných oneskorení", "Vypne RSC a čakania, nižší ping v hrách", t_tcp_lat, True),
    ("bg", "SÚKROMIE A BLOAT", "Vypnúť apky na pozadí", "Windows apky, reklamné návrhy, Edge na pozadí", t_bg, True),
    ("telemetry", "SÚKROMIE A BLOAT", "Vypnúť telemetriu", "Menej odosielania dát a bežiacich služieb", t_telemetry, True),
    ("ui", "SÚKROMIE A BLOAT", "Čistejšie rozhranie", "Bez Widgets, Chat, Copilot a webového hľadania", t_ui, True),
    ("quiet", "SÚKROMIE A BLOAT", "Tichý režim", "Vypne upozornenia a tipy Windowsu", t_quiet, False),
    ("clean", "ČISTENIE", "Vyčistiť dočasné súbory", "Temp, Windows Temp a kôš", t_clean, True),
    ("deep", "ČISTENIE", "Hlboké čistenie", "Crash dumps, chybové hlásenia, cache aktualizácií", t_deep, True),
]

PRESETS = {
    "MAX FPS": ["power", "cpu", "gpu", "anim", "usb", "fast", "ntfs", "core", "vbs", "timer", "fso", "mouse",
                "bg", "telemetry", "quiet", "clean"],
    "ZERO LAG WI-FI": ["net", "delivery", "nic_pm", "nic_adv", "tcp_lat", "usb", "bg", "power"],
    "ODĽAHČIŤ CPU": ["svc_bloat", "tasks_bloat", "kill_bg", "startup_trim", "bg", "telemetry", "ui", "quiet",
                     "delivery", "anim"],
    "VŠETKO": None,
}

TYPES = {"Zmazať obsah priečinka": "folder", "PowerShell": "ps", "CMD": "cmd"}
TYPE_NAME = {v: k for k, v in TYPES.items()}
EXAMPLES = {
    "folder": "%temp%",
    "ps": 'Remove-Item "$env:TEMP\\*" -Recurse -Force -ErrorAction SilentlyContinue',
    "cmd": "ipconfig /flushdns",
}
HINTS = {
    "folder": "Zadaj cestu (každú na nový riadok), napr. %temp%. Zmaže sa celý obsah – ako Win+R → %temp% → Ctrl+A → Delete.",
    "ps": "Príkazy PowerShellu. Viac riadkov je v poriadku.",
    "cmd": "Príkazy ako v .bat súbore (v cykloch for používaj %%x).",
}


def make_custom(c):
    def fn():
        t, code = c["type"], c["code"]
        if t == "folder":
            n = sum(wipe(line) for line in code.splitlines() if line.strip())
            return f"zmazaných {n} položiek"
        if t == "cmd":
            p = os.path.join(DATA, "_tmp_" + uuid.uuid4().hex[:6] + ".bat")
            with open(p, "w", encoding="utf-8") as f:
                f.write("@echo off\nchcp 65001 >nul\n" + code + "\n")
            try:
                rc, out, err = sh(["cmd", "/c", p])
            finally:
                try:
                    os.remove(p)
                except OSError:
                    pass
        else:
            rc, out, err = sh(code, ps=True)
        if rc != 0:
            raise Exception((err or out or f"kód skončil s chybou {rc}")[:160])
    return fn


# ---------- hardware scan ----------
PS_CPU = r'''
$c=Get-CimInstance Win32_Processor|Select -First 1;$b=Get-CimInstance Win32_BaseBoard;
$bi=Get-CimInstance Win32_BIOS;$cs=Get-CimInstance Win32_ComputerSystem;$o=Get-CimInstance Win32_OperatingSystem;
[pscustomobject]@{cpu=$c.Name.Trim();cores="$($c.NumberOfCores) jadier / $($c.NumberOfLogicalProcessors) vlákien";
clock=[math]::Round($c.MaxClockSpeed/1000,2);board="$($b.Manufacturer) $($b.Product)";
bios="$($bi.Manufacturer) $($bi.SMBIOSBIOSVersion)";pc="$($cs.Manufacturer) $($cs.Model)";
os="$($o.Caption) ($($o.OSArchitecture)), build $($o.BuildNumber)"}|ConvertTo-Json
'''
PS_GPU = r'''
$g=Get-CimInstance Win32_VideoController|ForEach-Object{[pscustomobject]@{n=$_.Name;d=$_.DriverVersion;
w=$_.CurrentHorizontalResolution;h=$_.CurrentVerticalResolution;r=$_.CurrentRefreshRate}};
$m=Get-CimInstance Win32_PhysicalMemory|ForEach-Object{[pscustomobject]@{c=[math]::Round($_.Capacity/1GB);
s=$_.Speed;t=$_.SMBIOSMemoryType;m=$_.Manufacturer}};
[pscustomobject]@{gpu=@($g);ram=@($m)}|ConvertTo-Json -Depth 4
'''
PS_DISK = r'''
$d=Get-PhysicalDisk|ForEach-Object{[pscustomobject]@{n=$_.FriendlyName;t="$($_.MediaType)";b="$($_.BusType)";
s=[math]::Round($_.Size/1GB)}};
$n=Get-NetAdapter -Physical -ErrorAction SilentlyContinue|Where-Object Status -eq 'Up'|
ForEach-Object{[pscustomobject]@{n=$_.InterfaceDescription;s=$_.LinkSpeed}};
$a=Get-CimInstance Win32_SoundDevice|ForEach-Object{$_.Name};
[pscustomobject]@{disk=@($d);net=@($n);audio=@($a)}|ConvertTo-Json -Depth 4
'''
DDR = {20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4", 34: "DDR5"}


def ps_json(script):
    try:
        out = run(script, ps=True)
        i = out.find("{")
        return json.loads(out[i:]) if i >= 0 else {}
    except Exception:
        return {}


def aslist(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def build_sections(a, b, c):
    S = []
    clean = lambda L: [str(x) for x in L if x not in (None, "", "None")]
    if a:
        S.append(("PROCESOR", clean([a.get("cpu"), a.get("cores"),
                                     f"{a['clock']} GHz (max)" if a.get("clock") else None])))
        S.append(("ZÁKLADNÁ DOSKA", clean([a.get("board"), ("BIOS: " + a["bios"]) if a.get("bios") else None])))
    gp = aslist(b.get("gpu")) if b else []
    if gp:
        L = []
        for g in gp:
            L += [g.get("n"), ("Ovládač " + str(g["d"])) if g.get("d") else None]
        S.append(("GRAFIKA", clean(L)))
        seen = []
        for g in gp:
            if g.get("w") and g.get("h"):
                s = f"{g['w']} × {g['h']}" + (f" @ {g['r']} Hz" if g.get("r") else "")
                if s not in seen:
                    seen.append(s)
        if seen:
            S.append(("OBRAZOVKA", seen))
    mem = aslist(b.get("ram")) if b else []
    if mem:
        total = sum(int(m.get("c") or 0) for m in mem)
        typ = DDR.get(int(mem[0].get("t") or 0), "")
        sp = mem[0].get("s")
        S.append(("PAMÄŤ RAM", clean([f"{total} GB", f"{len(mem)}× {mem[0].get('c')} GB {typ}".strip(),
                                      f"{sp} MHz" if sp else None])))
    if c:
        L = []
        for d in aslist(c.get("disk")):
            t = d.get("t") if d.get("t") not in ("Unspecified", "") else ""
            L.append(" ".join(x for x in [str(d.get("n")), "–", f"{d.get('s')} GB", t, d.get("b")] if x))
        if L:
            S.append(("DISKY", L))
        L = [f"{n.get('n')} – {n.get('s')}" for n in aslist(c.get("net"))]
        if L:
            S.append(("SIEŤ", L))
        L = clean(aslist(c.get("audio")))
        if L:
            S.append(("ZVUK", L))
    if a:
        S.append(("SYSTÉM", clean([a.get("pc"), a.get("os")])))
    return S


# ---------- games ----------
BAD = re.compile(r"(unins|setup|install|redist|dxsetup|dotnet|crash|report|helper|easyanticheat|eac|beservice|"
                 r"battleye|webhelper|notification|updater|oalinst|physx|prereq|bootstrap|cleanup|config|"
                 r"settings|server|cef|vulkan|vcredist|vc_redist)", re.I)


def subkeys(hive, path):
    out = []
    try:
        with winreg.OpenKey(HIVES[hive], path, 0, winreg.KEY_READ | W64) as k:
            i = 0
            while True:
                try:
                    out.append(winreg.EnumKey(k, i)); i += 1
                except OSError:
                    break
    except OSError:
        pass
    return out


def scan_games():
    games = {}
    # Steam
    try:
        sp = reg_get("HKCU", r"Software\Valve\Steam", "SteamPath") or \
            reg_get("HKLM", r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")
        if sp:
            sp = os.path.normpath(sp)
            libs = {sp}
            vdf = os.path.join(sp, "steamapps", "libraryfolders.vdf")
            if os.path.isfile(vdf):
                txt = open(vdf, encoding="utf-8", errors="ignore").read()
                for m in re.findall(r'"path"\s+"([^"]+)"', txt):
                    libs.add(os.path.normpath(m.replace("\\\\", "\\")))
            for lib in libs:
                sa = os.path.join(lib, "steamapps")
                if not os.path.isdir(sa):
                    continue
                for fn in os.listdir(sa):
                    if not (fn.startswith("appmanifest_") and fn.endswith(".acf")):
                        continue
                    t = open(os.path.join(sa, fn), encoding="utf-8", errors="ignore").read()
                    nm = re.search(r'"name"\s+"([^"]+)"', t)
                    idr = re.search(r'"installdir"\s+"([^"]+)"', t)
                    st = re.search(r'"StateFlags"\s+"(\d+)"', t)
                    if not nm or not idr or (st and not int(st.group(1)) & 4):
                        continue
                    if re.search(r"Steamworks|Redistributable|Proton|Steam Linux Runtime|Steam Controller",
                                 nm.group(1), re.I):
                        continue
                    d = os.path.join(sa, "common", idr.group(1))
                    if os.path.isdir(d):
                        gid = "steam_" + fn[12:-4]
                        games[gid] = {"id": gid, "name": nm.group(1), "launcher": "Steam", "dir": d}
    except Exception:
        pass
    # Epic Games
    try:
        md = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "Epic", "EpicGamesLauncher", "Data", "Manifests")
        if os.path.isdir(md):
            for fn in os.listdir(md):
                if not fn.endswith(".item"):
                    continue
                j = jload(os.path.join(md, fn), {})
                loc, name = j.get("InstallLocation"), j.get("DisplayName")
                if not loc or not name or not os.path.isdir(loc):
                    continue
                exe = os.path.join(loc, j.get("LaunchExecutable") or "")
                gid = "epic_" + (j.get("AppName") or fn)
                games[gid] = {"id": gid, "name": name, "launcher": "Epic", "dir": loc,
                              "exe": exe if j.get("LaunchExecutable") and os.path.isfile(exe) else ""}
    except Exception:
        pass
    # GOG
    try:
        base = r"SOFTWARE\WOW6432Node\GOG.com\Games"
        for s in subkeys("HKLM", base):
            p = base + "\\" + s
            name, path, exe = (reg_get("HKLM", p, "gameName"), reg_get("HKLM", p, "path"), reg_get("HKLM", p, "exe"))
            if name and path and os.path.isdir(path):
                gid = "gog_" + s
                games[gid] = {"id": gid, "name": name, "launcher": "GOG", "dir": path,
                              "exe": exe if exe and os.path.isfile(exe) else ""}
    except Exception:
        pass
    return sorted(games.values(), key=lambda g: g["name"].lower())


def find_exes(g):
    if g.get("exe") and os.path.isfile(g["exe"]):
        return [g["exe"]]
    base = g.get("dir")
    if not base or not os.path.isdir(base):
        return []
    bl = base.rstrip("\\/").count(os.sep)
    out = []
    for root, dirs, files in os.walk(base):
        for fn in files:
            if fn.lower().endswith(".exe") and not BAD.search(fn):
                p = os.path.join(root, fn)
                try:
                    sz = os.path.getsize(p)
                except OSError:
                    continue
                if sz > 1_000_000:
                    out.append((sz, p))
        if root.count(os.sep) - bl >= 4:
            dirs[:] = []
    out.sort(reverse=True)
    return [p for _, p in out[:3]]


PS_ICONS = r"""param($list)
Add-Type -AssemblyName System.Drawing
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class IconX {
  [DllImport("user32.dll", CharSet=CharSet.Unicode)]
  public static extern uint PrivateExtractIcons(string f, int i, int cx, int cy, IntPtr[] h, uint[] id, uint n, uint fl);
  [DllImport("user32.dll")] public static extern bool DestroyIcon(IntPtr h);
}
"@
foreach ($line in (Get-Content -LiteralPath $list -Encoding UTF8)) {
  $p = $line -split '\|', 2
  if ($p.Count -lt 2) { continue }
  $out = $p[0]; $exe = $p[1]
  try {
    $h = New-Object IntPtr[] 1; $ids = New-Object uint32[] 1
    $n = [IconX]::PrivateExtractIcons($exe, 0, 256, 256, $h, $ids, 1, 0)
    if ($n -ge 1 -and $h[0] -ne [IntPtr]::Zero) {
      $bmp = [System.Drawing.Icon]::FromHandle($h[0]).ToBitmap()
      $bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
      [void][IconX]::DestroyIcon($h[0])
    } else {
      [System.Drawing.Icon]::ExtractAssociatedIcon($exe).ToBitmap().Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
    }
  } catch { }
}
"""


def icon_path(gid):
    return os.path.join(ICONS, re.sub(r"[^A-Za-z0-9_.-]", "_", gid) + ".png")


def extract_icons(games):
    """Pull the real icon out of each game's .exe (256 px) and cache it as PNG."""
    todo = []
    for g in games:
        out = icon_path(g["id"])
        if os.path.isfile(out):
            continue
        exe = g.get("exe") if g.get("exe") and os.path.isfile(g["exe"]) else None
        if not exe:
            ex = find_exes(g)
            exe = ex[0] if ex else None
        if exe:
            todo.append((out, exe))
    if not todo:
        return 0
    lst = os.path.join(DATA, "_icons.txt")
    ps1 = os.path.join(DATA, "_icons.ps1")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("\n".join(f"{o}|{e}" for o, e in todo))
    with open(ps1, "w", encoding="utf-8-sig") as f:
        f.write(PS_ICONS)
    sh(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1, lst])
    return len(todo)


def make_tile(png, done=False):
    """Game icon on a rounded dark tile (gold ring when optimized)."""
    S = 128
    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=28, fill=(35, 35, 47, 255))
    ic = Image.open(png).convert("RGBA")
    ic.thumbnail((92, 92), Image.LANCZOS)
    tile.paste(ic, ((S - ic.width) // 2, (S - ic.height) // 2), ic)
    if done:
        d.rounded_rectangle((1, 1, S - 2, S - 2), radius=28, outline=(212, 175, 55, 255), width=5)
    return tile


def optimize_game(g):
    exes = find_exes(g)
    if not exes:
        raise Exception("Nenašiel som .exe hry")
    layers = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
    ifeo = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"
    for exe in exes:
        reg("HKCU", r"Software\Microsoft\DirectX\UserGpuPreferences", exe, "GpuPreference=2;", winreg.REG_SZ)
        toks = (reg_get("HKCU", layers, exe) or "").replace("~", "").split()
        if "DISABLEDXMAXIMIZEDWINDOWEDMODE" not in toks:
            toks.append("DISABLEDXMAXIMIZEDWINDOWEDMODE")
        reg("HKCU", layers, exe, "~ " + " ".join(toks), winreg.REG_SZ)
        reg("HKLM", ifeo + "\\" + os.path.basename(exe) + r"\PerfOptions", "CpuPriorityClass", 3)
    return exes


# ---------- pro tools ----------
PROTECTED = {"system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe",
             "svchost.exe", "winlogon.exe", "explorer.exe", "dwm.exe", "memory compression",
             "system idle process", "fontdrvhost.exe", "msmpeng.exe", "securityhealthservice.exe",
             "python.exe", "razese optimizer.exe"}
DNS_SETS = {"Cloudflare": ("1.1.1.1", "1.0.0.1"), "Google": ("8.8.8.8", "8.8.4.4"),
            "Quad9": ("9.9.9.9", "149.112.112.112"), "OpenDNS": ("208.67.222.222", "208.67.220.220")}
STARTUP_APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\%s"
RUN_KEYS = (("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run", "Run", "Registry"),
            ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", "Run", "Registry"),
            ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run", "Run32", "Registry"))
_nv = None


def fmt_rate(b):
    return f"{b / 1048576:.1f} MB/s" if b >= 1048576 else f"{b / 1024:.0f} KB/s"


def free_ram():
    k32, ps = ctypes.windll.kernel32, ctypes.windll.psapi
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    ps.EmptyWorkingSet.argtypes = [ctypes.c_void_p]
    before = psutil.virtual_memory().available
    for p in psutil.process_iter(["pid"]):
        try:
            h = k32.OpenProcess(0x0100 | 0x0400, False, p.info["pid"])
            if h:
                ps.EmptyWorkingSet(h)
                k32.CloseHandle(h)
        except Exception:
            pass
    time.sleep(0.4)
    return max(0, (psutil.virtual_memory().available - before) // 1048576)


def gpu_sample():
    global _nv
    if _nv is None:
        _nv = shutil.which("nvidia-smi") is not None
    if _nv:
        rc, out, _ = sh(["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"])
        if rc == 0 and out:
            try:
                u, t = [x.strip() for x in out.splitlines()[0].split(",")]
                return {"util": float(u), "temp": t}
            except Exception:
                pass
    rc, out, _ = sh(r"$s=(Get-Counter '\GPU Engine(*engtype_3D)\Utilization Percentage' -ErrorAction SilentlyContinue)"
                    r".CounterSamples|Measure-Object CookedValue -Sum;[math]::Round($s.Sum)", ps=True)
    try:
        return {"util": min(100.0, float(out)), "temp": ""}
    except Exception:
        return None


def ping_ms(ip):
    rc, out, _ = sh(["ping", "-n", "3", "-w", "1000", ip])
    m = re.findall(r"=\s*(\d+)\s*ms", out)
    return float(m[-1]) if m else float("inf")


def tool_ram():
    if not psutil:
        raise Exception("chýba knižnica psutil")
    return f"uvoľnených ~{free_ram()} MB (dočasne, Windows to časom vráti)"


def tool_dns():
    best = None
    for name, (a, b) in DNS_SETS.items():
        ms = ping_ms(a)
        if best is None or ms < best[0]:
            best = (ms, name, a, b)
    if best is None or best[0] == float("inf"):
        raise Exception("nepodarilo sa zmerať odozvu (si online?)")
    script = ("Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object "
              f"{{ Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses ('{best[2]}','{best[3]}') }}")
    rc, out, err = sh(script, ps=True)
    if rc != 0:
        raise Exception((err or "nastavenie DNS zlyhalo")[:100])
    flag("_dns")
    run(["ipconfig", "/flushdns"])
    return f"{best[1]} DNS nastavený ({best[0]:.0f} ms)"


def tool_netreset():
    run(["ipconfig", "/flushdns"])
    run(["netsh", "winsock", "reset"])
    return "sieť obnovená – reštartuj PC"


def tool_trim():
    rc, out, err = sh("Optimize-Volume -DriveLetter C -ReTrim -ErrorAction Stop", ps=True)
    if rc != 0:
        raise Exception("disk C: nepodporuje TRIM alebo nie je SSD")
    return "TRIM dokončený"


def tool_shader():
    la = os.environ.get("LOCALAPPDATA", "")
    n = sum(wipe(d, False) for d in (la + r"\D3DSCache", la + r"\NVIDIA\DXCache", la + r"\NVIDIA\GLCache",
                                     la + r"\AMD\DxCache", la + r"\AMD\GLCache"))
    return f"zmazaných {n} položiek (hry si ich pri prvom spustení vytvoria znova)"


def tool_sfc():
    sh(["sfc", "/scannow"])
    sh(["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"])
    return "kontrola dokončená – reštartuj PC"


def tool_explorer():
    run(["taskkill", "/f", "/im", "explorer.exe"])
    subprocess.Popen(["explorer.exe"])
    return "Explorer reštartovaný"


def tool_restore():
    rc, out, err = sh("Enable-ComputerRestore -Drive 'C:\\'; Checkpoint-Computer -Description 'RAZESE Optimizer' "
                      "-RestorePointType MODIFY_SETTINGS -ErrorAction Stop", ps=True)
    if rc != 0:
        raise Exception("Windows dovolí vytvoriť bod len raz za 24 hodín")
    return "bod obnovenia vytvorený"


def ping_stats(ip, count=10):
    rc, out, _ = sh(["ping", "-n", str(count), "-w", "1000", ip])
    t = [int(x) for x in re.findall(r"[=<](\d+)\s*ms\s+TTL=", out, re.I)]
    if not t:
        return None
    jit = sum(abs(t[i] - t[i - 1]) for i in range(1, len(t))) / max(1, len(t) - 1)
    return {"min": min(t), "avg": sum(t) / len(t), "max": max(t), "jit": jit, "loss": 100.0 * (count - len(t)) / count}


def tool_wifi():
    parts, band = [], None
    rc, out, _ = sh(["cmd", "/c", "chcp 65001>nul & netsh wlan show interfaces"])
    m = re.search(r"(\d+)\s*%", out)
    if m:
        parts.append(f"signál {m.group(1)} %")
    m = re.search(r"(?:Channel|Kan[aá]l)\s*:\s*(\d+)", out, re.I)
    if m:
        ch = int(m.group(1))
        band = "2,4 GHz" if ch <= 14 else "5/6 GHz"
        parts.append(f"kanál {ch} ({band})")
    if not parts:
        parts.append("Wi-Fi nenájdené (kábel?)")
    worst_jit, worst_loss = 0, 0
    for ip in ("1.1.1.1", "8.8.8.8"):
        r = ping_stats(ip)
        if r:
            parts.append(f"{ip}: {r['avg']:.0f} ms (min {r['min']}, max {r['max']}), jitter {r['jit']:.0f} ms, strata {r['loss']:.0f} %")
            worst_jit, worst_loss = max(worst_jit, r["jit"]), max(worst_loss, r["loss"])
        else:
            parts.append(f"{ip}: bez odpovede")
    tips = []
    if band == "2,4 GHz":
        tips.append("pripoj sa na 5 GHz")
    if worst_loss > 0 or worst_jit > 10:
        tips.append("spojenie je nestabilné – choď bližšie k routeru alebo použi kábel")
    if tips:
        parts.append("Tip: " + "; ".join(tips))
    return " • ".join(parts)


TOOLS = [
    ("killbg", "Ukončiť procesy na pozadí", "Hneď zavrie OneDrive, Teams, Widgets, Phone Link, Game Bar a updatery", t_kill_bg),
    ("ram", "Uvoľniť RAM", "Vyprázdni pracovnú pamäť všetkých procesov", tool_ram),
    ("dns", "Najrýchlejší DNS", "Otestuje Cloudflare, Google, Quad9 a OpenDNS a nastaví najrýchlejší", tool_dns),
    ("ping", "Test pingu a Wi-Fi", "Zmeria ping, jitter, stratu paketov a silu Wi-Fi signálu (trvá cca 20 s)", tool_wifi),
    ("netreset", "Reset siete", "Vyčistí DNS cache a obnoví Winsock (po ňom reštart)", tool_netreset),
    ("trim", "TRIM SSD (C:)", "Optimalizuje SSD disk pre dlhodobý výkon", tool_trim),
    ("shader", "Vyčistiť shader cache", "Pomáha pri seknutí hier po update ovládačov (NVIDIA / AMD / DirectX)", tool_shader),
    ("sfc", "Oprava systému (SFC + DISM)", "Skontroluje a opraví súbory Windowsu – trvá aj 15 minút", tool_sfc),
    ("explorer", "Reštartovať Explorer", "Zrýchli a oživí panel úloh, plochu a Prieskumníka", tool_explorer),
    ("restore", "Vytvoriť bod obnovenia", "Záloha systému pred väčšími zmenami", tool_restore),
]


def list_startup():
    items = []
    for hive, path, sub, src in RUN_KEYS:
        try:
            with winreg.OpenKey(HIVES[hive], path, 0, winreg.KEY_READ | W64) as k:
                i = 0
                while True:
                    try:
                        n, v, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    i += 1
                    items.append({"name": n, "cmd": str(v), "hive": hive, "sub": sub, "src": src})
        except OSError:
            pass
    folders = ((os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"), "HKCU"),
               (os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs\StartUp"), "HKLM"))
    for folder, hive in folders:
        if os.path.isdir(folder):
            for fn in os.listdir(folder):
                if fn.lower() != "desktop.ini":
                    items.append({"name": fn, "cmd": os.path.join(folder, fn), "hive": hive,
                                  "sub": "StartupFolder", "src": "Priečinok"})
    for it in items:
        st = reg_get(it["hive"], STARTUP_APPROVED % it["sub"], it["name"])
        it["enabled"] = not (isinstance(st, (bytes, bytearray)) and len(st) > 0 and st[0] % 2 == 1)
    return items


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title(APP)
        self.geometry("1100x800")
        self.minsize(1000, 720)
        self.configure(fg_color=BG)
        try:
            self.iconbitmap(res("bcg/icon.ico"))
        except Exception:
            pass
        self.busy = False
        self.vars = {}
        self.cfg = jload(CFG, {"autoclose": True, "restart": False, "selected": {}})
        self.customs = jload(CUS, [])
        self.manual = jload(GAMES, [])
        self.gopt = jload(GOPT, {})
        self.games = []
        self.gimgs = {}
        self.icons_busy = False
        self.gcards = {}
        self.running = set()
        self.load_done = False
        self.load_msg = "Spúšťam jadro"
        self.load_target = 0.05
        self.load_items = []
        self.sections = []
        self.cur_tab = "opt"
        self.mon_running = False
        self.gpu = None
        self.gpu_alive = False
        self.proc_info = [None] * 6
        self.f = lambda s, w="normal": ctk.CTkFont(family="Segoe UI", size=s, weight=w)
        self.build()
        self.show("opt")
        self.splash = Splash(self, lambda: {"target": self.load_target, "done": self.load_done,
                                            "msg": self.load_msg, "items": list(self.load_items)},
                             on_ready=self.on_loaded)
        threading.Thread(target=self.load_thread, daemon=True).start()

    # ---------------- loading ----------------
    def load_thread(self):
        a = b = c = {}
        add = lambda label, val: self.load_items.append((time.time(), label, val))
        try:
            self.load_msg = "Skenujem procesor a základnú dosku"
            a = ps_json(PS_CPU)
            if a.get("cpu"):
                add("PROCESOR", a["cpu"])
            self.load_target = 0.30
            self.load_msg = "Skenujem grafiku a pamäť"
            b = ps_json(PS_GPU)
            gp = aslist(b.get("gpu"))
            if gp and gp[0].get("n"):
                add("GRAFIKA", gp[0]["n"])
            mem = aslist(b.get("ram"))
            if mem:
                add("PAMÄŤ", f"{sum(int(m.get('c') or 0) for m in mem)} GB")
            self.load_target = 0.55
            self.load_msg = "Skenujem disky, sieť a zvuk"
            c = ps_json(PS_DISK)
            disks = aslist(c.get("disk"))
            if disks:
                add("ÚLOŽISKO", f"{len(disks)}× disk")
            self.load_target = 0.78
            self.load_msg = "Hľadám nainštalované hry"
            self.games = scan_games()
            add("HRY", f"{len(self.games)} nájdených")
            self.load_target = 0.95
            self.load_msg = "Pripravujem rozhranie"
            self.sections = build_sections(a, b, c)
        except Exception:
            pass
        self.load_target = 1.0
        self.load_done = True

    def on_loaded(self):
        self.populate_sys(self.sections)
        self.refresh_games()
        self.start_icon_load()
        self.refresh_startup()
        self.log("Skenovanie komponentov dokončené.")
        self.log(f"Nájdené hry: {len(self.game_list())}")

    # ---------------- layout ----------------
    def build(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=36, pady=(22, 0))
        tl = ctk.CTkFrame(head, fg_color="transparent")
        tl.pack(side="left")
        row = ctk.CTkFrame(tl, fg_color="transparent")
        row.pack(anchor="w")
        ctk.CTkLabel(row, text="RAZESE", font=self.f(32, "bold"), text_color=GOLD).pack(side="left")
        ctk.CTkLabel(row, text=" OPTIMIZER", font=self.f(32), text_color=TXT).pack(side="left")
        ctk.CTkLabel(tl, text="U L T I M A T E   P E R F O R M A N C E", font=self.f(10, "bold"),
                     text_color=MUTED).pack(anchor="w")
        self.tabs = {}
        for key, label, wd in (("set", "NASTAVENIA", 112), ("tools", "NÁSTROJE", 96), ("mon", "MONITOR", 92),
                               ("games", "HRY", 66), ("opt", "OPTIMALIZÁCIA", 130)):
            b = ctk.CTkButton(head, text=label, width=wd, height=34, corner_radius=17, font=self.f(11, "bold"),
                              command=lambda k=key: self.show(k))
            b.pack(side="right", padx=3, pady=(8, 0))
            self.tabs[key] = b
        ctk.CTkFrame(self, height=2, fg_color=GOLD, corner_radius=0).pack(fill="x", padx=36, pady=(12, 14))

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=36, pady=(0, 20))
        self.build_opt()
        self.build_games()
        self.build_monitor()
        self.build_tools()
        self.build_settings()

    def show(self, key):
        views = {"opt": self.opt, "games": self.gv, "mon": self.monv, "tools": self.toolv, "set": self.setv}
        for v in views.values():
            v.pack_forget()
        views[key].pack(fill="both", expand=True)
        self.cur_tab = key
        for k, b in self.tabs.items():
            on = k == key
            b.configure(fg_color=GOLD if on else CARD2, text_color="#0A0A0E" if on else MUTED,
                        hover_color=GOLD2 if on else "#262633")
        if key == "mon":
            self.mon_start()

    def card(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=18, border_width=1, border_color=LINE, **kw)

    # ---------------- optimization tab ----------------
    def build_opt(self):
        self.opt = ctk.CTkFrame(self.container, fg_color="transparent")
        body = ctk.CTkFrame(self.opt, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = self.card(body, width=330)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 16))
        left.grid_propagate(False)
        ctk.CTkLabel(left, text="KOMPONENTY PC", font=self.f(13, "bold"), text_color=GOLD).pack(
            anchor="w", padx=22, pady=(20, 0))
        self.sysbox = ctk.CTkScrollableFrame(left, fg_color="transparent", scrollbar_button_color="#2A2A36")
        self.sysbox.pack(fill="both", expand=True, padx=6, pady=(0, 10))

        right = self.card(body)
        right.grid(row=0, column=1, sticky="nsew")
        top = ctk.CTkFrame(right, fg_color="transparent")
        top.pack(fill="x", padx=22, pady=(20, 4))
        ctk.CTkLabel(top, text="FUNKCIE", font=self.f(13, "bold"), text_color=GOLD).pack(side="left")
        for pname, pw in (("MAX FPS", 78), ("ZERO LAG WI-FI", 120), ("ODĽAHČIŤ CPU", 112), ("VŠETKO", 64)):
            ctk.CTkButton(top, text=pname, width=pw, height=28, corner_radius=14, fg_color="transparent",
                          border_width=1, border_color=GOLD if pname != "VŠETKO" else LINE,
                          text_color=GOLD if pname != "VŠETKO" else MUTED, hover_color=CARD2, font=self.f(11, "bold"),
                          command=lambda n=pname: self.preset(n)).pack(side="left", padx=(6, 0))
        self.allsw = ctk.CTkSwitch(top, text="Všetky", font=self.f(12), progress_color=GOLD,
                                   command=self.toggle_all, fg_color="#2A2A36")
        self.allsw.pack(side="right")
        self.listf = ctk.CTkScrollableFrame(right, fg_color="transparent", scrollbar_button_color="#2A2A36")
        self.listf.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.refresh_list()

        bottom = ctk.CTkFrame(self.opt, fg_color="transparent")
        bottom.pack(fill="x", pady=(14, 0))
        self.status = ctk.CTkLabel(bottom, text="Vyber funkcie a stlač APPLY", font=self.f(12), text_color=MUTED)
        self.status.pack(anchor="w")
        self.bar = ctk.CTkProgressBar(bottom, height=8, progress_color=GOLD, fg_color="#1E1E28")
        self.bar.set(0)
        self.bar.pack(fill="x", pady=(6, 12))
        btns = ctk.CTkFrame(bottom, fg_color="transparent")
        btns.pack(fill="x")
        self.go = ctk.CTkButton(btns, text="APPLY", height=56, corner_radius=14, font=self.f(18, "bold"),
                                fg_color=GOLD, hover_color=GOLD2, text_color="#0A0A0E", command=self.apply)
        self.go.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(btns, text="Vrátiť späť", height=56, width=150, corner_radius=14, font=self.f(14, "bold"),
                      fg_color="transparent", border_width=1, border_color=GOLD, text_color=GOLD,
                      hover_color=CARD2, command=self.undo).pack(side="left", padx=(12, 0))
        self.logbox = ctk.CTkTextbox(bottom, height=70, fg_color=CARD, text_color=MUTED,
                                     font=ctk.CTkFont(family="Consolas", size=11), corner_radius=12)
        self.logbox.pack(fill="x", pady=(12, 0))
        self.logbox.configure(state="disabled")

    def populate_sys(self, sections):
        for w in self.sysbox.winfo_children():
            w.destroy()
        if not sections:
            ctk.CTkLabel(self.sysbox, text="Nepodarilo sa načítať komponenty.", font=self.f(12),
                         text_color=MUTED).pack(anchor="w", padx=12, pady=12)
        for title, lines in sections:
            ctk.CTkLabel(self.sysbox, text=title, font=self.f(10, "bold"), text_color=GOLD).pack(
                anchor="w", padx=14, pady=(14, 1))
            for ln in lines:
                ctk.CTkLabel(self.sysbox, text=ln, font=self.f(12), text_color=TXT, wraplength=262,
                             justify="left").pack(anchor="w", padx=14)

    def all_tweaks(self):
        out = list(TWEAKS)
        for c in self.customs:
            out.append(("c_" + c["id"], "VLASTNÉ", c["name"], c.get("desc") or TYPE_NAME[c["type"]],
                        make_custom(c), True))
        return out

    def refresh_list(self):
        for w in self.listf.winfo_children():
            w.destroy()
        saved = self.cfg.get("selected", {})
        cat = None
        for tid, c, title, desc, _, default in self.all_tweaks():
            if c != cat:
                cat = c
                ctk.CTkLabel(self.listf, text=c, font=self.f(11, "bold"), text_color=MUTED).pack(
                    anchor="w", padx=12, pady=(12, 2))
            if tid not in self.vars:
                self.vars[tid] = ctk.BooleanVar(value=saved.get(tid, default))
            row = ctk.CTkFrame(self.listf, fg_color=CARD2, corner_radius=12)
            row.pack(fill="x", padx=8, pady=3)
            ctk.CTkSwitch(row, text=title, variable=self.vars[tid], font=self.f(14, "bold"), text_color=TXT,
                          progress_color=GOLD, button_color=GOLD2, button_hover_color="#fff",
                          fg_color="#2A2A36").pack(anchor="w", padx=16, pady=(10, 0))
            ctk.CTkLabel(row, text=desc, font=self.f(11), text_color=MUTED).pack(anchor="w", padx=58, pady=(0, 10))

    def preset(self, name):
        ids = PRESETS[name]
        for tid, var in self.vars.items():
            if not tid.startswith("c_"):
                var.set(True if ids is None else tid in ids)
        self.status.configure(text=f"Preset {name} vybraný – stlač APPLY")

    def toggle_all(self):
        for v in self.vars.values():
            v.set(bool(self.allsw.get()))

    # ---------------- games tab ----------------
    def build_games(self):
        self.gv = ctk.CTkFrame(self.container, fg_color="transparent")
        card = self.card(self.gv)
        card.pack(fill="both", expand=True)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=22, pady=(20, 2))
        ctk.CTkLabel(top, text="TVOJE HRY", font=self.f(13, "bold"), text_color=GOLD).pack(side="left")
        self.gcount = ctk.CTkLabel(top, text="", font=self.f(12), text_color=MUTED)
        self.gcount.pack(side="left", padx=12)
        ctk.CTkButton(top, text="Optimalizovať všetky", height=36, corner_radius=12, fg_color=GOLD,
                      hover_color=GOLD2, text_color="#0A0A0E", font=self.f(12, "bold"),
                      command=self.opt_all_games).pack(side="right")
        ctk.CTkButton(top, text="+ Pridať hru", height=36, corner_radius=12, fg_color="transparent",
                      border_width=1, border_color=GOLD, text_color=GOLD, hover_color=CARD2,
                      font=self.f(12, "bold"), command=self.add_game).pack(side="right", padx=8)
        self.ghint = ctk.CTkLabel(card, text="Klikni na hru a optimalizuje sa (GPU výkon, priorita CPU, herný režim).",
                                  font=self.f(11), text_color=MUTED)
        self.ghint.pack(anchor="w", padx=22, pady=(0, 4))
        self.gscroll = ctk.CTkScrollableFrame(card, fg_color="transparent", scrollbar_button_color="#2A2A36")
        self.gscroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for i in range(3):
            self.gscroll.grid_columnconfigure(i, weight=1, uniform="g")

    def game_list(self):
        seen, out = set(), []
        for g in self.games + self.manual:
            if g["id"] not in seen:
                seen.add(g["id"])
                out.append(g)
        return sorted(out, key=lambda g: g["name"].lower())

    def refresh_games(self):
        for w in self.gscroll.winfo_children():
            w.destroy()
        self.gcards = {}
        gl = self.game_list()
        done = sum(1 for g in gl if g["id"] in self.gopt)
        self.gcount.configure(text=f"{len(gl)} hier  •  {done} optimalizovaných")
        if not gl:
            ctk.CTkLabel(self.gscroll, text="Nenašiel som žiadne hry (Steam, Epic, GOG).\nPridaj ich tlačidlom + Pridať hru.",
                         font=self.f(13), text_color=MUTED, justify="left").grid(row=0, column=0, columnspan=3,
                                                                                 padx=16, pady=20, sticky="w")
        for i, g in enumerate(gl):
            self.make_card(g, i)

    def make_card(self, g, idx):
        gid = g["id"]
        done = gid in self.gopt
        card = ctk.CTkFrame(self.gscroll, fg_color=CARD2, corner_radius=16, border_width=1,
                            border_color=GOLD if done else LINE)
        card.grid(row=idx // 3, column=idx % 3, padx=6, pady=6, sticky="ew")
        card.grid_columnconfigure(1, weight=1)
        try:
            card.configure(cursor="hand2")
        except Exception:
            pass
        badge = ctk.CTkLabel(card, text=g["name"][:1].upper(), width=54, height=54, corner_radius=14,
                             fg_color=GOLD if done else "#23232F", text_color="#0A0A0E" if done else GOLD,
                             font=self.f(24, "bold"))
        badge.grid(row=0, column=0, rowspan=2, padx=(14, 12), pady=14)
        name = ctk.CTkLabel(card, text=g["name"], font=self.f(14, "bold"), text_color=TXT, wraplength=185,
                            justify="left", anchor="w")
        name.grid(row=0, column=1, sticky="w", pady=(16, 0))
        status = ctk.CTkLabel(card, text="", font=self.f(11), anchor="w")
        status.grid(row=1, column=1, sticky="w", pady=(0, 14))
        self.gcards[gid] = {"card": card, "badge": badge, "status": status, "g": g, "icon": False}
        self.set_card(gid, "done" if done else "idle")
        self.try_icon(gid)
        if g.get("launcher") == "Vlastná":
            ctk.CTkButton(card, text="✕", width=24, height=24, fg_color="transparent", hover_color="#3A1D1D",
                          text_color=MUTED, font=self.f(12),
                          command=lambda i=gid: self.remove_game(i)).grid(row=0, column=2, padx=(0, 8), pady=(8, 0))
        for w in (card, badge, name, status):
            w.bind("<Button-1>", lambda e, gg=g: self.click_game(gg))
            w.bind("<Enter>", lambda e, i=gid: self.card_hover(i, True))
            w.bind("<Leave>", lambda e, i=gid: self.card_hover(i, False))

    def card_hover(self, gid, on):
        d = self.gcards.get(gid)
        if d:
            d["card"].configure(border_color=GOLD2 if on else (GOLD if gid in self.gopt else LINE))

    def set_card(self, gid, state, text=None):
        d = self.gcards.get(gid)
        if not d:
            return
        g = d["g"]
        if state == "done":
            d["status"].configure(text="✔ OPTIMALIZOVANÉ", text_color=GOLD)
            d["card"].configure(border_color=GOLD)
            if d.get("icon") and gid in self.gimgs:
                d["badge"].configure(image=self.gimgs[gid]["done"])
            else:
                d["badge"].configure(fg_color=GOLD, text_color="#0A0A0E")
        elif state == "busy":
            d["status"].configure(text="Optimalizujem…", text_color=GOLD2)
        elif state == "err":
            d["status"].configure(text="✖ " + (text or "chyba"), text_color="#E5736B")
        else:
            d["status"].configure(text=f"{g.get('launcher', '')}  •  klikni pre optimalizáciu", text_color=MUTED)

    def start_icon_load(self):
        if self.icons_busy or not PIL_OK:
            return
        self.icons_busy = True
        threading.Thread(target=self.icon_thread, daemon=True).start()

    def icon_thread(self):
        try:
            extract_icons(self.game_list())
            self.ui(self.apply_icons)
        except Exception:
            pass
        finally:
            self.icons_busy = False

    def apply_icons(self):
        for g in self.game_list():
            self.try_icon(g["id"])

    def try_icon(self, gid):
        d = self.gcards.get(gid)
        p = icon_path(gid)
        if not PIL_OK or not d or not os.path.isfile(p):
            return
        try:
            if gid not in self.gimgs:
                a, b = make_tile(p, False), make_tile(p, True)
                self.gimgs[gid] = {"idle": ctk.CTkImage(a, a, size=(56, 56)), "done": ctk.CTkImage(b, b, size=(56, 56))}
            d["badge"].configure(image=self.gimgs[gid]["done" if gid in self.gopt else "idle"], text="",
                                 fg_color="transparent", width=56, height=56)
            d["icon"] = True
        except Exception:
            pass

    def click_game(self, g):
        gid = g["id"]
        if self.busy or gid in self.running:
            return
        if gid in self.gopt:
            self.ghint.configure(text=f"{g['name']} je už optimalizovaná ✔")
            return
        self.running.add(gid)
        self.set_card(gid, "busy")
        threading.Thread(target=self.opt_game_thread, args=(g,), daemon=True).start()

    def opt_game_thread(self, g):
        gid = g["id"]
        try:
            if not self.cfg.get("gaming_base"):
                for fn in (t_power, t_cpu, t_gpu):
                    fn()
                self.cfg["gaming_base"] = True
                jsave(CFG, self.cfg)
            exes = optimize_game(g)
            self.gopt[gid] = {"exes": exes}
            jsave(GOPT, self.gopt)
            self.ui(lambda: self.game_done(gid, g))
        except Exception as e:
            msg = str(e)[:60]
            self.ui(lambda: self.set_card(gid, "err", msg))
        finally:
            self.running.discard(gid)

    def game_done(self, gid, g):
        self.set_card(gid, "done")
        gl = self.game_list()
        self.gcount.configure(text=f"{len(gl)} hier  •  {sum(1 for x in gl if x['id'] in self.gopt)} optimalizovaných")
        self.ghint.configure(text=f"✔ {g['name']} je optimalizovaná")

    def opt_all_games(self):
        todo = [g for g in self.game_list() if g["id"] not in self.gopt and g["id"] not in self.running]
        if self.busy:
            return
        if not todo:
            self.ghint.configure(text="Všetky hry sú už optimalizované ✔")
            return
        for g in todo:
            self.running.add(g["id"])
            self.set_card(g["id"], "busy")
        threading.Thread(target=lambda: [self.opt_game_thread(g) for g in todo], daemon=True).start()

    def add_game(self):
        p = filedialog.askopenfilename(title="Vyber .exe hry", filetypes=[("Programy", "*.exe")])
        if not p:
            return
        p = os.path.normpath(p)
        gid = "man_" + hashlib.md5(p.lower().encode()).hexdigest()[:8]
        if any(g["id"] == gid for g in self.game_list()):
            return
        self.manual.append({"id": gid, "name": os.path.splitext(os.path.basename(p))[0], "launcher": "Vlastná",
                            "dir": os.path.dirname(p), "exe": p})
        jsave(GAMES, self.manual)
        self.refresh_games()
        self.start_icon_load()

    def remove_game(self, gid):
        self.manual = [g for g in self.manual if g["id"] != gid]
        self.gopt.pop(gid, None)
        jsave(GAMES, self.manual)
        jsave(GOPT, self.gopt)
        self.refresh_games()

    # ---------------- settings tab ----------------
    def build_settings(self):
        self.setv = ctk.CTkFrame(self.container, fg_color="transparent")
        self.setv.grid_columnconfigure(1, weight=1)
        self.setv.grid_rowconfigure(0, weight=1)

        left = self.card(self.setv, width=330)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 16))
        left.grid_propagate(False)
        ctk.CTkLabel(left, text="MOŽNOSTI", font=self.f(13, "bold"), text_color=GOLD).pack(anchor="w", padx=22, pady=(20, 10))
        self.v_close = ctk.BooleanVar(value=self.cfg.get("autoclose", True))
        self.v_restart = ctk.BooleanVar(value=self.cfg.get("restart", False))
        for var, title, desc in ((self.v_close, "Zatvoriť okno po APPLY", "Po dokončení sa appka sama vypne"),
                                 (self.v_restart, "Reštartovať PC po APPLY", "Reštart za 15 sekúnd po dokončení")):
            ctk.CTkSwitch(left, text=title, variable=var, command=self.save_opts, font=self.f(14, "bold"),
                          progress_color=GOLD, button_color=GOLD2, fg_color="#2A2A36").pack(anchor="w", padx=22, pady=(10, 0))
            ctk.CTkLabel(left, text=desc, font=self.f(11), text_color=MUTED).pack(anchor="w", padx=64)
        ctk.CTkButton(left, text="Otvoriť priečinok s dátami", height=38, corner_radius=12, fg_color=CARD2,
                      hover_color="#262633", text_color=TXT, font=self.f(12),
                      command=lambda: os.startfile(DATA)).pack(anchor="w", padx=22, pady=(26, 0))

        right = self.card(self.setv)
        right.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(right, text="PRIDAŤ VLASTNÚ FUNKCIU", font=self.f(13, "bold"), text_color=GOLD).pack(
            anchor="w", padx=22, pady=(20, 8))
        r1 = ctk.CTkFrame(right, fg_color="transparent")
        r1.pack(fill="x", padx=22)
        self.e_name = ctk.CTkEntry(r1, placeholder_text="Názov (napr. Vymazať %temp%)", height=36, fg_color=CARD2,
                                   border_color=LINE, font=self.f(13))
        self.e_name.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.e_desc = ctk.CTkEntry(r1, placeholder_text="Čo robí (nepovinné)", height=36, fg_color=CARD2,
                                   border_color=LINE, font=self.f(13))
        self.e_desc.pack(side="left", fill="x", expand=True)
        r2 = ctk.CTkFrame(right, fg_color="transparent")
        r2.pack(fill="x", padx=22, pady=(8, 0))
        self.type_menu = ctk.CTkOptionMenu(r2, values=list(TYPES), command=self.type_changed, width=230, height=34,
                                           fg_color=CARD2, button_color=GOLD, button_hover_color=GOLD2,
                                           dropdown_fg_color=CARD2, text_color=TXT, font=self.f(12))
        self.type_menu.pack(side="left")
        ctk.CTkButton(r2, text="Vložiť ukážku", width=120, height=34, fg_color="transparent", border_width=1,
                      border_color=LINE, text_color=MUTED, hover_color=CARD2, font=self.f(12),
                      command=self.fill_example).pack(side="left", padx=8)
        self.hint = ctk.CTkLabel(right, text=HINTS["folder"], font=self.f(11), text_color=MUTED,
                                 wraplength=640, justify="left")
        self.hint.pack(anchor="w", padx=22, pady=(8, 4))
        self.code = ctk.CTkTextbox(right, height=95, fg_color=CARD2, border_width=1, border_color=LINE,
                                   font=ctk.CTkFont(family="Consolas", size=12))
        self.code.pack(fill="x", padx=22)
        r3 = ctk.CTkFrame(right, fg_color="transparent")
        r3.pack(fill="x", padx=22, pady=(10, 0))
        ctk.CTkButton(r3, text="PRIDAŤ FUNKCIU", height=40, corner_radius=12, fg_color=GOLD, hover_color=GOLD2,
                      text_color="#0A0A0E", font=self.f(13, "bold"), command=self.add_custom).pack(side="left")
        self.msg = ctk.CTkLabel(r3, text="Kód sa spúšťa s právami správcu – pridávaj len to, čomu rozumieš.",
                                font=self.f(11), text_color=MUTED)
        self.msg.pack(side="left", padx=12)
        ctk.CTkLabel(right, text="TVOJE FUNKCIE", font=self.f(11, "bold"), text_color=MUTED).pack(
            anchor="w", padx=22, pady=(14, 2))
        self.custlist = ctk.CTkScrollableFrame(right, fg_color="transparent", scrollbar_button_color="#2A2A36")
        self.custlist.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.refresh_custom()

    def cur_type(self):
        return TYPES[self.type_menu.get()]

    def type_changed(self, _):
        self.hint.configure(text=HINTS[self.cur_type()])

    def fill_example(self):
        self.code.delete("1.0", "end")
        self.code.insert("1.0", EXAMPLES[self.cur_type()])

    def save_opts(self):
        self.cfg["autoclose"] = bool(self.v_close.get())
        self.cfg["restart"] = bool(self.v_restart.get())
        jsave(CFG, self.cfg)

    def add_custom(self):
        name = self.e_name.get().strip()
        code = self.code.get("1.0", "end").strip()
        if not name or not code:
            self.msg.configure(text="Vyplň názov aj kód.", text_color="#E5736B")
            return
        self.customs.append({"id": uuid.uuid4().hex[:8], "name": name, "desc": self.e_desc.get().strip(),
                             "type": self.cur_type(), "code": code})
        jsave(CUS, self.customs)
        self.e_name.delete(0, "end")
        self.e_desc.delete(0, "end")
        self.code.delete("1.0", "end")
        self.msg.configure(text="Pridané ✔ – nájdeš ju v záložke Optimalizácia.", text_color=GOLD)
        self.refresh_custom()
        self.refresh_list()

    def del_custom(self, cid):
        self.customs = [c for c in self.customs if c["id"] != cid]
        self.vars.pop("c_" + cid, None)
        jsave(CUS, self.customs)
        self.refresh_custom()
        self.refresh_list()

    def refresh_custom(self):
        for w in self.custlist.winfo_children():
            w.destroy()
        if not self.customs:
            ctk.CTkLabel(self.custlist, text="Zatiaľ žiadne vlastné funkcie.", font=self.f(12),
                         text_color=MUTED).pack(anchor="w", padx=12, pady=6)
        for c in self.customs:
            row = ctk.CTkFrame(self.custlist, fg_color=CARD2, corner_radius=12)
            row.pack(fill="x", padx=8, pady=3)
            ctk.CTkLabel(row, text=c["name"], font=self.f(13, "bold"), text_color=TXT).pack(side="left", padx=(14, 8), pady=10)
            ctk.CTkLabel(row, text=TYPE_NAME[c["type"]], font=self.f(11), text_color=MUTED).pack(side="left")
            ctk.CTkButton(row, text="Zmazať", width=80, height=28, fg_color="#3A1D1D", hover_color="#5A2A2A",
                          text_color="#E5736B", font=self.f(12), command=lambda i=c["id"]: self.del_custom(i)
                          ).pack(side="right", padx=10)

    # ---------------- monitor tab ----------------
    def build_monitor(self):
        self.monv = ctk.CTkFrame(self.container, fg_color="transparent")
        card = self.card(self.monv)
        card.pack(fill="both", expand=True)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=22, pady=(20, 0))
        ctk.CTkLabel(top, text="LIVE MONITOR", font=self.f(13, "bold"), text_color=GOLD).pack(side="left")
        ctk.CTkButton(top, text="Uvoľniť RAM", height=34, corner_radius=12, fg_color=GOLD, hover_color=GOLD2,
                      text_color="#0A0A0E", font=self.f(12, "bold"), command=self.mon_free_ram).pack(side="right")
        self.mon_msg = ctk.CTkLabel(top, text="" if psutil else "Chýba knižnica psutil – spusti build.bat znova.",
                                    font=self.f(11), text_color=MUTED)
        self.mon_msg.pack(side="right", padx=12)
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(6, 0))
        self.gauges = {}
        for k, lbl in (("cpu", "CPU"), ("ram", "RAM"), ("gpu", "GPU"), ("disk", "DISK C:")):
            g = Gauge(row, lbl, bg=CARD)
            g.pack(side="left", expand=True)
            self.gauges[k] = g
        self.mon_info = ctk.CTkLabel(card, text="", font=self.f(12), text_color=MUTED)
        self.mon_info.pack(pady=(0, 6))
        ctk.CTkLabel(card, text="JADRÁ CPU", font=self.f(10, "bold"), text_color=GOLD).pack(anchor="w", padx=22)
        self.cores = CoreBars(card, bg=CARD)
        self.cores.pack(fill="x", padx=22, pady=(2, 10))
        ctk.CTkLabel(card, text="NAJVÄČŠIE PROCESY (RAM)", font=self.f(10, "bold"), text_color=GOLD).pack(anchor="w", padx=22)
        pf = ctk.CTkFrame(card, fg_color="transparent")
        pf.pack(fill="x", padx=22, pady=(2, 12))
        self.prow = []
        for i in range(6):
            r = ctk.CTkFrame(pf, fg_color=CARD2, corner_radius=10)
            r.pack(fill="x", pady=2)
            n = ctk.CTkLabel(r, text="", font=self.f(12, "bold"), text_color=TXT, width=240, anchor="w")
            n.pack(side="left", padx=(12, 0), pady=4)
            m = ctk.CTkLabel(r, text="", font=self.f(12), text_color=MUTED)
            m.pack(side="left", padx=12)
            ctk.CTkButton(r, text="Ukončiť", width=70, height=22, fg_color="#3A1D1D", hover_color="#5A2A2A",
                          text_color="#E5736B", font=self.f(11), command=lambda i=i: self.kill_proc(i)
                          ).pack(side="right", padx=8)
            self.prow.append((n, m))

    def mon_start(self):
        if self.mon_running or not psutil:
            return
        self.mon_running = True
        self.mon_n = 0
        psutil.cpu_percent(None)
        psutil.cpu_percent(percpu=True)
        self.mon_last_net = psutil.net_io_counters()
        self.mon_last_disk = psutil.disk_io_counters()
        self.mon_last_t = time.time()
        if not self.gpu_alive:
            self.gpu_alive = True
            threading.Thread(target=self.gpu_loop, daemon=True).start()
        self.after(400, self.mon_tick)

    def gpu_loop(self):
        try:
            while self.mon_running:
                self.gpu = gpu_sample()
                time.sleep(2.5)
        finally:
            self.gpu_alive = False

    def mon_tick(self):
        if self.cur_tab != "mon":
            self.mon_running = False
            return
        try:
            now = time.time()
            dt = max(0.2, now - self.mon_last_t)
            self.mon_last_t = now
            cpu = psutil.cpu_percent(None)
            per = psutil.cpu_percent(percpu=True)
            vm = psutil.virtual_memory()
            nio, dio = psutil.net_io_counters(), psutil.disk_io_counters()
            down = (nio.bytes_recv - self.mon_last_net.bytes_recv) / dt
            up = (nio.bytes_sent - self.mon_last_net.bytes_sent) / dt
            rd = wr = 0
            if dio and self.mon_last_disk:
                rd = (dio.read_bytes - self.mon_last_disk.read_bytes) / dt
                wr = (dio.write_bytes - self.mon_last_disk.write_bytes) / dt
            self.mon_last_net, self.mon_last_disk = nio, dio
            fq = psutil.cpu_freq()
            self.gauges["cpu"].set(cpu, f"{cpu:.0f}%", f"{fq.current / 1000:.1f} GHz" if fq else "")
            self.gauges["ram"].set(vm.percent, f"{vm.percent:.0f}%", f"{vm.used / 2**30:.1f} / {vm.total / 2**30:.0f} GB")
            gp = self.gpu
            if gp:
                self.gauges["gpu"].set(gp["util"], f"{gp['util']:.0f}%", f"{gp['temp']} °C" if gp.get("temp") else "")
            else:
                self.gauges["gpu"].set(None, "N/A", "")
            du = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
            self.gauges["disk"].set(du.percent, f"{du.percent:.0f}%", f"{du.free / 2**30:.0f} GB voľných")
            self.mon_info.configure(text=f"↓ {fmt_rate(down)}    ↑ {fmt_rate(up)}    •    disk čítanie {fmt_rate(rd)}    zápis {fmt_rate(wr)}")
            self.cores.set(per)
            if self.mon_n % 3 == 0:
                procs = []
                for p in psutil.process_iter(["pid", "name", "memory_info"]):
                    mi = p.info.get("memory_info")
                    if mi:
                        procs.append((mi.rss, p.info.get("name") or "?", p.info["pid"]))
                procs.sort(reverse=True)
                for i, (n, m) in enumerate(self.prow):
                    if i < len(procs):
                        rss, name, pid = procs[i]
                        n.configure(text=name)
                        m.configure(text=f"{rss / 1048576:.0f} MB")
                        self.proc_info[i] = (pid, name)
            self.mon_n += 1
        except Exception:
            pass
        self.after(1000, self.mon_tick)

    def kill_proc(self, i):
        info = self.proc_info[i]
        if not info:
            return
        pid, name = info
        if name.lower() in PROTECTED or pid == os.getpid():
            self.mon_msg.configure(text=f"{name} je chránený proces.", text_color="#E5736B")
            return
        if messagebox.askyesno(APP, f"Ukončiť proces {name}?\nNeuložená práca v ňom sa stratí."):
            try:
                psutil.Process(pid).terminate()
                self.mon_msg.configure(text=f"✔ {name} ukončený", text_color=GOLD)
            except Exception as e:
                self.mon_msg.configure(text=f"✖ {str(e)[:60]}", text_color="#E5736B")

    def mon_free_ram(self):
        if not psutil:
            return
        self.mon_msg.configure(text="Uvoľňujem…", text_color=GOLD2)

        def work():
            try:
                n = free_ram()
                self.ui(lambda: self.mon_msg.configure(text=f"✔ uvoľnených ~{n} MB", text_color=GOLD))
            except Exception as e:
                self.ui(lambda: self.mon_msg.configure(text=f"✖ {str(e)[:60]}", text_color="#E5736B"))
        threading.Thread(target=work, daemon=True).start()

    # ---------------- tools tab ----------------
    def build_tools(self):
        self.toolv = ctk.CTkFrame(self.container, fg_color="transparent")
        self.toolv.grid_columnconfigure(0, weight=1, uniform="t")
        self.toolv.grid_columnconfigure(1, weight=1, uniform="t")
        self.toolv.grid_rowconfigure(0, weight=1)
        left = self.card(self.toolv)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        ctk.CTkLabel(left, text="PROFI NÁSTROJE", font=self.f(13, "bold"), text_color=GOLD).pack(
            anchor="w", padx=22, pady=(20, 4))
        sc = ctk.CTkScrollableFrame(left, fg_color="transparent", scrollbar_button_color="#2A2A36")
        sc.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.tool_btns, self.tool_res = {}, {}
        for tid, title, desc, _ in TOOLS:
            row = ctk.CTkFrame(sc, fg_color=CARD2, corner_radius=12)
            row.pack(fill="x", padx=8, pady=4)
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=title, font=self.f(14, "bold"), text_color=TXT, anchor="w").grid(
                row=0, column=0, sticky="w", padx=16, pady=(10, 0))
            ctk.CTkLabel(row, text=desc, font=self.f(11), text_color=MUTED, anchor="w", justify="left",
                         wraplength=290).grid(row=1, column=0, sticky="w", padx=16)
            r = ctk.CTkLabel(row, text="", font=self.f(11), text_color=GOLD, anchor="w", justify="left",
                             wraplength=290)
            r.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 10))
            b = ctk.CTkButton(row, text="SPUSTIŤ", width=90, height=32, corner_radius=10, fg_color=GOLD,
                              hover_color=GOLD2, text_color="#0A0A0E", font=self.f(12, "bold"),
                              command=lambda t=tid: self.run_tool(t))
            b.grid(row=0, column=1, rowspan=3, padx=14)
            self.tool_btns[tid], self.tool_res[tid] = b, r

        right = self.card(self.toolv)
        right.grid(row=0, column=1, sticky="nsew")
        top = ctk.CTkFrame(right, fg_color="transparent")
        top.pack(fill="x", padx=22, pady=(20, 0))
        ctk.CTkLabel(top, text="SPÚŠŤANIE WINDOWSU", font=self.f(13, "bold"), text_color=GOLD).pack(side="left")
        self.stcount = ctk.CTkLabel(top, text="", font=self.f(11), text_color=MUTED)
        self.stcount.pack(side="right")
        ctk.CTkLabel(right, text="Vypni aplikácie, ktoré sa zbytočne spúšťajú so systémom (zrýchli štart PC).",
                     font=self.f(11), text_color=MUTED, wraplength=430, justify="left").pack(anchor="w", padx=22, pady=(2, 4))
        self.stlist = ctk.CTkScrollableFrame(right, fg_color="transparent", scrollbar_button_color="#2A2A36")
        self.stlist.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def run_tool(self, tid):
        t = next(x for x in TOOLS if x[0] == tid)
        b, r = self.tool_btns[tid], self.tool_res[tid]
        b.configure(state="disabled", text="…")
        r.configure(text="Beží…", text_color=GOLD2)

        def work():
            try:
                out, ok = t[3]() or "hotovo", True
            except Exception as e:
                out, ok = str(e)[:120], False

            def done():
                b.configure(state="normal", text="SPUSTIŤ")
                r.configure(text=("✔ " if ok else "✖ ") + out, text_color=GOLD if ok else "#E5736B")
            self.ui(done)
        threading.Thread(target=work, daemon=True).start()

    def refresh_startup(self):
        for w in self.stlist.winfo_children():
            w.destroy()
        try:
            items = list_startup()
        except Exception:
            items = []
        self.stcount.configure(text=f"{len(items)} položiek")
        if not items:
            ctk.CTkLabel(self.stlist, text="Žiadne spúšťané aplikácie.", font=self.f(12),
                         text_color=MUTED).pack(anchor="w", padx=12, pady=8)
        for it in items:
            row = ctk.CTkFrame(self.stlist, fg_color=CARD2, corner_radius=12)
            row.pack(fill="x", padx=8, pady=3)
            var = ctk.BooleanVar(value=it["enabled"])
            ctk.CTkSwitch(row, text=it["name"], variable=var, font=self.f(13, "bold"), text_color=TXT,
                          progress_color=GOLD, button_color=GOLD2, fg_color="#2A2A36",
                          command=lambda it=it, v=var: self.toggle_startup(it, v)).pack(anchor="w", padx=16, pady=(10, 0))
            ctk.CTkLabel(row, text=f"{it['src']}  •  {it['cmd'][:60]}", font=self.f(10),
                         text_color=MUTED).pack(anchor="w", padx=58, pady=(0, 10))

    def toggle_startup(self, it, var):
        en = bool(var.get())
        try:
            reg(it["hive"], STARTUP_APPROVED % it["sub"], it["name"], bytes([2 if en else 3] + [0] * 11), winreg.REG_BINARY)
        except Exception:
            var.set(not en)

    # ---------------- thread-safe helpers ----------------
    def ui(self, fn):
        self.after(0, fn)

    def log(self, t):
        def _():
            self.logbox.configure(state="normal")
            self.logbox.insert("end", t + "\n")
            self.logbox.see("end")
            self.logbox.configure(state="disabled")
        self.ui(_)

    def set_status(self, t):
        self.ui(lambda: self.status.configure(text=t))

    def set_prog(self, v):
        self.ui(lambda: self.bar.set(v))

    # ---------------- actions ----------------
    def apply(self):
        if self.busy:
            return
        allt = self.all_tweaks()
        sel = [t for t in allt if self.vars[t[0]].get()]
        if not sel:
            self.status.configure(text="Nič nie je vybrané.")
            return
        self.cfg["selected"] = {t[0]: bool(self.vars[t[0]].get()) for t in allt}
        jsave(CFG, self.cfg)
        self.busy = True
        self.go.configure(state="disabled", text="OPTIMALIZUJEM…")
        threading.Thread(target=self.worker, args=(sel,), daemon=True).start()

    def worker(self, sel):
        self.set_status("Vytváram bod obnovenia…")
        run("Enable-ComputerRestore -Drive 'C:\\'; Checkpoint-Computer -Description 'RAZESE Optimizer' "
            "-RestorePointType MODIFY_SETTINGS", ps=True)
        self.log("Bod obnovenia: pokus dokončený.")
        for i, (_, _, title, _, fn, _) in enumerate(sel):
            self.set_status(title + "…")
            try:
                r = fn()
                self.log("✔ " + title + (f"  ({r})" if r else ""))
            except Exception as e:
                self.log(f"✖ {title}: {e}")
            self.set_prog((i + 1) / len(sel))
        if {"power", "cpu", "gpu"} <= {t[0] for t in sel}:
            self.cfg["gaming_base"] = True
            jsave(CFG, self.cfg)
        self.ui(self.finish)

    def finish(self):
        if self.cfg.get("restart"):
            run(["shutdown", "/r", "/t", "15", "/c", "RAZESE Optimizer: reštart na dokončenie optimalizácie"])
            self.status.configure(text="Hotovo ✔ – PC sa reštartuje za 15 sekúnd")
        else:
            self.status.configure(text="Hotovo ✔ – niektoré zmeny sa prejavia po reštarte")
        if self.cfg.get("autoclose", True):
            self.after(2200, self.destroy)
        else:
            self.busy = False
            self.go.configure(state="normal", text="APPLY")

    def undo(self):
        if self.busy:
            return
        extra = revert_regs()
        if "_idle" in extra:
            run(["powercfg", "-setacvalueindex", "SCHEME_CURRENT", "54533251-82be-4824-96c1-47b60b740d00",
                 "5d76a2ca-e8c0-402f-a133-2158492d58ad", "0"])
        run(["powercfg", "-setactive", "381b4222-f694-41f0-9685-ff5bb260df2e"])
        if extra.get("_hib"):
            run(["powercfg", "-h", "on"])
        if "_lastaccess" in extra:
            run(["fsutil", "behavior", "set", "disablelastaccess", "2"])
        if "_tasks" in extra:
            for tn in BLOAT_TASKS:
                run(["schtasks", "/Change", "/TN", tn, "/Enable"])
        if "_bcd" in extra:
            run(["bcdedit", "/deletevalue", "disabledynamictick"])
        if "_nicpm" in extra:
            run("Get-NetAdapter -Physical | ForEach-Object { Enable-NetAdapterPowerManagement -Name $_.Name "
                "-ErrorAction SilentlyContinue }", ps=True)
        if "_nicadv" in extra:
            nic_adv_reset()
        if "_tcp" in extra:
            run(["netsh", "int", "tcp", "set", "global", "rsc=enabled"])
            run(["netsh", "int", "tcp", "set", "heuristics", "enabled"])
        if "_dns" in extra:
            run("Get-NetAdapter -Physical | ForEach-Object { Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex "
                "-ResetServerAddresses }", ps=True)
        self.gopt = {}
        jsave(GOPT, self.gopt)
        self.cfg["gaming_base"] = False
        jsave(CFG, self.cfg)
        self.refresh_games()
        self.bar.set(0)
        self.log("↩ Zmeny vrátené späť, aj optimalizácie hier (vlastné funkcie a čistenie sa vrátiť nedajú). Reštartuj PC.")
        self.status.configure(text="Zmeny vrátené")


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


if __name__ == "__main__":
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(f'"{a}"' for a in sys.argv), None, 1)
        sys.exit()
    App().mainloop()
