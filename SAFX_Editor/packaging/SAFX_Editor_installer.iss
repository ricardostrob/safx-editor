; Instalador Windows (Inno Setup 6+) — assistente gráfico, sem terminal.
; Pré-requisito: compilar com PyInstaller (pasta dist\SAFX_Editor).
; Compilar este script: iscc SAFX_Editor_installer.iss

#define MyAppName "SAFX Editor"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Adejo Tecnologia / TecTex"
#define MyAppExeName "SAFX_Editor.exe"

[Setup]
AppId={{E2B8F4A1-9C0D-4E5F-8A7B-6D5C4B3A2910}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\release
OutputBaseFilename=SAFX_Editor_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
; Artefactos gerados por: python packaging/branding/build_assets.py --inno-only
WizardImageFile=branding\wizard_large.bmp
WizardSmallImageFile=branding\wizard_small.bmp
SetupIconFile=branding\setup.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\SAFX_Editor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
begin
  if not DirExists(ExpandConstant('{src}\..\dist\SAFX_Editor')) then
  begin
    MsgBox('Pasta dist\SAFX_Editor não encontrada.'#13#10'Execute antes o PyInstaller (build_windows.ps1).', mbError, MB_OK);
    Result := False;
  end
  else
    Result := True;
end;
