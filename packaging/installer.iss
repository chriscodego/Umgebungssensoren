; Inno Setup script for the Umgebungssensoren Control Panel — requires Inno Setup 6.3 or newer.
;
; This file is UTF-8 *with BOM* on purpose. Without the BOM Inno Setup 6 reads the
; script in the ANSI code page and turns "Universität" into mojibake.
;
; Build the PyInstaller bundle first, then:
;   iscc /DAppVersion=0.1.0 /DAppVersionNumeric=0.1.0.0 packaging\installer.iss
; or simply: python packaging/build.py
;
; Output: dist\installer\UmgebungssensorenPanel-Setup-<version>.exe

#define AppName "Umgebungssensoren Control Panel"
; Stable product GUID for the Umgebungssensoren Control Panel (created 2026-10-02, PROJ-9).
; NEVER change it across releases: a new GUID makes Windows treat the next release as a
; separate product and leaves the old installation standing next to it.
#define AppId "{{918D6EB2-1FCC-4E91-85C0-5A5CFCD0C4F3}"
#define AppPublisher "Universität Paderborn"
#define AppExeName "UmgebungssensorenPanel.exe"

; Where the application keeps its writable state (measurement database, logs). Never part
; of [Files], never removed. Mirrors umwelt_panel.config.data_dir() =
; platformdirs.user_data_path("Umgebungssensoren", appauthor=False, roaming=False).
#define UserDataDir "{localappdata}\Umgebungssensoren"

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#ifndef AppVersionNumeric
  ; VersionInfoVersion only accepts digits. build.py always passes the four-part number
  ; explicitly; this fallback only covers a manual iscc run on a plain X.Y.Z version.
  #define AppVersionNumeric AppVersion + ".0"
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersionNumeric}
VersionInfoProductVersion={#AppVersionNumeric}

; Per-user installation: {userpf} is %LOCALAPPDATA%\Programs, the only program
; location a user without admin rights may write to. PrivilegesRequired=lowest means
; no UAC prompt at all, and PrivilegesRequiredOverridesAllowed stays unset so that no
; "install for all users?" dialog can appear either.
PrivilegesRequired=lowest
DefaultDirName={userpf}\{#AppName}
UsePreviousAppDir=yes
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile=app.ico

OutputDir=..\dist\installer
OutputBaseFilename=UmgebungssensorenPanel-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; The application does not create a named mutex, so AppMutex would never fire. The
; Restart Manager instead spots the running UmgebungssensorenPanel.exe through its locked
; files and asks the user to close it. *.pyd is added to the default filter because a
; running PyInstaller bundle locks its extension modules as well.
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no

; German unless the user passes /LANG=english — no language dialog, no guessing from
; the system locale.
ShowLanguageDialog=no
LanguageDetectionMethod=none

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
german.UserDataKept=Ihre Daten wurden nicht gelöscht.%n%nMesswert-Datenbank, Einstellungen und Logdateien liegen weiterhin unter:%n%n%1%n%nWenn Sie diese Daten endgültig entfernen möchten, löschen Sie diesen Ordner von Hand.
english.UserDataKept=Your data has not been deleted.%n%nThe measurement database, settings and log files remain in:%n%n%1%n%nDelete this folder manually if you want to remove them for good.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole PyInstaller one-dir bundle. Nothing outside {app} is ever touched, which is
; what keeps the user data directory safe across updates and uninstalls.
Source: "..\dist\UmgebungssensorenPanel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only the (then empty) program directory — no user data is involved.
Type: dirifempty; Name: "{app}\_internal"
Type: dirifempty; Name: "{app}"

[Code]

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  { User data survives the uninstall by design — the measurement history is worth more
    than a few megabytes of leftovers. Tell the user where it is so they can decide. }
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
  begin
    DataDir := ExpandConstant('{#UserDataDir}');
    if DirExists(DataDir) then
      MsgBox(FmtMessage(CustomMessage('UserDataKept'), [DataDir]), mbInformation, MB_OK);
  end;
end;
