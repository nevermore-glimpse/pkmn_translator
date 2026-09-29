Option Explicit

' Pokemon fan-game translation tool - create a desktop shortcut.
'
' Kept pure ASCII on purpose: Windows Script Host reads .vbs as ANSI, so
' Chinese literals turn into garbage the moment the file is re-saved in
' another encoding, and the FileExists() checks silently stop matching.
' Instead of hardcoding names we scan the folder this script lives in.

Dim fso, shell, scriptDir, desktop, lnkPath, iconPath, target, folder, f

Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
desktop   = shell.SpecialFolders("Desktop")
lnkPath   = desktop & "\PkmnTranslator.lnk"
iconPath  = scriptDir & "\start.ico"

Set folder = fso.GetFolder(scriptDir)
target = ""

' 1) prefer a *.exe shipped next to this script (name containing "Pkmn" wins)
For Each f In folder.Files
    If LCase(fso.GetExtensionName(f.Name)) = "exe" Then
        If target = "" Then target = f.Path
        If InStr(LCase(f.Name), "pkmn") > 0 Then target = f.Path
    End If
Next

' 2) no exe -> fall back to a launcher .bat (name containing "Start" wins)
If target = "" Then
    For Each f In folder.Files
        If LCase(fso.GetExtensionName(f.Name)) = "bat" Then
            If InStr(LCase(f.Name), "start") > 0 Then
                target = f.Path
                Exit For
            ElseIf target = "" Then
                target = f.Path
            End If
        End If
    Next
End If

If target = "" Then
    MsgBox "No .exe or .bat found next to this script:" & vbCrLf & vbCrLf & _
           scriptDir, 16, "Error"
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

MsgBox "Shortcut created:" & vbCrLf & vbCrLf & lnkPath & vbCrLf & _
       "Target: " & target, 64, "Done"
