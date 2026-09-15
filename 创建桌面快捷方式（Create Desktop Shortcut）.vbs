Option Explicit

Dim fso, shell, scriptDir, desktop, lnkPath, target, iconPath
Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
desktop   = shell.SpecialFolders("Desktop")
lnkPath   = desktop & "\PkmnTranslator.lnk"
iconPath  = scriptDir & "\start.ico"

' ������ exe���˻� bat
If fso.FileExists(scriptDir & "\PkmnTranslator.exe") Then
    target = scriptDir & "\PkmnTranslator.exe"
ElseIf fso.FileExists(scriptDir & "\�����η��빤��.exe") Then
    target = scriptDir & "\�����η��빤��.exe"
ElseIf fso.FileExists(scriptDir & "\Start.bat") Then
    target = scriptDir & "\Start.bat"
ElseIf fso.FileExists(scriptDir & "\������Start��.bat") Then
    target = scriptDir & "\������Start��.bat"
Else
    MsgBox "No exe or bat found in: " & scriptDir, 16, "Error"
    WScript.Quit 1
End If

Dim lnk
Set lnk = shell.CreateShortcut(lnkPath)
lnk.TargetPath       = target
lnk.WorkingDirectory = scriptDir
lnk.Description      = "Pokemon Fan Game Translation Tool"
lnk.WindowStyle      = 1
If fso.FileExists(iconPath) Then
    lnk.IconLocation = iconPath
End If
lnk.Save

MsgBox "Shortcut created: " & lnkPath, 64, "Done"