; ============================================================
; AvitoHunter — Профессиональный скрипт Inno Setup 7
; Максимальное ультра-сжатие (LZMA2 Ultra64 Solid)
; Фирменный стиль AvitoHunter, иконки, ярлыки, выбор пути
; ============================================================

#define MyAppName "AvitoHunter"
#define MyAppVersion "1.17"
#define MyAppPublisher "AvitoHunter Team"
#define MyAppURL "https://avitohunter.local"
#define MyAppExeName "gateway.py"
#define SourceAppDir SourcePath + "\app"
#define ResDir SourcePath + "\installer_res"

[Setup]
AppId={{8B19C34A-4D78-4A1B-9472-E7A9C4C61F12}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Путь установки по умолчанию: C:\Program Files (x86)\AvitoHunter
DefaultDirName={commonpf32}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=no

; Выходной файл инсталлятора
OutputDir={#SourcePath}
OutputBaseFilename=AvitoHunter_Setup

SetupIconFile={#ResDir}\skybase.ico
UninstallDisplayIcon={app}\img\skybase.ico

; Графика и оформление мастера в стиле сайта SkyBase
WizardStyle=modern
WizardImageFile={#ResDir}\wizard_large.bmp
WizardSmallImageFile={#ResDir}\wizard_small.bmp

; Максимальное ультра-сжатие
Compression=lzma2/ultra
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=2

; Права администратора для корректной установки и выдачи прав записи в Program Files
PrivilegesRequired=admin

; Чистый и аккуратный мастер
DisableWelcomePage=no
DisableDirPage=no
AlwaysShowComponentsList=yes
DisableFinishedPage=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Dirs]
; Выдаем полные права пользователям на папку программы для записи баз, настроек и логов
Name: "{app}"; Permissions: users-full
Name: "{app}\data"; Permissions: users-full
Name: "{app}\avito_bot"; Permissions: users-full

[Types]
Name: "full"; Description: "Полная установка (рекомендуется)"
Name: "custom"; Description: "Выборочная установка"; Flags: iscustom

[Components]
Name: "core"; Description: "Программа AvitoHunter (основные модули и веб-интерфейс)"; Types: full custom
Name: "python"; Description: "Автономная среда выполнения Python 3.11 и библиотеки"; Types: full custom

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные ярлыки:"; Flags: checkedonce

[Files]
; Файлы встроенного Python 3.11
Source: "{#SourceAppDir}\python.exe"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\pythonw.exe"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\python3.dll"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\python311.dll"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\python311.zip"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\python311._pth"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\python.cat"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\vcruntime140*.dll"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\lib*.dll"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\sqlite3.dll"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\_*.pyd"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\pyexpat.pyd"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\select.pyd"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\unicodedata.pyd"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\winsound.pyd"; DestDir: "{app}"; Flags: ignoreversion; Components: python; Permissions: users-full
Source: "{#SourceAppDir}\Lib\*"; DestDir: "{app}\Lib"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: python; Permissions: users-full

; Основные компоненты AvitoHunter
Source: "{#SourceAppDir}\*.py"; DestDir: "{app}"; Flags: ignoreversion; Components: core; Permissions: users-full
Source: "{#SourceAppDir}\*.pyd"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist; Components: core; Permissions: users-full; Excludes: "_*.pyd,pyexpat.pyd,select.pyd,unicodedata.pyd,winsound.pyd"
Source: "{#SourceAppDir}\*.bat"; DestDir: "{app}"; Flags: ignoreversion; Components: core; Permissions: users-full
Source: "{#SourceAppDir}\index.html"; DestDir: "{app}"; Flags: ignoreversion; Components: core; Permissions: users-full
Source: "{#SourceAppDir}\favicon.ico"; DestDir: "{app}"; Flags: ignoreversion; Components: core; Permissions: users-full
Source: "{#SourceAppDir}\manifest.json"; DestDir: "{app}"; Flags: ignoreversion; Components: core; Permissions: users-full
Source: "{#SourceAppDir}\sw.js"; DestDir: "{app}"; Flags: ignoreversion; Components: core; Permissions: users-full
Source: "{#SourceAppDir}\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion; Components: core; Permissions: users-full
Source: "{#SourceAppDir}\js\*"; DestDir: "{app}\js"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: core; Permissions: users-full
Source: "{#SourceAppDir}\css\*"; DestDir: "{app}\css"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: core; Permissions: users-full
Source: "{#SourceAppDir}\img\*"; DestDir: "{app}\img"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: core; Permissions: users-full
Source: "{#SourceAppDir}\sound\*"; DestDir: "{app}\sound"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: core; Permissions: users-full
Source: "{#SourceAppDir}\avito_bot\*"; DestDir: "{app}\avito_bot"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: core; Permissions: users-full
Source: "{#SourceAppDir}\data\*"; DestDir: "{app}\data"; Flags: onlyifdoesntexist recursesubdirs createallsubdirs; Components: core; Permissions: users-full

[Icons]
; Основной ярлык на Рабочем столе
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\AvitoHunter_Start.bat"; WorkingDir: "{app}"; IconFilename: "{app}\img\skybase.ico"; Tasks: desktopicon

; Ярлыки в меню Пуск
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\AvitoHunter_Start.bat"; WorkingDir: "{app}"; IconFilename: "{app}\img\skybase.ico"
Name: "{autoprograms}\{#MyAppName}\Папка с данными программы"; Filename: "{app}\data"
Name: "{autoprograms}\{#MyAppName}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; Чекбокс на странице завершения
Filename: "{app}\AvitoHunter_Start.bat"; Description: "Запустить AvitoHunter прямо сейчас"; Flags: postinstall shellexec skipifsilent

[InstallDelete]
Type: files; Name: "{app}\*.pid"
Type: files; Name: "{app}\*.log"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\*.log"
Type: filesandordirs; Name: "{app}\*.pid"
Type: filesandordirs; Name: "{app}\data"
Type: filesandordirs; Name: "{app}\avito_bot\*.log"
Type: filesandordirs; Name: "{app}\avito_bot\*.db*"
Type: filesandordirs; Name: "{app}\avito_bot\__pycache__"
Type: filesandordirs; Name: "{app}"

[Code]
// Блокировка/разблокировка чекбоксов компонентов в зависимости от выбранного режима установки:
// 1. При "Полная установка" (full) — все компоненты отмечены и заблокированы (снять галочки нельзя).
// 2. При "Выборочная установка" (custom) — чекбоксы разблокированы для свободного включения/отключения.

procedure UpdateComponentsLock;
var
  I: Integer;
  IsFull: Boolean;
begin
  // ItemIndex = 0 соответствует первому типу в секции [Types]: "full" (Полная установка)
  IsFull := (WizardForm.TypesCombo.ItemIndex = 0);
  for I := 0 to WizardForm.ComponentsList.Items.Count - 1 do
  begin
    if IsFull then
    begin
      WizardForm.ComponentsList.Checked[I] := True;
      WizardForm.ComponentsList.ItemEnabled[I] := False;
    end
    else
    begin
      WizardForm.ComponentsList.ItemEnabled[I] := True;
    end;
  end;
end;

procedure TypesComboOnChange(Sender: TObject);
begin
  UpdateComponentsLock;
end;

procedure ComponentsListOnClickCheck(Sender: TObject);
begin
  // Дополнительная защита: в режиме полной установки чекбоксы принудительно заблокированы
  if WizardForm.TypesCombo.ItemIndex = 0 then
    UpdateComponentsLock;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  // При переходе на страницу выбора компонентов актуализируем состояние чекбоксов
  if CurPageID = wpSelectComponents then
  begin
    UpdateComponentsLock;
  end;
end;

procedure InitializeWizard;
begin
  WizardForm.TypesCombo.OnChange := @TypesComboOnChange;
  WizardForm.ComponentsList.OnClickCheck := @ComponentsListOnClickCheck;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Завершаем запущенные процессы перед удалением файлов
    Exec('taskkill.exe', '/f /im AvitoHunter.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('taskkill.exe', '/f /im app_launcher.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec('taskkill.exe', '/f /im python.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Sleep(500);
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    // Полное удаление директории со всеми логами, кэшем и временными файлами
    DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
