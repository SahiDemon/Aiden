; ============================================================
; Aiden NSIS custom install / uninstall hooks
; ============================================================
; Install   - registers Aiden.exe for auto-start on login
;           - creates aiden.cmd in the backend folder
;           - appends the backend folder to the user PATH
; Uninstall - removes the auto-start entry
;           - removes the backend folder from user PATH
;           - deletes aiden.cmd
; ============================================================

; Backend folder inside the installed app (set by electron-builder)
; $INSTDIR = Electron app root  e.g. C:\Users\<user>\AppData\Local\Programs\Aiden
!define BACKEND_DIR "$INSTDIR\resources\backend\Aiden"
!define AIDEN_EXE   "${BACKEND_DIR}\Aiden.exe"
!define AIDEN_CMD   "${BACKEND_DIR}\aiden.cmd"

; ── Install ──────────────────────────────────────────────────────────────────
!macro customInstall

  ; 1. Register Aiden.exe to auto-start with Windows (current user)
  WriteRegStr HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Run" \
    "Aiden" \
    "${AIDEN_EXE}"

  ; 2. Write aiden.cmd so typing 'aiden' in PowerShell runs Aiden.exe --debug
  ;    (AttachConsole(-1) in main.py pipes output to the existing terminal)
  FileOpen  $0 "${AIDEN_CMD}" w
  FileWrite $0 "@echo off$\r$\n"
  FileWrite $0 '"${AIDEN_EXE}" --debug %*$\r$\n'
  FileClose $0

  ; 3. Add backend folder to the current-user PATH
  ;    Read current value → check if already present → append if not.
  ReadRegStr $R0 HKCU "Environment" "Path"

  ; Search for our dir inside the current PATH string
  StrLen $R1 "${BACKEND_DIR}"
  StrLen $R2 "$R0"
  IntOp  $R3 $R2 - $R1       ; max start index to scan
  StrCpy $R4 "0"              ; found flag

  scan_loop:
    IntCmp $R4 $R3 scan_done scan_done scan_past_end
    StrCpy $R5 "$R0" $R1 $R4  ; substring of length R1 starting at R4
    StrCmp $R5 "${BACKEND_DIR}" 0 next_char
      StrCpy $R4 "1"           ; mark found
      Goto scan_done
    next_char:
      IntOp $R4 $R4 + 1
      Goto scan_loop
  scan_past_end:
    StrCpy $R4 "0"             ; not found
  scan_done:

  ; R4 == "1"  →  already in PATH, skip
  ; R4 == "0"  →  append
  StrCmp $R4 "1" path_already_set
    StrCpy $R0 "$R0;${BACKEND_DIR}"
    WriteRegExpandStr HKCU "Environment" "Path" "$R0"
    ; Notify running processes of the change
    SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=2000
  path_already_set:

!macroend

; ── Uninstall ────────────────────────────────────────────────────────────────
!macro customUnInstall

  ; 1. Remove auto-start registry entry
  DeleteRegValue HKCU \
    "Software\Microsoft\Windows\CurrentVersion\Run" \
    "Aiden"

  ; 2. Delete aiden.cmd
  Delete "${AIDEN_CMD}"

  ; 3. Remove the backend folder from the user PATH
  ;    Strategy: rebuild PATH by copying all segments that are NOT our dir.
  ReadRegStr $R0 HKCU "Environment" "Path"
  StrCpy $R6 ""          ; rebuilt PATH
  StrCpy $R7 "$R0;"      ; work on a semicolon-terminated copy

  strip_loop:
    StrLen $R8 "$R7"
    IntCmp $R8 0 strip_done strip_done 0
    ; Find next semicolon
    StrCpy $R9 "0"
    find_semi:
      StrCpy $R1 "$R7" 1 $R9
      StrCmp $R1 ";" found_semi
      StrCmp $R1 "" strip_done
      IntOp $R9 $R9 + 1
      Goto find_semi
    found_semi:
      ; Extract segment [0..R9)
      StrCpy $R2 "$R7" $R9
      ; Advance past the semicolon
      IntOp  $R3 $R9 + 1
      StrCpy $R7 "$R7" "" $R3
      ; Skip if this segment is our dir
      StrCmp $R2 "${BACKEND_DIR}" strip_loop
      ; Append separator if needed
      StrLen $R4 "$R6"
      IntCmp $R4 0 0 0 add_semi
        StrCpy $R6 "$R2"
        Goto strip_loop
      add_semi:
        StrCpy $R6 "$R6;$R2"
        Goto strip_loop
  strip_done:

  WriteRegExpandStr HKCU "Environment" "Path" "$R6"
  SendMessage ${HWND_BROADCAST} ${WM_WININICHANGE} 0 "STR:Environment" /TIMEOUT=2000

!macroend
