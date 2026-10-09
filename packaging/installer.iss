; Inno Setup script for the Windows installer.
; Compile with `python scripts/build_windows.py --installer`, which passes the
; version. It installs for the current user, so it needs no administrator
; rights, and it installs nothing but the package: the package carries its
; own Python, so the computer does not need one.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; The identity upgrades are matched by. It must never change.
AppId={{6C1F2B0E-4D0A-4E57-9E0C-6B7D1E5A9F31}
AppName=Helyosfer
AppVersion={#AppVersion}
AppVerName=Helyosfer {#AppVersion}
AppPublisher=Helyosfer
AppPublisherURL=https://github.com/Helyosfer/helyosfer-app
AppSupportURL=https://github.com/Helyosfer/helyosfer-app/issues
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Helyosfer
VersionInfoDescription=Helyosfer Setup
DefaultDirName={autopf}\Helyosfer
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
MinVersion=10.0
ShowLanguageDialog=auto
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\Helyosfer.exe
UninstallDisplayName=Helyosfer
OutputDir=..\dist
OutputBaseFilename=Helyosfer-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; An upgrade replaces the program whole. A library the new version no longer
; ships must not be left behind for it to find.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Helyosfer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Helyosfer"; Filename: "{app}\Helyosfer.exe"
Name: "{autodesktop}\Helyosfer"; Filename: "{app}\Helyosfer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Helyosfer.exe"; Description: "{cm:LaunchProgram,Helyosfer}"; Flags: nowait postinstall skipifsilent

; Uninstalling removes the program only. Records, the encryption key and
; settings live in the user's profile and are left where they are.
