; Instalador de ListaCD (Inno Setup 6). Uso: iscc /DMyAppVersion=2.0.0 installer\ListaCD.iss
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{6F0E3E7B-6B44-4E0B-9C0B-6C1C5D0A2C11}
AppName=ListaCD
AppVersion={#MyAppVersion}
AppPublisher=ListaCD
DefaultDirName={autopf}\ListaCD
DefaultGroupName=ListaCD
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=ListaCD-Setup-{#MyAppVersion}
SetupIconFile=..\assets\listacd.ico
UninstallDisplayIcon={app}\ListaCD.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\ListaCD\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ListaCD"; Filename: "{app}\ListaCD.exe"
Name: "{autodesktop}\ListaCD"; Filename: "{app}\ListaCD.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ListaCD.exe"; Description: "{cm:LaunchProgram,ListaCD}"; Flags: nowait postinstall skipifsilent
