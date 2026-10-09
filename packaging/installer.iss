; Inno Setup script for the Windows installer.
; Compile with `python scripts/build_windows.py --installer`, which passes the
; version. Installs for the current user, so it needs no administrator rights.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1F2B0E-4D0A-4E57-9E0C-6B7D1E5A9F31}
AppName=Helyosfer
AppVersion={#AppVersion}
AppPublisher=Helyosfer
AppPublisherURL=https://github.com/Helyosfer/helyosfer-app
DefaultDirName={autopf}\Helyosfer
DefaultGroupName=Helyosfer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\LICENSE
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\Helyosfer.exe
OutputDir=..\dist
OutputBaseFilename=Helyosfer-{#AppVersion}-setup
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
Source: "..\dist\Helyosfer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Helyosfer"; Filename: "{app}\Helyosfer.exe"
Name: "{autodesktop}\Helyosfer"; Filename: "{app}\Helyosfer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Helyosfer.exe"; Description: "{cm:LaunchProgram,Helyosfer}"; Flags: nowait postinstall skipifsilent

; Uninstalling removes the program only. Records, the encryption key and
; settings live in the user's profile and are left where they are.
