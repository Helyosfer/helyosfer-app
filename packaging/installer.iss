; Inno Setup script for the Windows installer.
; Compile with `python scripts/build_windows.py --installer`, which passes the
; version. Installs for the current user, so it needs no administrator rights.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1F2B0E-4D0A-4E57-9E0C-6B7D1E5A9F31}
AppName=Helysofer
AppVersion={#AppVersion}
AppPublisher=Helysofer
AppPublisherURL=https://github.com/Helysofer/helysofer
DefaultDirName={autopf}\Helysofer
DefaultGroupName=Helysofer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\LICENSE
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\Helysofer.exe
OutputDir=..\dist
OutputBaseFilename=Helysofer-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Helysofer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Helysofer"; Filename: "{app}\Helysofer.exe"
Name: "{autodesktop}\Helysofer"; Filename: "{app}\Helysofer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Helysofer.exe"; Description: "{cm:LaunchProgram,Helysofer}"; Flags: nowait postinstall skipifsilent

; Uninstalling removes the program only. Records, the encryption key and
; settings live in the user's profile and are left where they are.
