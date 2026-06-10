; Inno Setup script for the eID Agent tray application.
; Compile from the repository root after the PyInstaller build:
;   ISCC.exe /DMyAppVersion=<version> packaging\eid-agent.iss

#ifndef MyAppVersion
  #define MyAppVersion "1.1.0"
#endif
#define MyAppName "eID Agent"
#define MyAppExeName "eid-agent-tray.exe"
#define MyAppPublisher "EICA"

[Setup]
AppId={{1B6C2D8E-4A57-4D8B-9C1E-7F3A25C40D96}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=output
OutputBaseFilename=eid-agent-setup-{#MyAppVersion}
SetupIconFile=eid-agent.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Lancer {#MyAppName} à l'ouverture de session Windows"; GroupDescription: "Démarrage automatique :"

[Files]
Source: "..\dist\eid-agent-tray\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; \
  Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop the running tray instance before removing files.
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#MyAppExeName} /F"; \
  Flags: runhidden; RunOnceId: "StopTray"
