/*
 * Prometheus.exe — the double-click way to start Prometheus on Windows.
 *
 * It's a small launcher, not the whole app frozen into one file: the app
 * stays as Python in app\ (fast to start, easy to update and develop).
 *
 * Step 1: find app\ next to this exe
 * Step 2: pick Python —
 *           app\runtime\python\pythonw.exe   (the folder's own, from make_portable)
 *           pythonw.exe on this computer     (no black console window)
 *           python.exe / py.exe              (console hidden)
 * Step 3: start  <python> main.py  in app\, passing any arguments on
 * Step 4: if it stops with an error in the first few seconds (packages not
 *         installed yet, say), explain what to do instead of vanishing
 *
 * Built by app\tools\build_exe.py (MinGW): it also puts the icon in.
 */

#define WIN32_LEAN_AND_MEAN
#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>

#define BIG 4096

static int exists(const wchar_t *path) {
    return GetFileAttributesW(path) != INVALID_FILE_ATTRIBUTES;
}

/* Full path of an exe on PATH, or 0. (A Store "install Python" stub that
   isn't backed by a real Python exits at once — Step 4 then explains.) */
static int on_path(const wchar_t *name, wchar_t *out) {
    wchar_t *part;
    return SearchPathW(NULL, name, NULL, BIG, out, &part) != 0;
}

static void tell(const wchar_t *text) {
    MessageBoxW(NULL, text, L"Prometheus", MB_OK | MB_ICONINFORMATION);
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR args, int show) {
    (void)inst; (void)prev; (void)show;
    wchar_t here[BIG], app[BIG], python[BIG], cmd[BIG];
    DWORD flags = 0;

    /* Step 1 */
    GetModuleFileNameW(NULL, here, BIG);
    wchar_t *slash = wcsrchr(here, L'\\');
    if (slash) *slash = 0;
    _snwprintf(app, BIG, L"%s\\app", here);
    wchar_t main_py[BIG];
    _snwprintf(main_py, BIG, L"%s\\main.py", app);
    if (!exists(main_py)) {
        /* Also works if the exe is put inside app\ itself */
        _snwprintf(main_py, BIG, L"%s\\main.py", here);
        if (!exists(main_py)) {
            tell(L"Prometheus.exe needs its app folder next to it.\n\n"
                 L"Keep Prometheus.exe and the app folder together when you copy them.");
            return 1;
        }
        _snwprintf(app, BIG, L"%s", here);
    }

    /* Step 2 */
    wchar_t own[BIG], own_pkgs[BIG];
    _snwprintf(own, BIG, L"%s\\runtime\\python\\pythonw.exe", app);
    _snwprintf(own_pkgs, BIG, L"%s\\runtime\\python\\Lib\\site-packages\\PySide6", app);
    if (exists(own) && exists(own_pkgs)) {
        _snwprintf(python, BIG, L"%s", own);
    } else if (on_path(L"pythonw.exe", python)) {
        /* nothing else to do */
    } else if (on_path(L"python.exe", python) || on_path(L"py.exe", python)) {
        flags = CREATE_NO_WINDOW;
    } else {
        tell(L"Prometheus needs Python, and it isn't on this computer yet.\n\n"
             L"Open the app folder and double-click setup.bat — it walks you through it.");
        ShellExecuteW(NULL, L"open", app, NULL, NULL, SW_SHOWNORMAL);
        return 1;
    }

    /* Step 3 */
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");
    _snwprintf(cmd, BIG, L"\"%s\" main.py %s", python, args ? args : L"");
    STARTUPINFOW si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(NULL, cmd, NULL, NULL, FALSE, flags, NULL, app, &si, &pi)) {
        tell(L"Prometheus couldn't start Python.\n\n"
             L"Open the app folder and double-click debug_run.bat to see why.");
        return 1;
    }

    /* Step 4: still running after 8 s = the window is up (or on its way) */
    DWORD code = 0;
    if (WaitForSingleObject(pi.hProcess, 8000) == WAIT_OBJECT_0 &&
        GetExitCodeProcess(pi.hProcess, &code) && code != 0) {
        tell(L"Prometheus stopped while starting.\n\n"
             L"If this is the first run on this computer, open the app folder and "
             L"double-click setup.bat.\n\nOtherwise double-click debug_run.bat there "
             L"to see what went wrong.");
        ShellExecuteW(NULL, L"open", app, NULL, NULL, SW_SHOWNORMAL);
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return (int)code;
}
